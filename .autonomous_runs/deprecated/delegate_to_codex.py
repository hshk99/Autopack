#!/usr/bin/env python3
"""
Codex Delegation Script for Complex Issue Analysis

This script allows Cursor (Claude) to delegate complex debugging and analysis
tasks to Codex. It follows the same pattern as Autopack's Builder/Auditor delegation.

Usage:
    python delegate_to_codex.py --issue "500 error on /runs/start endpoint" \
        --files "src/autopack/main.py,src/autopack/schemas.py" \
        --context "Error occurs after fixing slowapi Request import"

Magic Word Trigger (for Cursor):
    "DELEGATE TO CODEX: [issue description]"

When Cursor sees this magic phrase, it will:
1. Extract issue description and relevant files
2. Run this script with appropriate parameters
3. Present Codex's analysis and recommendations
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class CodexDelegationRequest:
    """Request structure for Codex analysis"""

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
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            "issue_description": self.issue_description,
            "file_paths": self.file_paths,
            "context": self.context,
            "error_logs": self.error_logs,
            "attempted_fixes": self.attempted_fixes,
            "timestamp": self.timestamp
        }


class CodexDelegationResult:
    """Result structure from Codex analysis"""

    def __init__(
        self,
        analysis: str,
        root_cause: str,
        recommended_fixes: List[Dict],
        confidence: str,
        additional_investigation: List[str]
    ):
        self.analysis = analysis
        self.root_cause = root_cause
        self.recommended_fixes = recommended_fixes
        self.confidence = confidence
        self.additional_investigation = additional_investigation
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            "analysis": self.analysis,
            "root_cause": self.root_cause,
            "recommended_fixes": self.recommended_fixes,
            "confidence": self.confidence,
            "additional_investigation": self.additional_investigation,
            "timestamp": self.timestamp
        }


class CodexDelegator:
    """Main delegation handler"""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.delegation_log_dir = workspace_root / ".autonomous_runs" / "codex_delegations"
        self.delegation_log_dir.mkdir(parents=True, exist_ok=True)

    def delegate(self, request: CodexDelegationRequest) -> CodexDelegationResult:
        """
        Delegate complex issue analysis to Codex.

        In production, this would:
        1. Format the request for Codex API
        2. Invoke Codex with appropriate context
        3. Parse Codex's response
        4. Return structured result

        For now, this creates a structured analysis request file
        that Codex can process.
        """
        print(f"[Codex Delegation] Starting analysis...")
        print(f"[Codex Delegation] Issue: {request.issue_description}")
        print(f"[Codex Delegation] Files: {', '.join(request.file_paths)}")

        # Read file contents
        file_contents = {}
        for file_path in request.file_paths:
            full_path = self.workspace_root / file_path
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    file_contents[file_path] = f.read()
            else:
                print(f"[WARNING] File not found: {file_path}")

        # Create delegation request document
        delegation_doc = self._create_delegation_document(request, file_contents)

        # Save delegation request
        request_file = self._save_delegation_request(delegation_doc)
        print(f"[Codex Delegation] Request saved: {request_file}")

        # In production: Invoke Codex API here
        # For now: Return a structured template for Codex to fill
        result = self._create_codex_analysis_template(request)

        # Save result template
        result_file = self._save_delegation_result(result)
        print(f"[Codex Delegation] Result template saved: {result_file}")

        print(f"\n{'='*80}")
        print(f"CODEX DELEGATION CREATED")
        print(f"{'='*80}")
        print(f"\nRequest File: {request_file}")
        print(f"Result Template: {result_file}")
        print(f"\n{'='*80}")
        print(f"NEXT STEPS:")
        print(f"{'='*80}")
        print(f"1. Codex will analyze the request file")
        print(f"2. Codex will fill in the result template with analysis")
        print(f"3. Cursor will read the result and apply recommendations")
        print(f"\n{'='*80}")

        return result

    def _create_delegation_document(
        self,
        request: CodexDelegationRequest,
        file_contents: Dict[str, str]
    ) -> str:
        """Create a comprehensive delegation document for Codex"""

        doc = f"""# Codex Delegation Request
Generated: {request.timestamp}

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

