import contextlib
import io
import os
import unittest
from unittest.mock import patch

import run_account_deletion_worker as cli


class DeletionWorkerCliTests(unittest.TestCase):
    def test_requires_database_url_without_opening_connection(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(
            cli.psycopg, "connect"
        ) as connect, contextlib.redirect_stderr(output):
            result = cli.main()
        self.assertEqual(result, 2)
        self.assertIn("DATABASE_URL", output.getvalue())
        connect.assert_not_called()

    def test_runs_worker_and_prints_machine_readable_result(self):
        output = io.StringIO()
        expected = {"status": "completed", "processed": 1, "failed": 0}
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}), patch.object(
            cli, "run_ready_deletions", return_value=expected
        ) as run_worker, contextlib.redirect_stdout(output):
            result = cli.main()
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), '{"status": "completed", "processed": 1, "failed": 0}')
        factory = run_worker.call_args.args[0]
        with patch.object(cli.psycopg, "connect", return_value="connection") as connect:
            self.assertEqual(factory(), "connection")
        connect.assert_called_once_with("postgresql://test", connect_timeout=10)


if __name__ == "__main__":
    unittest.main()
