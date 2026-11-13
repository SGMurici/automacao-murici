"""Tests for independent OTP and editorial scheduler dispatch."""
import unittest
from unittest.mock import call, patch

import app as application


class SchedulerDispatcherTests(unittest.TestCase):
    def test_runs_otp_before_cleanup_and_editorial(self):
        events = []

        def otp(*args, **kwargs):
            events.append("otp")
            self.assertEqual(kwargs, {"batch_size": 1})
            return {"claimed": 1, "sent": 1, "retrying": 0, "failed": 0}

        def cleanup():
            events.append("cleanup")
            return 2

        def publish():
            events.append("editorial")
            return {"status": "publicado", "post_number": 12}

        with (
            patch.object(application.otp_email_outbox_worker, "run_once", side_effect=otp),
            patch.object(application, "cleanup_expired_pending_signups", side_effect=cleanup),
            patch.object(application, "scheduler_publish_one", side_effect=publish),
        ):
            result = application.scheduler_run_cycle()

        self.assertEqual(events, ["otp", "cleanup", "editorial"])
        self.assertEqual(result["status"], "publicado")
        self.assertEqual(result["otp_delivery"]["sent"], 1)
        self.assertEqual(result["pending_signup_cleanup"]["removed"], 2)

    def test_uncertain_otp_delivery_is_reported_without_blocking_other_queues(self):
        with (
            patch.object(
                application.otp_email_outbox_worker,
                "run_once",
                return_value={"claimed": 1, "sent": 0, "retrying": 0, "failed": 0, "uncertain": 1},
            ),
            patch.object(application, "cleanup_expired_pending_signups", return_value=0),
            patch.object(application, "scheduler_publish_one", return_value={"status": "idle"}),
        ):
            result = application.scheduler_run_cycle()

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["otp_delivery"]["status"], "uncertain")
        self.assertEqual(result["otp_delivery"]["uncertain"], 1)
        self.assertEqual(result["pending_signup_cleanup"]["status"], "completed")

    def test_otp_failure_does_not_block_editorial_or_cleanup(self):
        with (
            patch.object(
                application.otp_email_outbox_worker,
                "run_once",
                side_effect=RuntimeError("database unavailable"),
            ),
            patch.object(application, "cleanup_expired_pending_signups", return_value=0),
            patch.object(application, "scheduler_publish_one", return_value={"status": "idle"}),
        ):
            result = application.scheduler_run_cycle()

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["otp_delivery"], {"status": "error"})
        self.assertEqual(result["pending_signup_cleanup"]["status"], "completed")

    def test_cleanup_failure_does_not_block_otp_or_editorial(self):
        with (
            patch.object(
                application.otp_email_outbox_worker,
                "run_once",
                return_value={"claimed": 0, "sent": 0, "retrying": 0, "failed": 0},
            ),
            patch.object(
                application,
                "cleanup_expired_pending_signups",
                side_effect=RuntimeError("cleanup unavailable"),
            ),
            patch.object(application, "scheduler_publish_one", return_value={"status": "idle"}),
        ):
            result = application.scheduler_run_cycle()

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["otp_delivery"]["status"], "completed")
        self.assertEqual(result["pending_signup_cleanup"], {"status": "error"})

    def test_editorial_failure_preserves_otp_result(self):
        with (
            patch.object(
                application.otp_email_outbox_worker,
                "run_once",
                return_value={"claimed": 1, "sent": 1, "retrying": 0, "failed": 0},
            ),
            patch.object(application, "cleanup_expired_pending_signups", return_value=0),
            patch.object(
                application,
                "scheduler_publish_one",
                side_effect=RuntimeError("LinkedIn unavailable"),
            ),
        ):
            result = application.scheduler_run_cycle()

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["otp_delivery"]["sent"], 1)

    def test_scheduler_route_keeps_existing_uncertain_status_code(self):
        payload = {
            "status": "incerto",
            "mensagem": "Verifique o resultado externo antes de tentar novamente.",
            "queue_id": 17,
            "reconciliacao_manual": True,
            "otp_delivery": {"status": "completed", "claimed": 0},
            "pending_signup_cleanup": {"status": "completed", "removed": 0},
        }
        with (
            patch.object(application, "require_publish_secret", return_value=None),
            patch.object(application, "scheduler_run_cycle", return_value=payload),
        ):
            response = application.app.test_client().post("/scheduler/run")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["status"], "incerto")
        self.assertEqual(response.get_json()["otp_delivery"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
