import json
import unittest
from unittest.mock import patch

from whatsapp_cloud_api import (
    WhatsAppConfigurationError,
    build_email_summary_message,
    send_test_template,
)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"messages": [{"id": "provider-id"}]}).encode()


class WhatsAppCloudApiTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "WHATSAPP_TEST_MODE": "true",
            "WHATSAPP_TEST_SEND_ENABLED": "true",
            "WHATSAPP_TEST_RECIPIENTS": "5511999999999",
            "WHATSAPP_ACCESS_TOKEN": "test-token",
            "WHATSAPP_PHONE_NUMBER_ID": "test-phone-id",
            "WHATSAPP_GRAPH_API_VERSION": "v23.0",
            "WHATSAPP_TEST_TEMPLATE": "hello_world",
            "WHATSAPP_TEST_TEMPLATE_LANGUAGE": "en_US",
        }

    def test_send_is_disabled_without_explicit_test_mode(self):
        self.env["WHATSAPP_TEST_MODE"] = "false"
        with self.assertRaises(WhatsAppConfigurationError):
            send_test_template("5511999999999", env=self.env, opener=lambda *a, **k: self.fail())

    def test_send_is_disabled_by_default(self):
        self.env["WHATSAPP_TEST_SEND_ENABLED"] = "false"
        with self.assertRaises(WhatsAppConfigurationError):
            send_test_template("5511999999999", env=self.env, opener=lambda *a, **k: self.fail())

    def test_non_allowlisted_recipient_is_blocked_before_network(self):
        with self.assertRaises(WhatsAppConfigurationError):
            send_test_template("5511888888888", env=self.env, opener=lambda *a, **k: self.fail())

    def test_only_template_payload_is_sent_to_allowlisted_recipient(self):
        captured = {}

        def fake_opener(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode())
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse()

        result = send_test_template("+55 (11) 99999-9999", env=self.env, opener=fake_opener)
        self.assertEqual(result, {"status": "accepted", "provider": "meta", "message_count": 1})
        self.assertEqual(captured["payload"]["type"], "template")
        self.assertEqual(captured["payload"]["template"]["name"], "hello_world")
        self.assertEqual(captured["payload"]["to"], "5511999999999")
        self.assertEqual(captured["authorization"], "Bearer test-token")

    def test_summary_contains_aggregates_only(self):
        message = build_email_summary_message({
            "total": 8,
            "categories": {"seguranca_conta": 2, "nao_classificado": 6},
            "priorities": {"alta": 2, "normal": 6},
            "private_subject": "must never appear",
        })
        self.assertIn("Mensagens analisadas: 8", message)
        self.assertNotIn("must never appear", message)
        self.assertNotIn("subject", message.lower())

    def test_summary_rejects_invalid_total(self):
        with self.assertRaises(ValueError):
            build_email_summary_message({"total": True, "categories": {}, "priorities": {}})


if __name__ == "__main__":
    unittest.main()
