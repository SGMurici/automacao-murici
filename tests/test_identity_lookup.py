import hashlib
import unittest

import identity_lookup


class IdentityLookupTests(unittest.TestCase):
    def test_email_is_trimmed_casefolded_and_idna_normalized(self):
        self.assertEqual(
            identity_lookup.normalize_identity("email", "  USER@Exämple.COM  "),
            "user@xn--exmple-cua.com",
        )

    def test_phone_formatting_is_normalized_to_e164(self):
        self.assertEqual(
            identity_lookup.normalize_identity("phone", "+55 (21) 98765-4321"),
            "+5521987654321",
        )

    def test_phone_requires_explicit_country_code_and_valid_length(self):
        for value in ("21987654321", "+0123456789", "+123", "+1234567890123456"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    identity_lookup.normalize_identity("phone", value)

    def test_invalid_email_and_identity_type_are_rejected(self):
        for value in ("missing-at.example", "a..b@example.com", "user@-bad.example", "user @example.com"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    identity_lookup.normalize_identity("email", value)
        with self.assertRaises(ValueError):
            identity_lookup.normalize_identity("username", "murici")

    def test_lookup_digest_is_keyed_deterministic_and_domain_separated(self):
        pepper = b"kappa-identity-lookup-pepper-32-bytes-min"
        email_a = identity_lookup.hash_identity_lookup("email", "USER@EXAMPLE.COM", pepper)
        email_b = identity_lookup.hash_identity_lookup("email", " user@example.com ", pepper)
        phone = identity_lookup.hash_identity_lookup("phone", "+1 (202) 555-0100", pepper)
        rotated_key = identity_lookup.hash_identity_lookup(
            "email", "user@example.com", b"different-identity-pepper-32-bytes"
        )
        self.assertEqual(len(email_a), 32)
        self.assertEqual(email_a, email_b)
        self.assertNotEqual(email_a, phone)
        self.assertNotEqual(email_a, rotated_key)
        self.assertNotEqual(email_a, hashlib.sha256(b"user@example.com").digest())

    def test_weak_pepper_is_rejected(self):
        with self.assertRaises(ValueError):
            identity_lookup.hash_identity_lookup("email", "user@example.com", b"short")


if __name__ == "__main__":
    unittest.main()