Please provide:

1. **Root Cause Analysis**: What is causing this issue?

2. **Technical Explanation**: Explain the technical details of why this is happening.

3. **Recommended Fixes**: Provide specific, actionable fixes (prioritized).

4. **Code Examples**: Show exact code changes needed (if applicable).

5. **Additional Investigation**: What else should be investigated?

6. **Confidence Level**: How confident are you in this analysis? (high/medium/low)

## Expected Output Format

Please fill in the CODEX_DELEGATION_RESULT.md file with your analysis using the template provided.
"""

        return doc

    def _create_codex_analysis_template(self, request: CodexDelegationRequest) -> CodexDelegationResult:
        """Create a template for Codex to fill with analysis"""

        return CodexDelegationResult(
            analysis="""
[Codex will provide detailed analysis here]

This section should include:
- What the code is doing
- Where the issue is occurring
- Why the current fix didn't work
- What needs to change
""",
            root_cause="""
[Codex will identify the root cause here]

Be specific about:
- The exact line/function causing the issue
- The underlying technical reason
- Any framework/library-specific behavior
""",
            recommended_fixes=[
                {
                    "priority": 1,
                    "description": "[Codex will provide fix description]",
                    "file": "[file path]",
                    "changes": "[specific code changes]",
                    "rationale": "[why this fix works]"
                }
            ],
            confidence="[high|medium|low]",
            additional_investigation=[
                "[Codex will suggest additional things to investigate]"
            ]
        )

    def _save_delegation_request(self, delegation_doc: str) -> Path:
        """Save delegation request to file"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"CODEX_DELEGATION_REQUEST_{timestamp}.md"
        filepath = self.delegation_log_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(delegation_doc)

        return filepath

    def _save_delegation_result(self, result: CodexDelegationResult) -> Path:
        """Save delegation result template to file"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"CODEX_DELEGATION_RESULT_{timestamp}.md"
        filepath = self.delegation_log_dir / filename

        # Create markdown template
        doc = f"""# Codex Delegation Result
Generated: {result.timestamp}

## Analysis

{result.analysis}

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

        doc += f"""
## Additional Investigation

"""
        for item in result.additional_investigation:
            doc += f"- {item}\n"

        doc += f"""
## Confidence Level

{result.confidence}

---

**Codex**: Please replace the placeholder text above with your actual analysis.
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(doc)

        # Also save as JSON
        json_filename = f"CODEX_DELEGATION_RESULT_{timestamp}.json"
        json_filepath = self.delegation_log_dir / json_filename

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, indent=2)

        return filepath


def main():
    parser = argparse.ArgumentParser(
        description="Delegate complex issues to Codex for analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delegate a 500 error investigation
  python delegate_to_codex.py \\
    --issue "500 Internal Server Error on /runs/start endpoint" \\
    --files "src/autopack/main.py,src/autopack/schemas.py" \\
    --context "Error persists after fixing slowapi Request import" \\
    --logs "No traceback in logs despite server running"

  # Delegate a complex bug
  python delegate_to_codex.py \\
    --issue "Database deadlock during concurrent phase execution" \\
    --files "src/autopack/models.py,src/autopack/main.py" \\
    --context "Occurs when multiple phases access same tier" \\
    --attempted-fixes "Added transaction isolation" "Added connection pooling"

Magic Word Trigger:
  When Cursor encounters a complex issue, say:
  "DELEGATE TO CODEX: [issue description]"

  Cursor will automatically run this script with relevant context.
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

    args = parser.parse_args()

    # Parse file paths
    file_paths = [f.strip() for f in args.files.split(',')]

    # Create workspace root path
    workspace_root = Path(args.workspace).resolve()

    # Create delegation request
    request = CodexDelegationRequest(
        issue_description=args.issue,
        file_paths=file_paths,
        context=args.context,
        error_logs=args.logs,
        attempted_fixes=args.attempted_fixes
    )

    # Delegate to Codex
    delegator = CodexDelegator(workspace_root)
    result = delegator.delegate(request)

    print("\n[SUCCESS] Codex delegation created successfully")
    print("[INFO] Waiting for Codex analysis...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
