"""cMCP policy adapter and signed TRACE v0.2 Trust Record exporter.

``build_trace_record`` emits a software-only Level 0 record signed by the
independent Ed25519 key in ``TRACE_PRIVATE_KEY_PEM``.
"""

from .trace_mapper import build_trace_record
from .policy_adapter import RamenCmcpAdapter, AdapterDecision
from ._receipt_verify import verify_v5_receipt

__all__ = [
    "build_trace_record",
    "RamenCmcpAdapter",
    "AdapterDecision",
    "verify_v5_receipt",
]
