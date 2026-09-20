"""The sing-box domain provider (child-repo integration fork).

The neutral engine lives in the parent repository; this package owns all
sing-box domain detail and follows ``PROVIDER_STANDARD.md``.
"""

from .provider import SingBoxProvider

__all__ = ["SingBoxProvider"]
