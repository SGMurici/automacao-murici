"""HTTP semantics for uncertain scheduler outcomes."""
import unittest
from unittest.mock import patch

import app as application


class SchedulerResponseTests(unittest.TestCase):
    def test_uncertain_publish_result_returns_accepted_not_server_error(self):
        payload = {
            "status": "incerto",
            "mensagem": "Verifique o resultado externo antes de tentar novamente.",
            "queue_id": 17,
            "reconciliacao_manual": True,
        }
        with (
            patch.object(application, "require_publish_secret", return_value=None),
            patch.object(application, "scheduler_publish_one", return_value=payload),
        ):
            response = application.app.test_client().post("/scheduler/run")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["status"], "incerto")
        self.assertTrue(response.get_json()["reconciliacao_manual"])


if __name__ == "__main__":
    unittest.main()
