import unittest

from identity_policy import (
    AuthorizationDenied,
    Principal,
    require_principal,
    require_role,
    require_same_tenant,
    require_same_user,
)


class IdentityPolicyTests(unittest.TestCase):
    def test_missing_principal_is_denied(self):
        with self.assertRaises(AuthorizationDenied):
            require_principal(None)

    def test_same_user_can_access_owned_resource(self):
        require_same_user(Principal("user-a"), "user-a")

    def test_other_user_is_denied(self):
        with self.assertRaises(AuthorizationDenied):
            require_same_user(Principal("user-a"), "user-b")

    def test_missing_resource_owner_is_denied(self):
        with self.assertRaises(AuthorizationDenied):
            require_same_user(Principal("user-a"), None)

    def test_same_tenant_can_access_resource(self):
        require_same_tenant(Principal("user-a", "family-a"), "family-a")

    def test_cross_tenant_is_denied(self):
        with self.assertRaises(AuthorizationDenied):
            require_same_tenant(Principal("user-a", "family-a"), "family-b")

    def test_missing_tenant_context_is_denied(self):
        with self.assertRaises(AuthorizationDenied):
            require_same_tenant(Principal("user-a"), "family-a")

    def test_family_membership_does_not_grant_resource_owner_role(self):
        member = Principal("user-a", "family-a", frozenset({"family_member"}))
        with self.assertRaises(AuthorizationDenied):
            require_role(member, "resource_owner")

    def test_explicit_role_is_required(self):
        require_role(Principal("user-a", roles=frozenset({"admin"})), "admin")


if __name__ == "__main__":
    unittest.main()
