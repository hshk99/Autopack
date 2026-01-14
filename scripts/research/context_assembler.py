"""
Universal Context Assembler

Assembles comprehensive project context from SOT files and research.
Works for any project (Autopack, file-organizer, or future projects).
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import anthropic

from scripts.research.data_structures import ProjectContext, ResearchType


class ContextAssembler:
    """
    Assembles comprehensive project context for strategic decision-making.

    Context includes:
    - Current state (from SOT files via PostgreSQL)
    - Vision & strategy (from product vision research)
    - Market context (from market research)
    - Domain requirements (from domain research)
    - Technical constraints (from architecture decisions)
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.db_url = os.getenv("DATABASE_URL")
        self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def _extract_json_from_response(self, text: str) -> dict:
        """Extract JSON from LLM response that may have extra text"""
        # Try direct JSON parse first
        try:
            return json.loads(text)
        except:
            pass

        # Look for JSON object in the text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass

        # Look for JSON array in the text
        array_match = re.search(r"\[.*\]", text, re.DOTALL)
        if array_match:
            try:
                return json.loads(array_match.group())
            except:
                pass

        raise ValueError("Could not extract JSON from response")

    def assemble(self) -> ProjectContext:
        """Assemble complete project context"""
        print(f"\n{'=' * 60}")
        print(f"ASSEMBLING CONTEXT: {self.project_id}")
        print(f"{'=' * 60}\n")

        context = ProjectContext(project_id=self.project_id)

        # Phase 1: Extract current state from SOT files
        print("Phase 1: Extracting current state from SOT files...")
        context.implemented_features = self._extract_implemented_features()
        context.architecture_constraints = self._extract_architecture_constraints()
        context.known_issues = self._extract_known_issues()
        context.planned_features = self._extract_planned_features()
        context.learned_rules = self._extract_learned_rules()
        context.tech_stack = self._extract_tech_stack()

        # Phase 2: Extract vision & strategy from research
        print("\nPhase 2: Extracting vision & strategy from research...")
        self._extract_product_vision(context)

        # Phase 3: Extract market context from research
        print("\nPhase 3: Extracting market context from research...")
        self._extract_market_context(context)

        # Phase 4: Extract domain requirements from research
        print("\nPhase 4: Extracting domain requirements from research...")
        self._extract_domain_context(context)

        print(f"\n{'=' * 60}")
        print("CONTEXT ASSEMBLY COMPLETE")
        print(f"{'=' * 60}\n")
        self._print_summary(context)

        return context

    def _extract_implemented_features(self) -> List[Dict]:
        """Extract implemented features from BUILD_HISTORY"""
        if not self.db_url:
            print("  ⚠️  PostgreSQL not available, reading from file...")
            return self._extract_from_build_history_file()

        try:
            conn = psycopg2.connect(self.db_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                """
                SELECT title, content, metadata
                FROM sot_entries
                WHERE project_id = %s AND file_type = 'BUILD_HISTORY'
                ORDER BY created_at DESC
                LIMIT 100
            """,
                (self.project_id,),
            )

            entries = cursor.fetchall()
            cursor.close()
            conn.close()

            features = []
            for entry in entries:
                if entry["metadata"] and entry["metadata"].get("status") == "implemented":
                    features.append(
                        {
                            "title": entry["title"],
                            "description": entry["content"][:200],
                            "category": entry["metadata"].get("category", "unknown"),
                        }
                    )

            print(f"  ✓ Extracted {len(features)} implemented features")
            return features

        except Exception as e:
            print(f"  ⚠️  Database error: {e}")
            return self._extract_from_build_history_file()

    def _extract_from_build_history_file(self) -> List[Dict]:
        """Fallback: Extract from BUILD_HISTORY.md file"""
        build_history_path = self._get_sot_file_path("BUILD_HISTORY.md")
        if not build_history_path.exists():
            return []

        features = []
        content = build_history_path.read_text(encoding="utf-8")

        # Simple extraction: Look for "## " headings (build entries)
        for line in content.split("\n"):
            if line.startswith("## ") and "BUILD:" in line:
                title = line.replace("## ", "").strip()
                features.append({"title": title, "description": "", "category": "build"})

        print(f"  ✓ Extracted {len(features)} build entries from file")
        return features

    def _extract_architecture_constraints(self) -> List[Dict]:
        """Extract architecture decisions/constraints"""
        arch_path = self._get_sot_file_path("ARCHITECTURE_DECISIONS.md")
        if not arch_path.exists():
            return []

        constraints = []
        content = arch_path.read_text(encoding="utf-8")

        # Extract decision headings
        for line in content.split("\n"):
            if line.startswith("## ") and "DECISION:" in line:
                title = line.replace("## ", "").strip()
                constraints.append({"title": title, "type": "architecture_decision"})

        print(f"  ✓ Extracted {len(constraints)} architecture constraints")
        return constraints

    def _extract_known_issues(self) -> List[Dict]:
        """Extract known issues from DEBUG_LOG"""
        debug_path = self._get_sot_file_path("DEBUG_LOG.md")
        if not debug_path.exists():
            return []

        issues = []
        content = debug_path.read_text(encoding="utf-8")

        # Extract debug session headings
        for line in content.split("\n"):
            if line.startswith("## ") and "DEBUG:" in line:
                title = line.replace("## ", "").strip()
                issues.append({"title": title, "type": "debug_session"})

        print(f"  ✓ Extracted {len(issues)} known issues")
        return issues

    def _extract_planned_features(self) -> List[Dict]:
        """Extract planned features from FUTURE_PLAN"""
        future_path = self._get_sot_file_path("FUTURE_PLAN.md")
        if not future_path.exists():
            return []

        features = []
        content = future_path.read_text(encoding="utf-8")

        # Extract feature headings
        for line in content.split("\n"):
            if line.startswith("## "):
                title = line.replace("## ", "").strip()
                features.append({"title": title, "status": "planned"})

        print(f"  ✓ Extracted {len(features)} planned features")
        return features

    def _extract_learned_rules(self) -> List[Dict]:
        """Extract learned rules from LEARNED_RULES.json"""
        rules_path = self._get_sot_file_path("LEARNED_RULES.json")
        if not rules_path.exists():
            return []

        try:
            data = json.loads(rules_path.read_text(encoding="utf-8"))
            rules = data.get("rules", [])
            print(f"  ✓ Extracted {len(rules)} learned rules")
            return rules
        except Exception as e:
            print(f"  ⚠️  Error reading LEARNED_RULES.json: {e}")
            return []

    def _extract_tech_stack(self) -> List[str]:
        """Extract tech stack from architecture decisions"""
        # This is project-agnostic - extracts technologies mentioned in decisions
        arch_path = self._get_sot_file_path("ARCHITECTURE_DECISIONS.md")
        if not arch_path.exists():
            return []

        content = arch_path.read_text(encoding="utf-8")

        # Common tech keywords to look for
        tech_keywords = [
            "Python",
            "JavaScript",
            "TypeScript",
            "React",
            "Vue",
            "Angular",
            "PostgreSQL",
            "MySQL",
            "MongoDB",
            "Redis",
            "Qdrant",
            "FastAPI",
            "Flask",
            "Django",
            "Express",
            "Node.js",
            "Docker",
            "Kubernetes",
            "AWS",
            "GCP",
            "Azure",
            "Electron",
            "Tauri",
            "SQLite",
        ]

        found_tech = []
        for tech in tech_keywords:
            if tech in content:
                found_tech.append(tech)

        print(f"  ✓ Identified {len(found_tech)} technologies")
        return found_tech

    def _extract_product_vision(self, context: ProjectContext):
        """Extract product vision from research files using LLM"""
        research_dir = self._get_research_dir()
        if not research_dir.exists():
            print("  ⚠️  No research directory found")
            return

        # Look for product vision files
        vision_files = []
        for file in research_dir.rglob("*.md"):
            filename_lower = file.name.lower()
            if any(kw in filename_lower for kw in ["vision", "product", "intent", "strategy"]):
                vision_files.append(file)

        if not vision_files:
            print("  ⚠️  No product vision files found")
            return

        # Read first vision file and extract with LLM
        vision_file = vision_files[0]
        content = vision_file.read_text(encoding="utf-8")[:10000]  # First 10k chars

        prompt = f"""Extract the following from this product vision document:

1. Vision statement (1-2 sentences)
2. Target users (list)
3. Core design principles (list)
4. Market positioning (1 sentence)

Document:
{content}

Return JSON:
{{
  "vision_statement": "...",
  "target_users": ["...", "..."],
  "core_principles": ["...", "..."],
  "positioning": "..."
}}"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._extract_json_from_response(response.content[0].text)
            context.vision_statement = result.get("vision_statement")
            context.target_users = result.get("target_users", [])
            context.core_principles = result.get("core_principles", [])
            context.positioning = result.get("positioning")

            print(f"  ✓ Extracted vision from {vision_file.name}")
        except Exception as e:
            print(f"  ⚠️  Error extracting vision: {e}")

    def _extract_market_context(self, context: ProjectContext):
        """Extract market context from market research files"""
        research_dir = self._get_research_dir()
        if not research_dir.exists():
            return

        # Look for market research files
        market_files = []
        for file in research_dir.rglob("*.md"):
            filename_lower = file.name.lower()
            if any(kw in filename_lower for kw in ["market", "competitive", "competitor"]):
                market_files.append(file)

        if not market_files:
            print("  ⚠️  No market research files found")
            return

        # Read first market file and extract with LLM
        market_file = market_files[0]
        content = market_file.read_text(encoding="utf-8")[:10000]

        prompt = f"""Extract the following from this market research document:

