"""ramen_cmcp — cMCP policy adapter and TRACE Trust Record exporter.

Public surface:
    build_trace_record   Map a ramen-ai V5 receipt dict onto a TRACE Trust Record dict.
    RamenCmcpAdapter     Evaluate a cMCP tool-call payload via the ramen-ai API and
                         return an allow / deny decision structure.
    verify_v5_receipt    Verify Ed25519 signature + SHA-256 input binding on a V5 receipt.
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
