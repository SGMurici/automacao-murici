"""HTTP tests for the separately callable scheduler watchdog."""
import unittest
from unittest.mock import MagicMock, patch

import app as application


class SchedulerWatchdogRouteTests(unittest.TestCase):
    def _locked_connection(self, acquired):
        connection = MagicMock()
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        cursor.fetchone.return_value = (acquired,)
        connection.cursor.return_value = cursor
        return connection, cursor

    def test_watchdog_recovers_expired_rows_under_dispatcher_lock(self):
        connection, cursor = self._locked_connection(True)
        with (
            patch.object(application, "require_publish_secret", return_value=None),
            patch.object(application, "ensure_scheduler_tables"),
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application, "scheduler_recover_expired_processing", return_value=2) as recover,
        ):
            response = application.app.test_client().post("/scheduler/recover")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["recuperadas_para_reconciliacao"], 2)
        recover.assert_called_once_with()
        self.assertTrue(any("pg_advisory_unlock" in str(call) for call in cursor.execute.call_args_list))
        connection.close.assert_called_once_with()

    def test_watchdog_returns_conflict_when_dispatcher_holds_lock(self):
        connection, _cursor = self._locked_connection(False)
        with (
            patch.object(application, "require_publish_secret", return_value=None),
            patch.object(application, "ensure_scheduler_tables"),
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application, "scheduler_recover_expired_processing") as recover,
        ):
            response = application.app.test_client().post("/scheduler/recover")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "busy")
        recover.assert_not_called()
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
