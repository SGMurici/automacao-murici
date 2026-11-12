"""One-shot OTP email outbox worker. No scheduler is installed by this module."""
import json
import os
import sys

import psycopg

import email_delivery
import otp_email_outbox


def run_once(connection_factory, batch_size=1):
    stats = {"claimed": 0, "sent": 0, "retrying": 0, "failed": 0}
    with connection_factory() as conn:
        otp_email_outbox.expire_due(conn)
        jobs = otp_email_outbox.claim_batch(conn, batch_size)
        conn.commit()
    stats["claimed"] = len(jobs)

    for job in jobs:
        try:
            payload = otp_email_outbox.decrypt_payload(job["ciphertext"])
            if payload["challenge_id"] != job["challenge_id"]:
                # A valid ciphertext bound to another challenge is corrupt/misbound
                # data, not a transient key/configuration failure. Never deliver it.
                raise otp_email_outbox.OutboxPayloadError("OTP challenge mismatch")
            delivery = email_delivery.send_otp_email(
                payload["recipient"], payload["code"], payload["purpose"],
                expires_minutes=payload["expires_minutes"],
            )
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_sent(
                    conn, job["challenge_id"], job["lease_token"],
                    delivery["message_id"],
                )
                conn.commit()
            if finalized:
                stats["sent"] += 1
        except email_delivery.EmailDeliveryError:
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], False, "provider_transient",
                )
                conn.commit()
            if finalized:
                stats["retrying"] += 1
        except otp_email_outbox.OutboxPayloadError:
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], True, "payload_invalid",
                )
                conn.commit()
            if finalized:
                stats["failed"] += 1
        except otp_email_outbox.OutboxConfigurationError:
            # Missing/reused key configuration is operational: retain payload and retry.
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], False, "configuration",
                )
                conn.commit()
            if finalized:
                stats["retrying"] += 1
        except Exception:
            # Unknown failures are retried with the same challenge/code. Never log payload.
            with connection_factory() as conn:
                finalized = otp_email_outbox.mark_failure(
                    conn, job["challenge_id"], job["lease_token"],
                    job["attempts"], False, "provider_transient",
                )
                conn.commit()
            if finalized:
                stats["retrying"] += 1
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
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
