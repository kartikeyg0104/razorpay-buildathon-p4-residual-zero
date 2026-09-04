"""Who is asking, and which organisation they may ask about.

This package holds the *only* thing in Residual Zero that decides identity. It has no
opinion about financial truth: it resolves a credential to a
:class:`~residual_zero.identity.store.Principal` and binds that principal's organisation,
and every financial answer still comes from the deterministic engine afterwards.

No role in here can authorise ``CLEARED``. That gate belongs to the solver and the verifier
(``UNIQUE`` + zero-paise residual + ``FULL`` pool + a derived threshold) and is not
expressible as a permission, which is why ``clear`` is absent from the permission set.
"""

from residual_zero.identity.store import (
    IdentityStore,
    Principal,
    Role,
    hash_password,
    verify_password,
)

__all__ = ["IdentityStore", "Principal", "Role", "hash_password", "verify_password"]
