#!/usr/bin/env python3
"""
OpenAI Delegation Script for Complex Issue Analysis

This script delegates complex debugging and analysis tasks to OpenAI's GPT-4o API
for deep code analysis and recommendations.

Usage:
    python delegate_to_openai.py --issue "500 error on /runs/start endpoint" \
        --files "src/autopack/main.py,src/autopack/schemas.py" \
        --context "Error occurs after fixing slowapi Request import"

Environment:
    OPENAI_API_KEY: Required for API access
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timezone

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)


class OpenAIDelegationRequest:
    """Request structure for OpenAI analysis"""

    def __init__(
        self,
        issue_description: str,
        file_paths: List[str],
        context: Optional[str] = None,
        error_logs: Optional[str] = None,
        attempted_fixes: Optional[List[str]] = None
    ):
        self.issue_description = issue_description
        self.file_paths = file_paths
        self.context = context or ""
        self.error_logs = error_logs or ""
        self.attempted_fixes = attempted_fixes or []
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict:
        return {
            "issue_description": self.issue_description,
            "file_paths": self.file_paths,
            "context": self.context,
            "error_logs": self.error_logs,
            "attempted_fixes": self.attempted_fixes,
            "timestamp": self.timestamp
        }


class OpenAIDelegationResult:
    """Result structure from OpenAI analysis"""

    def __init__(
        self,
        analysis: str,
        root_cause: str,
        recommended_fixes: List[Dict],
        confidence: str,
        additional_investigation: List[str],
        raw_response: str = ""
    ):
        self.analysis = analysis
        self.root_cause = root_cause
        self.recommended_fixes = recommended_fixes
        self.confidence = confidence
        self.additional_investigation = additional_investigation
        self.raw_response = raw_response
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict:
        return {
            "analysis": self.analysis,
            "root_cause": self.root_cause,
            "recommended_fixes": self.recommended_fixes,
            "confidence": self.confidence,
            "additional_investigation": self.additional_investigation,
            "raw_response": self.raw_response,
            "timestamp": self.timestamp
        }


class OpenAIDelegator:
    """Main delegation handler using OpenAI API"""

    def __init__(self, workspace_root: Path, api_key: Optional[str] = None):
        self.workspace_root = workspace_root
        self.delegation_log_dir = workspace_root / ".autonomous_runs" / "openai_delegations"
        self.delegation_log_dir.mkdir(parents=True, exist_ok=True)

        # Initialize OpenAI client
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable or --api-key required")

        self.client = OpenAI(api_key=self.api_key)

    def delegate(self, request: OpenAIDelegationRequest) -> OpenAIDelegationResult:
        """
        Delegate complex issue analysis to OpenAI GPT-4o.

        Steps:
        1. Read file contents
        2. Format comprehensive analysis prompt
        3. Call OpenAI API
        4. Parse structured response
        5. Save results
        """
        print("[OpenAI Delegation] Starting analysis...")
        print(f"[OpenAI Delegation] Issue: {request.issue_description}")
        print(f"[OpenAI Delegation] Files: {', '.join(request.file_paths)}")

        # Read file contents
        file_contents = {}
        for file_path in request.file_paths:
            full_path = self.workspace_root / file_path
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    file_contents[file_path] = f.read()
                print(f"[OpenAI Delegation] [OK] Read {file_path} ({len(file_contents[file_path])} chars)")
            else:
                print(f"[OpenAI Delegation] [WARN] File not found: {file_path}")

        if not file_contents:
            raise ValueError("No files found to analyze")

        # Create delegation request document
        delegation_doc = self._create_delegation_document(request, file_contents)

        # Save delegation request
        request_file = self._save_delegation_request(delegation_doc, request)
        print(f"[OpenAI Delegation] Request saved: {request_file}")

        # Call OpenAI API
        print("[OpenAI Delegation] Calling OpenAI GPT-4o API...")
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert code debugger and analyzer specializing in Python, FastAPI, SQLAlchemy, and API development.

Your task is to analyze complex issues and provide:
1. Deep technical analysis of what's happening
2. Root cause identification with specific file/line references
3. Prioritized, actionable fixes with exact code changes
4. Additional investigation suggestions
5. Confidence level (high/medium/low)

Be precise, specific, and provide code examples where applicable."""
                    },
                    {
                        "role": "user",
                        "content": delegation_doc
                    }
                ],
                temperature=0.2,  # Lower temperature for more focused debugging
                max_tokens=4000
            )

            raw_response = response.choices[0].message.content
            print(f"[OpenAI Delegation] [OK] Received response ({len(raw_response)} chars)")

            # Parse response into structured result
            result = self._parse_openai_response(raw_response, request)

        except Exception as e:
            print(f"[OpenAI Delegation] [ERROR] API call failed: {e}")
            # Return error result
            result = OpenAIDelegationResult(
                analysis=f"API call failed: {str(e)}",
                root_cause="Unable to analyze due to API error",
                recommended_fixes=[],
                confidence="n/a",
                additional_investigation=["Retry with valid API key", "Check network connectivity"],
                raw_response=""
            )

        # Save result
        result_file = self._save_delegation_result(result)
        print(f"[OpenAI Delegation] Result saved: {result_file}")

        print(f"\n{'='*80}")
        print("OPENAI DELEGATION COMPLETE")
        print(f"{'='*80}")
        print(f"\nRequest File: {request_file}")
        print(f"Result File: {result_file}")
        print(f"\n{'='*80}")
        print("ANALYSIS SUMMARY")
        print(f"{'='*80}")
        print(f"\nRoot Cause:\n{result.root_cause}\n")
        print(f"Confidence: {result.confidence}\n")
        if result.recommended_fixes:
            print(f"Recommended Fixes ({len(result.recommended_fixes)}):")
            for i, fix in enumerate(result.recommended_fixes, 1):
                print(f"  {i}. {fix.get('description', 'N/A')}")
        print(f"\n{'='*80}")

        return result

    def _create_delegation_document(
        self,
        request: OpenAIDelegationRequest,
        file_contents: Dict[str, str]
    ) -> str:
        """Create a comprehensive delegation document for OpenAI"""

        doc = f"""# Issue Analysis Request

## Issue Description
{request.issue_description}

## Context
{request.context}

## Error Logs
```
{request.error_logs}
```

## Attempted Fixes
"""
        for i, fix in enumerate(request.attempted_fixes, 1):
            doc += f"{i}. {fix}\n"

        doc += "\n## File Contents\n\n"

        for file_path, content in file_contents.items():
            doc += f"### {file_path}\n```python\n{content}\n```\n\n"

        doc += """
## Analysis Request

Please provide a comprehensive analysis with:

1. **Technical Analysis**: What is happening in the code? Walk through the execution flow that leads to the error.

2. **Root Cause**: What is the exact technical reason for this issue? Be specific about:
   - The exact line/function causing the problem
   - The underlying framework/library behavior
   - Why previous fixes didn't work

3. **Recommended Fixes**: Provide prioritized, actionable fixes. For each fix:
   - Priority level (1 = highest)
   - Description of what to change
   - File path and specific location
   - Exact code changes (before/after)
   - Rationale for why this will work

4. **Additional Investigation**: What else should be investigated or checked?

5. **Confidence Level**: How confident are you in this analysis? (high/medium/low)

Format your response clearly with these sections.
"""

        return doc

    def _parse_openai_response(
        self,
        raw_response: str,
        request: OpenAIDelegationRequest
    ) -> OpenAIDelegationResult:
        """Parse OpenAI's response into structured result"""

        # Simple parsing - extract sections
        # In production, could use more sophisticated parsing or ask OpenAI for JSON format

        lines = raw_response.split('\n')

        # Extract sections (simple heuristic-based parsing)
        analysis = ""
        root_cause = ""
        recommended_fixes = []
        additional_investigation = []
        confidence = "medium"

        current_section = None
        current_fix = None

        for line in lines:
            line_lower = line.lower()

            # Detect sections
            if "root cause" in line_lower or "cause:" in line_lower:
                current_section = "root_cause"
                continue
            elif "recommended fix" in line_lower or "fixes:" in line_lower or "solution" in line_lower:
                current_section = "fixes"
                continue
            elif "additional investigation" in line_lower or "investigate:" in line_lower:
                current_section = "investigation"
                continue
            elif "confidence" in line_lower:
                current_section = "confidence"
                # Extract confidence level
                if "high" in line_lower:
                    confidence = "high"
                elif "low" in line_lower:
                    confidence = "low"
                else:
                    confidence = "medium"
                continue

            # Append to appropriate section
            if current_section == "root_cause":
                root_cause += line + "\n"
            elif current_section == "fixes":
                # Simple fix parsing - look for numbered items or bullet points
                if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "-", "*")):
                    if current_fix:
                        recommended_fixes.append(current_fix)
                    current_fix = {
                        "priority": len(recommended_fixes) + 1,
                        "description": line.strip(),
                        "file": "See analysis",
                        "changes": "",
                        "rationale": ""
                    }
                elif current_fix and line.strip():
                    current_fix["description"] += " " + line.strip()
            elif current_section == "investigation":
                if line.strip().startswith(("-", "*", "1.", "2.", "3.")):
                    additional_investigation.append(line.strip().lstrip("-*123. "))

        # Add last fix if exists
        if current_fix:
            recommended_fixes.append(current_fix)

        # If parsing failed, use raw response as analysis
        if not root_cause:
            analysis = raw_response
            root_cause = "See analysis section"

        # Clean up root cause
        root_cause = root_cause.strip()

        return OpenAIDelegationResult(
            analysis=raw_response,  # Full response as analysis
            root_cause=root_cause,
            recommended_fixes=recommended_fixes if recommended_fixes else [
                {
                    "priority": 1,
                    "description": "See full analysis for recommendations",
                    "file": "Multiple files",
                    "changes": "",
                    "rationale": "Detailed in analysis"
                }
            ],
            confidence=confidence,
            additional_investigation=additional_investigation if additional_investigation else [
                "Review full analysis for investigation steps"
            ],
            raw_response=raw_response
        )

    def _save_delegation_request(self, delegation_doc: str, request: OpenAIDelegationRequest) -> Path:
        """Save delegation request to file"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"OPENAI_DELEGATION_REQUEST_{timestamp}.md"
        filepath = self.delegation_log_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(delegation_doc)

        # Also save JSON
        json_filename = f"OPENAI_DELEGATION_REQUEST_{timestamp}.json"
        json_filepath = self.delegation_log_dir / json_filename

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(request.to_dict(), f, indent=2)

        return filepath

    def _save_delegation_result(self, result: OpenAIDelegationResult) -> Path:
        """Save delegation result to file"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"OPENAI_DELEGATION_RESULT_{timestamp}.md"
        filepath = self.delegation_log_dir / filename

        # Create markdown result
        doc = f"""# OpenAI Delegation Result
Generated: {result.timestamp}

## Full Analysis

{result.raw_response}

## Root Cause

{result.root_cause}

## Recommended Fixes

"""
        for fix in result.recommended_fixes:
            doc += f"""
### Fix {fix.get('priority', 'N/A')}

**Description**: {fix.get('description', '')}

**File**: `{fix.get('file', '')}`

**Changes**:
```python
{fix.get('changes', '')}
```

**Rationale**: {fix.get('rationale', '')}

---
"""

        doc += """
## Additional Investigation

"""
        for item in result.additional_investigation:
            doc += f"- {item}\n"

        doc += f"""
## Confidence Level

{result.confidence}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(doc)

        # Also save as JSON
        json_filename = f"OPENAI_DELEGATION_RESULT_{timestamp}.json"
        json_filepath = self.delegation_log_dir / json_filename

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, indent=2)

        return filepath


def main():
    parser = argparse.ArgumentParser(
        description="Delegate complex issues to OpenAI GPT-4o for analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delegate a 500 error investigation
  python delegate_to_openai.py \\
    --issue "500 Internal Server Error on /runs/start endpoint" \\
    --files "src/autopack/main.py,src/autopack/schemas.py" \\
    --context "Error persists after fixing slowapi Request import" \\
    --logs "No traceback in logs despite server running"

  # Delegate a complex bug
  python delegate_to_openai.py \\
    --issue "Database deadlock during concurrent phase execution" \\
    --files "src/autopack/models.py,src/autopack/main.py" \\
    --context "Occurs when multiple phases access same tier" \\
    --attempted-fixes "Added transaction isolation" "Added connection pooling"

Environment:
  OPENAI_API_KEY    OpenAI API key (required)
"""
    )

    parser.add_argument(
        '--issue',
        required=True,
        help='Brief description of the issue'
    )

    parser.add_argument(
        '--files',
        required=True,
        help='Comma-separated list of relevant file paths (relative to workspace root)'
    )

    parser.add_argument(
        '--context',
        default='',
        help='Additional context about the issue'
    )

    parser.add_argument(
        '--logs',
        default='',
        help='Error logs or output related to the issue'
    )

    parser.add_argument(
        '--attempted-fixes',
        nargs='*',
        default=[],
        help='List of fixes that were already attempted'
    )

    parser.add_argument(
        '--workspace',
        default='.',
        help='Workspace root directory (default: current directory)'
    )

    parser.add_argument(
        '--api-key',
        default=None,
        help='OpenAI API key (default: $OPENAI_API_KEY)'
    )

    args = parser.parse_args()

    # Parse file paths
    file_paths = [f.strip() for f in args.files.split(',')]

    # Create workspace root path
    workspace_root = Path(args.workspace).resolve()

    # Create delegation request
    request = OpenAIDelegationRequest(
        issue_description=args.issue,
        file_paths=file_paths,
        context=args.context,
        error_logs=args.logs,
        attempted_fixes=args.attempted_fixes
    )

    # Delegate to OpenAI
    try:
        delegator = OpenAIDelegator(workspace_root, api_key=args.api_key)
        result = delegator.delegate(request)

        print("\n[SUCCESS] OpenAI delegation completed successfully")
        return 0

    except ValueError as e:
        print(f"\n[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
