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


if __name__ == "__main__":
    unittest.main()
