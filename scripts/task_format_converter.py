#!/usr/bin/env python3
"""
Autopack Task Format Converter

Automatically converts narrative/unstructured task descriptions into
the structured Autopack task format.

This utility detects if a markdown file is already in Autopack format,
and if not, intelligently converts it using pattern matching and heuristics.
"""

import re
from typing import List
from pathlib import Path


class TaskFormatConverter:
    """Converts narrative task descriptions to Autopack format"""

    @staticmethod
    def is_autopack_format(content: str) -> bool:
        """
        Check if content is already in Autopack format.

        Looks for the presence of structured task headers with required fields.
        """
        # Check for the structured format pattern
        pattern = r'###\s+Task\s+\d+:.*?\n\*\*Phase ID\*\*:\s+`[^`]+`.*?\*\*Category\*\*:.*?\*\*Complexity\*\*:'

        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # If we find at least one properly formatted task, consider it Autopack format
        return len(matches) > 0

    @staticmethod
    def extract_project_slug(file_path: Path) -> str:
        """Extract project slug from file path for generating Phase IDs"""
        # Try to get from parent directory name
        # e.g., /path/to/.autonomous_runs/my-project-v1/FUTURE_PLAN.md
        parent = file_path.parent.name

        # Remove version suffix for cleaner phase IDs
        slug = re.sub(r'-v\d+$', '', parent)

        # Fallback
        if not slug or slug == '.autonomous_runs':
            slug = "project"

        return slug

    @staticmethod
    def infer_complexity(text: str) -> str:
        """
        Infer task complexity from text content.

        Uses keyword matching and heuristics:
        - LOW: "fix", "update", "simple", "quick", small token estimates
        - MEDIUM: "add", "create", "implement", medium token estimates
        - HIGH: "design", "architecture", "complex", "migration", large token estimates
        """
        text_lower = text.lower()

        # HIGH complexity indicators
        high_indicators = [
            'architecture', 'migration', 'authentication', 'security',
            'complex', 'multi-user', 'refactor', 'redesign'
        ]

        # LOW complexity indicators
        low_indicators = [
            'fix', 'update', 'simple', 'quick', 'small', 'minor',
            'bugfix', 'typo', 'dependency', 'version'
        ]

        # Check token estimates if present
        token_match = re.search(r'(\d+)k?\s+tokens?', text_lower)
        if token_match:
            tokens = int(token_match.group(1))
            if tokens > 15000:
                return "high"
            elif tokens < 8000:
                return "low"

        # Check text indicators
        for indicator in high_indicators:
            if indicator in text_lower:
                return "high"

        for indicator in low_indicators:
            if indicator in text_lower:
                return "low"

        # Default to medium
        return "medium"

    @staticmethod
    def infer_category(text: str, title: str) -> str:
        """
        Infer task category from text and title.

        Categories: backend, frontend, database, api, testing, docs, deployment
        """
        combined = (title + " " + text).lower()

        # Category keyword mapping
        category_keywords = {
            'backend': ['backend', 'api', 'server', 'service', 'endpoint', 'python', 'fastapi'],
            'frontend': ['frontend', 'ui', 'react', 'component', 'electron', 'npm', 'css', 'html'],
            'database': ['database', 'sql', 'migration', 'schema', 'query', 'index'],
            'api': ['api', 'rest', 'endpoint', 'request', 'response'],
            'testing': ['test', 'testing', 'pytest', 'unit test', 'integration', 'e2e'],
            'docs': ['documentation', 'readme', 'guide', 'docs', 'markdown'],
            'deployment': ['docker', 'deploy', 'container', 'compose', 'production'],
        }

        # Count matches for each category
        scores = {}
        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined)
            if score > 0:
                scores[category] = score

        # Return category with highest score
        if scores:
            return max(scores, key=scores.get)

        # Default to backend
        return "backend"

    def convert_to_autopack_format(self, content: str, file_path: Path) -> str:
        """
        Convert narrative format to Autopack format.

        Detects numbered sections, extracts information, and converts
        to structured format with Phase ID, Category, Complexity, etc.
        """
        # Extract project slug for Phase IDs
        project_slug = self.extract_project_slug(file_path)

        # Pattern to match numbered task sections
        # Matches: ### 1. Task Name, ### Task 1: Name, ## 1. Name, etc.
        section_pattern = r'###?\s+(?:Task\s+)?(\d+)[.:]\s+([^\n]+)(.*?)(?=###?\s+(?:Task\s+)?\d+[.:]|$)'

        matches = re.finditer(section_pattern, content, re.DOTALL | re.MULTILINE)

        tasks = []
        task_number = 1

        for match in matches:
            task_num_str = match.group(1)
            task_title = match.group(2).strip()
            task_body = match.group(3).strip()

            # Remove common prefixes/suffixes from title
            task_title = re.sub(r'\(.*?\)$', '', task_title).strip()
            task_title = re.sub(r'\s*[-–]\s*.*$', '', task_title).strip()

            # Extract description (first paragraph or specific markers)
            description_match = re.search(
                r'\*\*(?:What Autopack Would Do|Description|Overview)\*\*:?\s*(.*?)(?=\n\n|\*\*|$)',
                task_body,
                re.DOTALL
            )

            if description_match:
                description = description_match.group(1).strip()
            else:
                # Use first non-empty paragraph as description
                paragraphs = [p.strip() for p in task_body.split('\n\n') if p.strip()]
                description = paragraphs[0] if paragraphs else task_title

            # Clean description (remove code blocks, excessive whitespace)
            description = re.sub(r'```.*?```', '', description, flags=re.DOTALL)
            description = re.sub(r'\n+', ' ', description)
            description = re.sub(r'\s+', ' ', description).strip()

            # Truncate if too long
            if len(description) > 500:
                description = description[:497] + "..."

            # Extract acceptance criteria if present
            criteria_match = re.search(
                r'\*\*(?:Deliverables|Acceptance Criteria)\*\*:?\s*(.*?)(?=\n\n|\*\*|$)',
                task_body,
                re.DOTALL
            )

            criteria = []
            if criteria_match:
                criteria_text = criteria_match.group(1)
                # Extract bullet points
                criteria = re.findall(r'[-•✅]\s+(.+?)(?=\n|$)', criteria_text)

            # If no criteria found, create generic ones
            if not criteria:
                criteria = [
                    "Implementation complete",
                    "Tests passing",
                    "Documentation updated"
                ]

            # Infer metadata
            complexity = self.infer_complexity(task_title + " " + task_body)
            category = self.infer_category(task_body, task_title)

            # Generate Phase ID
            phase_id = f"{project_slug}-task{task_number}"

            # Detect dependencies (simple heuristic)
            dependencies = "None"
            if re.search(r'depend|require|after|first', task_body, re.IGNORECASE):
                if task_number > 1:
                    dependencies = f"`{project_slug}-task{task_number - 1}`"

            # Build structured task
            task_md = f"""### Task {task_number}: {task_title}
**Phase ID**: `{phase_id}`
**Category**: {category}
**Complexity**: {complexity}
**Description**: {description}

**Acceptance Criteria**:
"""

            for criterion in criteria[:5]:  # Limit to 5 criteria
                # Clean criterion
                criterion = criterion.strip()
                if criterion.startswith('✅'):
                    criterion = criterion[1:].strip()
                task_md += f"- [ ] {criterion}\n"

            task_md += f"\n**Dependencies**: {dependencies}\n\n---\n"

            tasks.append(task_md)
            task_number += 1

        # If no tasks found, try alternative pattern (numbered lists)
        if not tasks:
            tasks = self._convert_simple_list_format(content, project_slug)

        # Build final document
        if tasks:
            # Preserve header if present
            header_match = re.match(r'^(#[^#].*?)(?=###)', content, re.DOTALL)
            header = header_match.group(1).strip() if header_match else f"# {project_slug.title()} - Tasks"

            converted = f"{header}\n\n**Auto-converted to Autopack format**\n\n---\n\n## Tasks\n\n"
            converted += "\n".join(tasks)

            return converted
        else:
            # Unable to convert - return error message
            raise ValueError(
                "Unable to auto-convert task file to Autopack format.\n"
                "No recognizable task sections found.\n"
                "Please manually format the file or provide tasks in a numbered list."
            )

    def _convert_simple_list_format(self, content: str, project_slug: str) -> List[str]:
        """Convert simple numbered list format (fallback)"""
        # Pattern: 1. Task name
        #          Description...
        pattern = r'^\s*(\d+)\.\s+(.+?)(?=^\s*\d+\.|$)'

        matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)

        tasks = []
        for match in matches:
            task_num = int(match.group(1))
            task_content = match.group(2).strip()

            # First line is title, rest is description
            lines = task_content.split('\n', 1)
            title = lines[0].strip()
            description = lines[1].strip() if len(lines) > 1 else title

            # Truncate description
            if len(description) > 300:
                description = description[:297] + "..."

            complexity = self.infer_complexity(task_content)
            category = self.infer_category(task_content, title)
            phase_id = f"{project_slug}-task{task_num}"

            task_md = f"""### Task {task_num}: {title}
**Phase ID**: `{phase_id}`
**Category**: {category}
**Complexity**: {complexity}
**Description**: {description}

**Acceptance Criteria**:
- [ ] Implementation complete
- [ ] Tests passing

**Dependencies**: None

---
"""
            tasks.append(task_md)

        return tasks

    def convert_file(self, input_path: Path, output_path: Path = None, backup: bool = True) -> Path:
        """
        Convert a task file to Autopack format.

        Args:
            input_path: Path to input markdown file
            output_path: Path for converted file (default: overwrites input with .backup)
            backup: Whether to create a backup of original file

        Returns:
            Path to converted file
        """
        # Read input file
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if already in Autopack format
        if self.is_autopack_format(content):
            print(f"[INFO] File is already in Autopack format: {input_path}")
            return input_path

        print(f"[INFO] Converting {input_path} to Autopack format...")

        # Convert
        converted = self.convert_to_autopack_format(content, input_path)

        # Create backup if requested
        if backup:
            backup_path = input_path.with_suffix('.md.backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[INFO] Backup created: {backup_path}")

        # Determine output path
        if output_path is None:
            output_path = input_path

        # Write converted file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(converted)

        print(f"[INFO] Converted file written: {output_path}")

        return output_path


def main():
    """CLI entry point for standalone usage"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert narrative task files to Autopack format"
    )
    parser.add_argument('input_file', help='Input markdown file')
    parser.add_argument(
        '--output',
        '-o',
        help='Output file (default: overwrites input with backup)'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup of original file'
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check if file is in Autopack format'
    )

    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output) if args.output else None

    converter = TaskFormatConverter()

    if args.check_only:
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        is_autopack = converter.is_autopack_format(content)
        print(f"File {'IS' if is_autopack else 'IS NOT'} in Autopack format")
        return 0 if is_autopack else 1

    try:
        result_path = converter.convert_file(
            input_path,
            output_path,
            backup=not args.no_backup
        )
        print(f"[SUCCESS] Conversion complete: {result_path}")
        return 0
    except Exception as e:
        print(f"[ERROR] Conversion failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
