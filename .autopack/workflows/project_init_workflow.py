"""
Autopack Project Initialization Workflow

Automatically triggered when user says:
- "I want to build [PROJECT]"
- "Let's create [APPLICATION]"
- "I need to develop [TOOL]"

This workflow:
1. Creates build branch
2. Conducts market research (web + GitHub)
3. Compiles findings into reference files
4. Generates GPT strategic prompt
5. Sets up project tracking

Usage:
    This is automatically invoked by Claude when project initialization keywords are detected.
    No manual invocation needed.
"""

import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ProjectInitWorkflow:
    """Handles automated project initialization workflow"""

    def __init__(self, config_path: str = ".autopack/config/project_init_config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.project_info = {}

    def _load_config(self) -> Dict:
        """Load project initialization configuration"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def should_trigger(self, user_message: str) -> bool:
        """
        Detect if user message indicates project initialization

        Trigger phrases:
        - "I want to build [X]"
        - "Let's create [X]"
        - "I need to develop [X]"
        - "Can we build [X]"
        """
        triggers = [
            "want to build",
            "let's build",
            "let's create",
            "need to develop",
            "can we build",
            "should we build",
            "i'd like to build",
            "i want to create"
        ]

        user_lower = user_message.lower()
        return any(trigger in user_lower for trigger in triggers)

    def extract_project_info(self, user_message: str) -> Dict:
        """
        Extract project information from user message

        Returns:
            Dict with: project_name, project_type, key_features, domain, etc.
        """
        # This would use NLP or LLM to extract structured info
        # For now, placeholder that would be filled by Claude
        return {
            'project_name': '',  # To be extracted
            'project_type': '',  # desktop_app, web_app, cli_tool, etc.
            'domain': '',        # legal, personal, business, etc.
            'key_features': [],  # List of main features
            'use_case': '',      # Primary use case
            'constraints': [],   # Technical/business constraints
        }

    def generate_search_queries(self, project_info: Dict) -> List[str]:
        """
        Generate web search queries based on project info

        Uses templates from config and fills in project-specific terms
        """
        templates = self.config['project_init']['research']['web_search']['queries']

        queries = []
        for template in templates:
            query = template.format(
                project_type=project_info.get('project_type', ''),
                domain=project_info.get('domain', ''),
                key_feature=', '.join(project_info.get('key_features', [])[:2]),
                use_case=project_info.get('use_case', ''),
                keywords=' '.join(project_info.get('key_features', [])[:3]),
                technology=project_info.get('technology', 'AI')
            )
            queries.append(query)

        return queries

    def compile_market_research(self, search_results: List[Dict]) -> str:
        """
        Compile search results into structured market research document

        Args:
            search_results: List of {solution_name, url, description, pros, cons, limitations}

        Returns:
            Markdown formatted research document
        """
        template = self.config['market_research_template']

        # Format solutions
        solutions_detailed = self._format_solutions_detailed(search_results)
        matrix_table = self._format_solution_matrix(search_results)
        gaps_analysis = self._analyze_market_gaps(search_results)
        consolidation = self._identify_consolidation(search_results)
        competitive_advantages = self._identify_advantages(search_results)

        return template.format(
            project_name=self.project_info['project_name'],
            date=datetime.now().strftime('%Y-%m-%d'),
            summary=self._generate_executive_summary(search_results),
            solutions_detailed=solutions_detailed,
            matrix_table=matrix_table,
            gaps_analysis=gaps_analysis,
            consolidation_potential=consolidation,
            competitive_advantages=competitive_advantages
        )

    def _format_solutions_detailed(self, solutions: List[Dict]) -> str:
        """Format solutions into detailed sections"""
        output = []
        for i, solution in enumerate(solutions, 1):
            output.append(f"### {i}. {solution['name']}")
            output.append(f"**Type**: {solution.get('type', 'N/A')}")
            output.append(f"**Platform**: {solution.get('platform', 'N/A')}")
            output.append(f"**URL**: {solution.get('url', 'N/A')}")
            output.append("")
            output.append("**Key Features**:")
            for feature in solution.get('features', []):
                output.append(f"- {feature}")
            output.append("")
            output.append("**Pros**:")
            for pro in solution.get('pros', []):
                output.append(f"- ✅ {pro}")
            output.append("")
            output.append("**Cons**:")
            for con in solution.get('cons', []):
                output.append(f"- ❌ {con}")
            output.append("")
            output.append("**Limitations**:")
            for limitation in solution.get('limitations', []):
                output.append(f"- {limitation}")
            output.append("")
            output.append("---")
            output.append("")

        return '\n'.join(output)

    def _format_solution_matrix(self, solutions: List[Dict]) -> str:
        """Create comparison matrix table"""
        columns = self.config['project_init']['research']['solution_matrix']['columns']

        # Header
        header = "| " + " | ".join([col.replace('_', ' ').title() for col in columns]) + " |"
        separator = "|" + "|".join(["---" for _ in columns]) + "|"

        # Rows
        rows = []
        for solution in solutions:
            row = "| " + " | ".join([
                str(solution.get(col, 'N/A')) for col in columns
            ]) + " |"
            rows.append(row)

        return '\n'.join([header, separator] + rows)

    def _analyze_market_gaps(self, solutions: List[Dict]) -> str:
        """Identify market gaps based on solution analysis"""
        # This would use LLM to analyze gaps
        # Placeholder for now
        return "Market gaps to be analyzed by Claude..."

    def _identify_consolidation(self, solutions: List[Dict]) -> str:
        """Identify consolidation opportunities"""
        return "Consolidation opportunities to be analyzed by Claude..."

    def _identify_advantages(self, solutions: List[Dict]) -> str:
        """Identify competitive advantages"""
        return "Competitive advantages to be analyzed by Claude..."

    def _generate_executive_summary(self, solutions: List[Dict]) -> str:
        """Generate executive summary"""
        return f"Found {len(solutions)} existing solutions. Analysis follows..."

    def compile_user_requirements(self, user_message: str, project_info: Dict) -> str:
        """
        Compile user requirements into structured document

        Args:
            user_message: Original user message
            project_info: Extracted project information

        Returns:
            Markdown formatted requirements document
        """
        template = self.config['user_requirements_template']

        return template.format(
            project_name=project_info['project_name'],
            date=datetime.now().strftime('%Y-%m-%d'),
            core_requirements=self._format_requirements(project_info.get('requirements', [])),
            use_cases=self._format_use_cases(project_info.get('use_cases', [])),
            target_users=project_info.get('target_users', 'To be defined'),
            constraints=self._format_constraints(project_info.get('constraints', [])),
            lessons_if_applicable=project_info.get('lessons_learned', 'N/A'),
            must_have=self._format_features(project_info.get('must_have', [])),
            should_have=self._format_features(project_info.get('should_have', [])),
            nice_to_have=self._format_features(project_info.get('nice_to_have', []))
        )

    def _format_requirements(self, requirements: List[str]) -> str:
        return '\n'.join([f"{i}. {req}" for i, req in enumerate(requirements, 1)])

    def _format_use_cases(self, use_cases: List[str]) -> str:
        return '\n'.join([f"- {uc}" for uc in use_cases])

    def _format_constraints(self, constraints: List[str]) -> str:
        return '\n'.join([f"- {c}" for c in constraints])

    def _format_features(self, features: List[str]) -> str:
        return '\n'.join([f"{i}. {f}" for i, f in enumerate(features, 1)])

    def generate_gpt_prompt(self, project_info: Dict, solution_count: int) -> str:
        """
        Generate GPT strategic analysis prompt

        Args:
            project_info: Project information
            solution_count: Number of solutions found in research

        Returns:
            Markdown formatted GPT prompt
        """
        template = self.config['gpt_prompt_template']

        # Get project-type-specific analysis request
        project_type = project_info.get('project_type', 'desktop_app')
        analysis_request = self.config['analysis_requests'].get(
            project_type,
            self.config['analysis_requests']['desktop_app']
        )

        return template.format(
            project_name=project_info['project_name'],
            date=datetime.now().strftime('%Y-%m-%d'),
            project_description=project_info.get('description', ''),
            solution_count=solution_count,
            specific_analysis_request=analysis_request['request'],
            expected_outputs=analysis_request['outputs']
        )

    def create_project_structure(self, project_slug: str) -> Path:
        """
        Create project directory structure

        Args:
            project_slug: URL-friendly project name

        Returns:
            Path to project directory
        """
        output_dir = self.config['project_init']['outputs']['directory'].format(
            project_slug=project_slug
        )

        project_path = Path(output_dir)
        project_path.mkdir(parents=True, exist_ok=True)

        return project_path

    def generate_user_notification(self, project_slug: str, solution_count: int) -> str:
        """
        Generate user notification message

        Args:
            project_slug: Project slug
            solution_count: Number of solutions researched

        Returns:
            Formatted notification message
        """
        template = self.config['user_notification']

        return template.format(
            project_slug=project_slug,
            solution_count=solution_count
        )


# Workflow execution checklist for Claude:
"""
When user says "I want to build [PROJECT]":

1. ✅ Detect trigger phrase using should_trigger()
2. ✅ Extract project info from user message
3. ✅ Create build branch: git checkout -b build/{project-slug}-v1
4. ✅ Generate search queries using generate_search_queries()
5. ✅ Execute web searches (use WebSearch tool)
6. ✅ Execute GitHub searches (use WebSearch with github.com)
7. ✅ Compile market research using compile_market_research()
8. ✅ Write MARKET_RESEARCH_EXTENDED_2025.md
9. ✅ Compile user requirements using compile_user_requirements()
10. ✅ Write REF_USER_REQUIREMENTS.md
11. ✅ Generate GPT prompt using generate_gpt_prompt()
12. ✅ Write GPT_STRATEGIC_ANALYSIS_PROMPT.md
13. ✅ Create README.md in project directory
14. ✅ Display user notification using generate_user_notification()

Example Usage (for Claude):
    workflow = ProjectInitWorkflow()

    if workflow.should_trigger(user_message):
        # Extract project info
        project_info = workflow.extract_project_info(user_message)

        # Create project structure
        project_path = workflow.create_project_structure(project_info['slug'])

        # Generate search queries
        queries = workflow.generate_search_queries(project_info)

        # Execute searches (use WebSearch tool)
        search_results = []  # Populated from WebSearch

        # Compile research
        market_research = workflow.compile_market_research(search_results)
        with open(project_path / 'MARKET_RESEARCH_EXTENDED_2025.md', 'w') as f:
            f.write(market_research)

        # Compile requirements
        requirements = workflow.compile_user_requirements(user_message, project_info)
        with open(project_path / 'REF_USER_REQUIREMENTS.md', 'w') as f:
            f.write(requirements)

        # Generate GPT prompt
        gpt_prompt = workflow.generate_gpt_prompt(project_info, len(search_results))
        with open(project_path / 'GPT_STRATEGIC_ANALYSIS_PROMPT.md', 'w') as f:
            f.write(gpt_prompt)

        # Notify user
        notification = workflow.generate_user_notification(project_info['slug'], len(search_results))
        print(notification)
"""
