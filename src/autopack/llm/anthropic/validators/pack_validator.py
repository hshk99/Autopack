"""Pack YAML validation for Anthropic Builder responses.

Extracted from full_file_parser.py lines 314-351 as part of PR-CLIENT-3.
Validates pack YAML files for completeness and schema compliance.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PackValidator:
    """Validates pack YAML files from Builder responses.

    Responsibilities:
    1. Validate pack YAML schema (name, description, version, etc.)
    2. Check for required sections (categories, official_sources)
    3. Detect truncation in pack YAMLs
    4. File-specific validation for backend/packs/*.yaml
    """

    def validate_pack_fullfile(self, file_path: str, content: str) -> Optional[str]:
        """
        Lightweight preflight for pack YAMLs in full-file mode.
        Reject obviously incomplete/truncated outputs before diff generation so the Builder can retry.

        Args:
            file_path: Path to the file being validated
            content: File content to validate

        Returns:
            Error message if validation fails, None if validation passes
        """
        if not (file_path.endswith((".yaml", ".yml")) and "backend/packs/" in file_path):
            return None

        stripped = content.lstrip()
        if not stripped:
            return f"pack_fullfile_empty: {file_path} returned empty content"

        # YAML allows comments (#) before document marker (---) or keys
        # The --- document marker is optional in YAML, so we don't enforce it
        lines = stripped.split("\n")

        # Check that required top-level keys appear in the first ~50 lines
        # This catches patches that only include partial content
        first_lines = "\n".join(lines[:50])
        required_top_level = ["name:", "description:", "version:", "country:", "domain:"]
        missing_top = [k for k in required_top_level if k not in first_lines]
        if missing_top:
            return (
                f"pack_fullfile_incomplete_header: {file_path} is missing top-level keys in header: {', '.join(missing_top)}. "
                f"First 200 chars: {stripped[:200]}... "
                "You must emit the COMPLETE YAML file with ALL top-level keys, not a patch."
            )

        # Check that required sections appear somewhere in the file
        required_sections = ["categories:", "official_sources:"]
        missing_sections = [s for s in required_sections if s not in content]
        if missing_sections:
            return (
                f"pack_fullfile_missing_sections: {file_path} missing required sections: {', '.join(missing_sections)}. "
                "You must emit the COMPLETE YAML file with all required sections."
            )

        return None
