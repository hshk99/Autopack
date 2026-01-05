"""
Test that DEBUG_LOG.md stub sections follow the canonical stub policy.

This test ensures that all stub sections include the standard marker line,
preventing ambiguity about stub vs non-stub status.

Policy: Stubs are canonical placeholders that satisfy the INDEX/section contract.
Stubs MUST include the exact marker line defined in DEBUG_LOG.md "Stub Section Policy".
"""

import re
from pathlib import Path

# Canonical stub marker (MUST match DEBUG_LOG.md "Stub Section Policy")
STUB_MARKER = (
    "**Note**: This is a stub section generated from INDEX table entry. "
    "Full details to be added in future documentation updates."
)


def test_debug_log_stub_sections_have_standard_marker():
    """
    Guardrail: DEBUG_LOG.md stub sections must include standard marker.

    Checks:
    1. All sections that mention "stub section generated from INDEX table entry"
       MUST include the exact canonical STUB_MARKER string
    2. This prevents drift and ensures unambiguous stub vs non-stub distinction

    Policy: See docs/DEBUG_LOG.md "Stub Section Policy (Canonical Truth)" section
    """
    repo_root = Path(__file__).parents[2]
    dbg_path = repo_root / "docs" / "DEBUG_LOG.md"
    content = dbg_path.read_text(encoding="utf-8")

    # Find each DBG section block (### DBG-### headings)
    section_re = re.compile(r"^###\s+(DBG-\d+)\b", re.MULTILINE)
    starts = [m.start() for m in section_re.finditer(content)]

    # Extract section blocks (from each heading to next heading or EOF)
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(content)
        block_text = content[start:end]
        blocks.append(
            {
                "id": content[start : start + 100].split("\n")[0].strip(),  # First line (heading)
                "text": block_text,
            }
        )

    # Identify stub blocks (contain "stub section generated from INDEX table entry")
    # This is the canonical signal of a stub (case-insensitive for robustness)
    stub_signal = "stub section generated from INDEX table entry"
    stub_blocks = [b for b in blocks if stub_signal.lower() in b["text"].lower()]

    # Enforce that all stubs include the exact canonical marker
    violations = []
    for block in stub_blocks:
        if STUB_MARKER not in block["text"]:
            violations.append(block["id"])

    assert not violations, (
        "DEBUG_LOG stub sections missing canonical marker line:\n"
        + "\n".join([f"  - {bid}" for bid in violations])
        + f"\n\nExpected marker:\n  {STUB_MARKER}"
        + "\n\nFix: Ensure all stub sections include the exact marker from 'Stub Section Policy'."
        + f"\n\nStub sections are detected by presence of '{stub_signal}' in section text."
    )

    # Optional: Report stub count for visibility
    if stub_blocks:
        print(
            f"\nNote: DEBUG_LOG has {len(stub_blocks)} stub sections (all include canonical marker ✅)"
        )
