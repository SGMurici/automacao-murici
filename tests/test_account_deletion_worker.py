import unittest
from unittest.mock import patch

import account_deletion_worker as worker


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.executed = []
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def execute(self, query, params=None):
        self.executed.append((query, params))
    def fetchone(self):
        return self.rows.pop(0) if self.rows else None
    def fetchall(self):
        return self.rows


class FakeTransaction:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, lock=True, request_ids=None):
        self.cursor_calls = 0
        self.cursors = [
            FakeCursor([(lock,)]),
            FakeCursor([(value,) for value in (request_ids or [])]),
        ]
        self.unlock_cursor = FakeCursor()
        self.commits = 0
        self.closed = False
        self.transactions = 0
    def cursor(self):
        if self.cursor_calls < len(self.cursors):
            cursor = self.cursors[self.cursor_calls]
            self.cursor_calls += 1
            return cursor
        return self.unlock_cursor
    def commit(self):
        self.commits += 1
    def transaction(self):
        self.transactions += 1
        return FakeTransaction()
    def close(self):
        self.closed = True


class DeletionWorkerTests(unittest.TestCase):
    def test_busy_lock_does_not_query_or_process_requests(self):
        conn = FakeConnection(lock=False)
        result = worker.run_ready_deletions(lambda: conn)
        self.assertEqual(result, {"status": "busy", "processed": 0, "failed": 0})
        self.assertTrue(conn.closed)
        self.assertEqual(conn.cursor_calls, 1)

    def test_processes_only_candidates_returned_by_ready_gate_query(self):
        request_ids = ["request-1", "request-2"]
        conn = FakeConnection(request_ids=request_ids)
        with patch.object(
            worker.account_deletion_core,
            "process_primary_database_deletion",
            side_effect=[True, True],
        ) as purge:
            result = worker.run_ready_deletions(lambda: conn, batch_size=5)

        self.assertEqual(
            result, {"status": "completed", "processed": 2, "failed": 0}
        )
        self.assertEqual(
            [call.args[1] for call in purge.call_args_list], request_ids
        )
        self.assertEqual(conn.transactions, 2)
        self.assertTrue(conn.closed)
        query, params = conn.cursors[1].executed[0]
        self.assertIn("COUNT(*)", query)
        self.assertIn("s.status IN ('completed', 'not_applicable')", query)
        self.assertEqual(params, (4, 5))

    def test_one_failed_request_does_not_prevent_next_request(self):
        conn = FakeConnection(request_ids=["bad", "good"])
        with patch.object(
            worker.account_deletion_core,
            "process_primary_database_deletion",
            side_effect=[RuntimeError("database failure"), True],
        ):
            result = worker.run_ready_deletions(lambda: conn)

        self.assertEqual(
            result, {"status": "completed_with_errors", "processed": 1, "failed": 1}
        )
        self.assertEqual(conn.transactions, 2)
        self.assertTrue(conn.closed)

    def test_rejects_invalid_batch_size(self):
        for value in (True, 0, -1, 101, "10"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    worker.run_ready_deletions(lambda: self.fail("connection opened"), value)


if __name__ == "__main__":
    unittest.main()
