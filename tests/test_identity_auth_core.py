import unittest

import identity_auth_core


class IdentityAuthConfigurationTests(unittest.TestCase):
    def test_required_pepper_requires_at_least_32_bytes(self):
        self.assertEqual(
            identity_auth_core.required_pepper(
                "OTP_PEPPER", {"OTP_PEPPER": "x" * 32}
            ),
            b"x" * 32,
        )
        with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
            identity_auth_core.required_pepper("OTP_PEPPER", {"OTP_PEPPER": "short"})

    def test_trusted_client_ip_uses_rightmost_trusted_proxy_count(self):
        ip = identity_auth_core.trusted_client_ip(
            ["198.51.100.20", "203.0.113.10"],
            {"OTP_TRUSTED_PROXY_HOPS": "2"},
        )
        self.assertEqual(ip, "198.51.100.20")

    def test_trusted_client_ip_canonicalizes_ipv4_mapped_ipv6(self):
        ip = identity_auth_core.trusted_client_ip(
            ["::ffff:192.0.2.45"],
            {"OTP_TRUSTED_PROXY_HOPS": "1"},
        )
        self.assertEqual(ip, "192.0.2.45")

    def test_trusted_client_ip_fails_closed_without_proxy_configuration(self):
        with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
            identity_auth_core.trusted_client_ip(["198.51.100.20"], {})

    def test_trusted_client_ip_rejects_incomplete_chain(self):
        with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
            identity_auth_core.trusted_client_ip(
                ["198.51.100.20"],
                {"OTP_TRUSTED_PROXY_HOPS": "2"},
            )

    def test_trusted_client_ip_rejects_invalid_address(self):
        with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
            identity_auth_core.trusted_client_ip(
                ["not-an-ip"],
                {"OTP_TRUSTED_PROXY_HOPS": "1"},
            )

    def test_trusted_client_ip_rejects_out_of_range_proxy_count(self):
        with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
            identity_auth_core.trusted_client_ip(
                ["198.51.100.20"],
                {"OTP_TRUSTED_PROXY_HOPS": "9"},
            )


if __name__ == "__main__":
    unittest.main()
