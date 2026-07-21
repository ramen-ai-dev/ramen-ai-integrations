#!/usr/bin/env python3
"""Emit a TRACE Trust Record from a ramen-ai V5 receipt fixture.

Loads ``examples/fixtures/vector1_allowed.json``, maps the receipt onto a TRACE
Trust Record via :func:`ramen_cmcp.build_trace_record`, signs it with an
ephemeral Ed25519 key via ``agentrust_trace.sign_record``, verifies the
round-trip, and writes two files:

  <out>              Unsigned record for ``trace-tests verify``
  <out>.signed.json  Signed record, verifiable with
                     ``agentrust_trace.verify_record(..., allow_embedded_key=True)``

Requires the ``agentrust`` optional extras:
    pip install -e "plugins/cmcp-python[agentrust]"

Usage:
    python examples/emit_record.py --out trust-record.jwt
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# allow running directly from the plugin root without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import agentrust_trace
except ImportError as exc:
    sys.exit(
        "agentrust_trace is required — install with:\n"
        "  pip install -e 'plugins/cmcp-python[agentrust]'\n"
        f"Original error: {exc}"
    )

from ramen_cmcp import build_trace_record, verify_v5_receipt

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vector1_allowed.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Path for the trace-tests-gradable record")
    parser.add_argument("--fixture", default=str(FIXTURE), help="V5 receipt fixture JSON")
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    receipt: dict = fixture["receipt"]
    original_input: str = fixture["input"]

    # ── 1. verify the fixture receipt before mapping ───────────────────────
    valid, reason = verify_v5_receipt(receipt, original_input)
    if not valid:
        print(f"ERROR: fixture receipt failed verification: {reason}", file=sys.stderr)
        return 1
    print(f"Fixture receipt verified OK  (kid={receipt['kid']})")

    # ── 2. generate an ephemeral signing key for the TRACE record ──────────
    key = agentrust_trace.generate_key()
    jwk = agentrust_trace.key_to_jwk(key)

    # ── 3. build the unsigned TRACE Trust Record ───────────────────────────
    record = build_trace_record(receipt, iat=int(time.time()), jwk=jwk)
    print(f"TRACE subject: {record['subject']}")
    print(f"TRACE appraisal.status: {record['appraisal']['status']}")

    # ── 4. sign and verify the round-trip ─────────────────────────────────
    signed = agentrust_trace.sign_record(dict(record), key)
    agentrust_trace.verify_record(signed, allow_embedded_key=True)
    print("sign_record / verify_record round-trip OK")

    # ── 5. write output files ──────────────────────────────────────────────
    out = Path(args.out)
    # trace-tests 0.1.0 rejects plain records carrying a top-level `signature`
    # field (anti-downgrade), so the gradable file is the unsigned payload.
    out.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    signed_out = out.with_name(out.name + ".signed.json")
    signed_out.write_text(
        json.dumps(signed, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    print(f"Unsigned (for trace-tests): {out}")
    print(f"Signed   (verify_record OK): {signed_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
