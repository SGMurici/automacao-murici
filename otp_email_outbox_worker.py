"""One-shot OTP email outbox worker. No scheduler is installed by this module."""
import json
import os
import sys

import psycopg

import email_delivery
import otp_email_outbox


def run_once(connection_factory, batch_size=1):
    stats = {"claimed": 0, "sent": 0, "retrying": 0, "failed": 0, "uncertain": 0}
    with connection_factory() as conn:
        otp_email_outbox.expire_due(conn)
        jobs = otp_email_outbox.claim_batch(conn, batch_size)
        conn.commit()
    stats["claimed"] = len(jobs)

    for job in jobs:
        # Decryption/configuration failures happen before SMTP dispatch and are safe to retry.
        try:
            payload = otp_email_outbox.decrypt_payload(job["ciphertext"])
            if payload["challenge_id"] != job["challenge_id"]:
                raise otp_email_outbox.OutboxPayloadError("OTP challenge mismatch")
        except otp_email_outbox.OutboxPayloadError:
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], True, "payload_invalid",
                )
                conn.commit()
            if finalized:
                stats["failed"] += 1
            continue
        except otp_email_outbox.OutboxConfigurationError:
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], False, "configuration",
                )
                conn.commit()
            if finalized:
                stats["retrying"] += 1
            continue

        # Commit dispatching before touching SMTP. An expired dispatching lease
        # becomes uncertain and is never reclaimed for another send.
        with connection_factory() as conn:
            dispatching = otp_email_outbox.mark_dispatching(
                conn, job["challenge_id"], job["lease_token"]
            )
            conn.commit()
        if not dispatching:
            stats["uncertain"] += 1
            continue

        try:
            delivery = email_delivery.send_otp_email(
                payload["recipient"], payload["code"], payload["purpose"],
                expires_minutes=payload["expires_minutes"],
            )
        except email_delivery.EmailDeliveryUncertain:
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_uncertain(
                    conn, job["challenge_id"], job["lease_token"]
                )
                conn.commit()
            if finalized:
                stats["uncertain"] += 1
            continue
        except email_delivery.EmailDeliveryError:
            # This exception is reserved for failures before SMTP DATA or an
            # explicit recipient refusal, where automatic retry cannot duplicate.
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], False, "provider_transient",
                )
                conn.commit()
            if finalized:
                stats["retrying"] += 1
            continue
        except Exception:
            # Unknown send-phase failures are conservative: do not risk a duplicate.
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_uncertain(
                    conn, job["challenge_id"], job["lease_token"]
                )
                conn.commit()
            if finalized:
                stats["uncertain"] += 1
            continue

        # If SMTP returned success but DB finalization fails, let the lease expire.
        # expire_due will mark it uncertain; this code must never schedule a retry.
        with connection_factory() as conn:
            finalized = otp_email_outbox.mark_sent(
                conn, job["challenge_id"], job["lease_token"],
                delivery["message_id"],
            )
            conn.commit()
        if finalized:
            stats["sent"] += 1
        else:
            stats["uncertain"] += 1
    return stats

def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL não configurado.", file=sys.stderr)
        return 2
    try:
        result = run_once(lambda: psycopg.connect(database_url, connect_timeout=10))
    except Exception:
        print("Falha ao executar worker de e-mail OTP.", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not result["failed"] and not result["uncertain"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
