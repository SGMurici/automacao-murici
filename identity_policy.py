"""Fail-closed identity and tenant-isolation policy helpers.

Pure functions only: no Flask, database, network, or production integration.
These helpers are not authentication and must only be called after a trusted
authentication layer has verified the principal.
"""
from dataclasses import dataclass


class AuthorizationDenied(PermissionError):
    """Raised when a principal cannot access a tenant-owned resource."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str | None = None
    roles: frozenset[str] = frozenset()


def require_principal(principal: Principal | None) -> Principal:
    if principal is None or not isinstance(principal, Principal):
        raise AuthorizationDenied("Authenticated principal required.")
    if not isinstance(principal.user_id, str) or not principal.user_id.strip():
        raise AuthorizationDenied("Authenticated user identifier required.")
    return principal


def require_same_user(principal: Principal | None, owner_user_id: str | None) -> None:
    actor = require_principal(principal)
    if not isinstance(owner_user_id, str) or not owner_user_id.strip():
        raise AuthorizationDenied("Resource owner is missing.")
    if actor.user_id != owner_user_id:
        raise AuthorizationDenied("Cross-user access denied.")


def require_same_tenant(principal: Principal | None, resource_tenant_id: str | None) -> None:
    actor = require_principal(principal)
    if not actor.tenant_id or not resource_tenant_id:
        raise AuthorizationDenied("Tenant context is required.")
    if actor.tenant_id != resource_tenant_id:
        raise AuthorizationDenied("Cross-tenant access denied.")


def require_role(principal: Principal | None, required_role: str) -> None:
    actor = require_principal(principal)
    if not isinstance(required_role, str) or not required_role.strip():
        raise ValueError("required_role must be a non-empty string.")
    if required_role not in actor.roles:
        raise AuthorizationDenied("Required role is missing.")