1. Key competitors (list of names)
2. Competitive gaps (features competitors have that we should consider)
3. Competitive advantages (what makes this product unique)
4. Market opportunities (gaps in the market)

Document:
{content}

Return JSON:
{{
  "key_competitors": ["...", "..."],
  "competitive_gaps": ["...", "..."],
  "competitive_advantages": ["...", "..."],
  "market_opportunities": ["...", "..."]
}}"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._extract_json_from_response(response.content[0].text)
            context.key_competitors = result.get("key_competitors", [])
            context.competitive_gaps = result.get("competitive_gaps", [])
            context.competitive_advantages = result.get("competitive_advantages", [])
            context.market_opportunities = result.get("market_opportunities", [])

            print(f"  ✓ Extracted market context from {market_file.name}")
        except Exception as e:
            print(f"  ⚠️  Error extracting market context: {e}")

    def _extract_domain_context(self, context: ProjectContext):
        """Extract domain requirements from domain research files"""
        research_dir = self._get_research_dir()
        if not research_dir.exists():
            return

        # Look for domain requirement files
        domain_files = []
        for file in research_dir.rglob("*.md"):
            filename_lower = file.name.lower()
            if any(
                kw in filename_lower
                for kw in ["domain", "requirement", "legal", "tax", "compliance"]
            ):
                domain_files.append(file)

        if not domain_files:
            print("  ⚠️  No domain requirement files found")
            return

        # Combine all domain files (they're usually shorter)
        combined_content = ""
        for file in domain_files[:3]:  # Max 3 files
            combined_content += f"\n\n=== {file.name} ===\n"
            combined_content += file.read_text(encoding="utf-8")[:5000]

        prompt = f"""Extract the following from these domain requirement documents:

1. Domain focus areas (e.g., tax, legal, finance, immigration)
2. Regulatory/compliance requirements
3. User pain points in this domain

Documents:
{combined_content}

Return JSON:
{{
  "domain_focus": ["...", "..."],
  "regulatory_requirements": ["...", "..."],
  "user_pain_points": ["...", "..."]
}}"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._extract_json_from_response(response.content[0].text)
            context.domain_focus = result.get("domain_focus", [])
            context.regulatory_requirements = result.get("regulatory_requirements", [])
            context.user_pain_points = result.get("user_pain_points", [])

            print(f"  ✓ Extracted domain context from {len(domain_files)} files")
        except Exception as e:
            print(f"  ⚠️  Error extracting domain context: {e}")

    def _get_sot_file_path(self, filename: str) -> Path:
        """Get path to SOT file (universal for any project)"""
        if self.project_id == "autopack":
            return Path("docs") / filename
        else:
            return Path(".autonomous_runs") / self.project_id / "docs" / filename

    def _get_research_dir(self) -> Path:
        """Get research directory (universal for any project)"""
        if self.project_id == "autopack":
            return Path("archive") / "research"
        else:
            return Path(".autonomous_runs") / self.project_id / "archive" / "research"

    def _print_summary(self, context: ProjectContext):
        """Print summary of assembled context"""
        print("Summary:")
        print(f"  • Implemented features: {len(context.implemented_features)}")
        print(f"  • Architecture constraints: {len(context.architecture_constraints)}")
        print(f"  • Known issues: {len(context.known_issues)}")
        print(f"  • Planned features: {len(context.planned_features)}")
        print(f"  • Learned rules: {len(context.learned_rules)}")
        print(f"  • Tech stack: {len(context.tech_stack)}")
        print(f"  • Target users: {len(context.target_users)}")
        print(f"  • Core principles: {len(context.core_principles)}")
        print(f"  • Key competitors: {len(context.key_competitors)}")
        print(f"  • Domain focus: {len(context.domain_focus)}")

        if context.vision_statement:
            print(f"\nVision: {context.vision_statement[:100]}...")


if __name__ == "__main__":
    import sys

    project_id = sys.argv[1] if len(sys.argv) > 1 else "file-organizer-app-v1"

    assembler = ContextAssembler(project_id)
    context = assembler.assemble()

    # Save to JSON
    output_path = Path(f".autonomous_runs/{project_id}/context.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(context.to_dict(), indent=2), encoding="utf-8")
    print(f"\n✓ Context saved to {output_path}")
