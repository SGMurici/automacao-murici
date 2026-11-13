import unittest

import identity_auth_core


class IdentityAuthConfigurationTests(unittest.TestCase):
    def test_trusted_proxy_networks_reject_catch_all_cidrs(self):
        for cidr in ("0.0.0.0/0", "::/0"):
            with self.subTest(cidr=cidr):
                with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
                    identity_auth_core.trusted_proxy_networks({"TRUSTED_PROXY_CIDRS": cidr})

    def test_trusted_proxy_networks_accept_explicit_ranges(self):
        networks = identity_auth_core.trusted_proxy_networks(
            {"TRUSTED_PROXY_CIDRS": "10.0.0.0/8,192.0.2.0/24"}
        )
        self.assertEqual(len(networks), 2)

    def test_required_pepper_requires_at_least_32_bytes(self):
        self.assertEqual(
            identity_auth_core.required_pepper(
                "OTP_PEPPER", {"OTP_PEPPER": "x" * 32}
            ),
            b"x" * 32,
        )
        with self.assertRaises(identity_auth_core.IdentityAuthConfigurationError):
            identity_auth_core.required_pepper("OTP_PEPPER", {"OTP_PEPPER": "short"})


if __name__ == "__main__":
    unittest.main()
