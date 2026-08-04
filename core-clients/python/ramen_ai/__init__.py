"""ramen-ai-core — Python client and Ed25519 V5 verifier for the ramen-ai cloud API."""

from .client import RamenClient
from .verifier import verify_receipt

__all__ = ["RamenClient", "verify_receipt"]
__version__ = "0.2.1"
