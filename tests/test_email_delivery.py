import os
import unittest
from unittest.mock import MagicMock, patch

import email_delivery


class EmailDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "587",
            "SMTP_FROM": "no-reply@example.test",
            "SMTP_USERNAME": "user",
            "SMTP_PASSWORD": "secret",
            "SMTP_USE_TLS": "true",
            "SMTP_USE_SSL": "false",
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=True)
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    def test_builds_operational_message(self):
        message = email_delivery.build_otp_message("User@example.test", "00123456", "signup")
        body = message.get_content()
        self.assertEqual(message["To"], "user@example.test")
        self.assertEqual(message["Subject"], "Confirme seu e-mail")
        self.assertNotIn("KAPPA", message["Subject"])
        self.assertIn("00123456", body)
        self.assertIn("não contém publicidade", body)
        self.assertIn("\n\n", body)
        self.assertNotIn("\\n", body)

    def test_rejects_invalid_code_and_purpose(self):
        with self.assertRaises(ValueError):
            email_delivery.build_otp_message("user@example.test", "123", "signup")
        with self.assertRaises(ValueError):
            email_delivery.build_otp_message("user@example.test", "12345678", "marketing")

    def test_requires_tls(self):
        os.environ["SMTP_USE_TLS"] = "false"
        with self.assertRaises(email_delivery.EmailDeliveryError):
            email_delivery._smtp_config()

    def test_requires_authenticated_smtp_even_when_both_credentials_are_missing(self):
        os.environ.pop("SMTP_USERNAME")
        os.environ.pop("SMTP_PASSWORD")
        with self.assertRaises(email_delivery.EmailDeliveryError):
            email_delivery._smtp_config()

    def test_rejects_conflicting_tls_modes(self):
        os.environ["SMTP_USE_SSL"] = "true"
        with self.assertRaises(email_delivery.EmailDeliveryError):
            email_delivery._smtp_config()

    def test_requires_complete_credentials(self):
        os.environ.pop("SMTP_PASSWORD")
        with self.assertRaises(email_delivery.EmailDeliveryError):
            email_delivery._smtp_config()

    @patch("email_delivery.smtplib.SMTP")
    def test_sends_with_starttls_and_returns_message_id(self, smtp_cls):
        client = MagicMock()
        client.send_message.return_value = {}
        smtp_cls.return_value = client

        result = email_delivery.send_otp_email("User@example.test", "00123456", "signup")

        client.ehlo.assert_called()
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("user", "secret")
        client.send_message.assert_called_once()
        self.assertEqual(client.send_message.call_args.kwargs["to_addrs"], ["user@example.test"])
        client.quit.assert_called_once()
        self.assertTrue(result["message_id"].startswith("<"))

    @patch("email_delivery.smtplib.SMTP_SSL")
    def test_uses_implicit_tls_when_configured(self, smtp_ssl_cls):
        os.environ["SMTP_USE_SSL"] = "true"
        os.environ["SMTP_USE_TLS"] = "false"
        client = MagicMock()
        client.send_message.return_value = {}
        smtp_ssl_cls.return_value = client

        email_delivery.send_otp_email("user@example.test", "00123456", "login")

        smtp_ssl_cls.assert_called_once()
        client.starttls.assert_not_called()

    @patch("email_delivery.smtplib.SMTP")
    def test_rejects_refused_recipient(self, smtp_cls):
        client = MagicMock()
        client.send_message.return_value = {"user@example.test": (550, b"rejected")}
        smtp_cls.return_value = client

        with self.assertRaisesRegex(email_delivery.EmailDeliveryError, "recusou"):
            email_delivery.send_otp_email("user@example.test", "00123456", "signup")

    @patch("email_delivery.smtplib.SMTP")
    def test_sanitizes_provider_errors(self, smtp_cls):
        smtp_cls.side_effect = OSError("provider response with secret details")
        with self.assertRaises(email_delivery.EmailDeliveryError) as raised:
            email_delivery.send_otp_email("user@example.test", "00123456", "signup")
        self.assertNotIn("secret details", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
