"""Email integration for Hestia."""

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter, EmailAdapterError

__all__ = ["EmailAdapter", "EmailConfig", "EmailAdapterError"]
