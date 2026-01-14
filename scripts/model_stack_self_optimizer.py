#!/usr/bin/env python3
"""Model Stack Self-Optimizer

Periodically re-evaluates model cost-effectiveness using:
1. Real Autopack run logs (tokens, costs, success/failure rates)
2. Current pricing from config/pricing.yaml
3. Frontier LLM analysis for optimization recommendations

Usage:
    python scripts/model_stack_self_optimizer.py --optimizer-model gpt-5
    python scripts/model_stack_self_optimizer.py --dry-run
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_yaml(path: str) -> dict:
    """Load YAML config file."""
    with open(path) as f:
        return yaml.safe_load(f)


def load_jsonl_logs(log_dir: str, days: int = 30) -> List[dict]:
    """Load recent JSONL log files from log directory."""
    log_path = Path(log_dir)
    if not log_path.exists():
        return []

    entries = []
    for log_file in log_path.glob("*.jsonl"):
        try:
            with open(log_file) as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        except Exception as e:
            print(f"Warning: Failed to parse {log_file}: {e}")

    return entries


def aggregate_stats(log_entries: List[dict], pricing: dict) -> dict:
    """
    Aggregate statistics from log entries.

    Returns stats grouped by (role, complexity, model).
    """
    stats = defaultdict(
        lambda: {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_cost_usd": 0.0,
            "escalation_count": 0,
            "attempts": [],
        }
    )

    for entry in log_entries:
        role = entry.get("role", "unknown")
        complexity = entry.get("effective_complexity", entry.get("original_complexity", "unknown"))
        model = entry.get("model", "unknown")

        key = (role, complexity, model)
        stats[key]["total_calls"] += 1

        # Track escalation
        escalation_info = entry.get("escalation_info", {})
        if escalation_info.get("complexity_escalation_reason"):
            stats[key]["escalation_count"] += 1

        # Track attempts
        attempt_idx = entry.get("attempt_index", 0)
        stats[key]["attempts"].append(attempt_idx)

    return dict(stats)


def get_model_price(model: str, pricing: dict) -> tuple:
    """Get (input_price, output_price) per 1K tokens for a model."""
    # Check all providers
    for provider, models in pricing.items():
        if isinstance(models, dict) and model in models:
            model_pricing = models[model]
            if isinstance(model_pricing, dict):
                return (model_pricing.get("input_per_1k", 0), model_pricing.get("output_per_1k", 0))
    return (0, 0)


def build_optimization_prompt(
    models_yaml: dict, pricing_yaml: dict, run_stats: dict, previous_report: Optional[str] = None
) -> str:
    """Build the optimization prompt for frontier LLM."""

    # Extract current model mappings
    escalation_chains = models_yaml.get("escalation_chains", {})
    complexity_models = models_yaml.get("complexity_models", {})

    prompt = f"""# Model Stack Optimization Analysis Request

## Current Date
{datetime.utcnow().strftime("%Y-%m-%d")}

## Task
Analyze the current Autopack model stack configuration and recommend optimizations to:
1. Minimize cost per successful phase
2. Maintain quality (success rate, accuracy)
3. Optimize escalation thresholds

## Current Model Configuration

### Escalation Chains (cheap -> expensive)
```yaml
{yaml.dump(escalation_chains, default_flow_style=False)}
```

### Complexity Models (baseline)
```yaml
{yaml.dump(complexity_models, default_flow_style=False)}
```

## Current Pricing (USD per 1K tokens)
```yaml
{yaml.dump(pricing_yaml, default_flow_style=False)}
```

## Run Statistics (Last 30 Days)
"""

    if run_stats:
        prompt += (
            "\n| Role | Complexity | Model | Calls | Success Rate | Avg Attempts | Est. Cost |\n"
        )
        prompt += "|------|------------|-------|-------|--------------|--------------|----------|\n"

        for (role, complexity, model), data in sorted(run_stats.items()):
            total = data["total_calls"]
            success = data["successful_calls"]
            success_rate = (success / total * 100) if total > 0 else 0
            avg_attempts = sum(data["attempts"]) / len(data["attempts"]) if data["attempts"] else 0
            est_cost = data.get("total_cost_usd", 0)

            prompt += f"| {role} | {complexity} | {model} | {total} | {success_rate:.1f}% | {avg_attempts:.1f} | ${est_cost:.4f} |\n"
    else:
        prompt += "\n*No run statistics available yet. Using default analysis.*\n"

    prompt += """

## Analysis Requirements

Please analyze the above configuration and provide:

1. **Cost Efficiency Analysis**
   - Which model assignments are over-provisioned (expensive model for simple tasks)?
   - Which are under-provisioned (cheap model failing too often)?

2. **Escalation Chain Recommendations**
   - Are the current escalation chains optimal?
   - Should any models be added, removed, or reordered?
   - Are the threshold values (low_to_medium: 2, medium_to_high: 2) appropriate?

3. **Specific Model Swap Recommendations**
   - For each role (builder/auditor) and complexity (low/medium/high):
     - Current model(s)
     - Recommended model(s)
     - Expected cost savings
     - Risk assessment

4. **Proposed Configuration Changes**
   Output the recommended changes as valid YAML that can be merged into models.yaml.

## Output Format

Provide your response in the following structure:

### Executive Summary
[2-3 sentence summary of key findings]

### Detailed Analysis
[Analysis sections as requested above]

### Proposed models.yaml Changes
```yaml
# Only include sections that need changes
escalation_chains:
  # ... changes ...

complexity_escalation:
  # ... threshold changes if needed ...
```

### Risk Assessment
[Any risks or caveats with the recommendations]
"""

    return prompt


def call_frontier_llm(prompt: str, model: str) -> str:
    """Call frontier LLM with the optimization prompt."""
    try:
        import openai

        client = openai.OpenAI()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at LLM cost optimization and model selection for automated code generation systems. Provide detailed, actionable recommendations.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.3,
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Error calling frontier LLM: {e}")
        return f"Error: {e}"


def parse_optimizer_response(response: str) -> tuple:
    """
    Parse the optimizer response to extract:
    - Markdown report
    - Proposed YAML changes
    """
    # Extract YAML block if present
    proposed_yaml = None
    yaml_start = response.find("```yaml")
    yaml_end = response.find("```", yaml_start + 7) if yaml_start != -1 else -1

    if yaml_start != -1 and yaml_end != -1:
        yaml_content = response[yaml_start + 7 : yaml_end].strip()
        try:
            proposed_yaml = yaml.safe_load(yaml_content)
        except yaml.YAMLError:
            proposed_yaml = {"raw": yaml_content}

    return response, proposed_yaml


def main():
    parser = argparse.ArgumentParser(description="Model Stack Self-Optimizer")
    parser.add_argument(
        "--optimizer-model",
        default="gpt-4o",
        help="Model to use for optimization analysis (default: gpt-4o)",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/autopack",
        help="Directory containing JSONL logs (default: logs/autopack)",
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Number of days of logs to analyze (default: 30)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without calling LLM"
    )
    parser.add_argument(
        "--output-dir", default=".", help="Directory for output files (default: current directory)"
    )

    args = parser.parse_args()

    print("[ModelStackOptimizer] Starting analysis...")

    # Load configurations
    models_yaml = load_yaml("config/models.yaml")
    pricing_yaml = load_yaml("config/pricing.yaml")

    print("[ModelStackOptimizer] Loaded models.yaml and pricing.yaml")

    # Load and aggregate run statistics
    log_entries = load_jsonl_logs(args.log_dir, args.days)
    print(f"[ModelStackOptimizer] Found {len(log_entries)} log entries")

    run_stats = aggregate_stats(log_entries, pricing_yaml)
    print(f"[ModelStackOptimizer] Aggregated stats for {len(run_stats)} model combinations")

    # Build optimization prompt
    prompt = build_optimization_prompt(
        models_yaml=models_yaml,
        pricing_yaml=pricing_yaml,
        run_stats=run_stats,
    )

    if args.dry_run:
        print("\n[DRY RUN] Would send this prompt to optimizer LLM:\n")
        print("=" * 60)
        print(prompt[:2000] + "...[truncated]" if len(prompt) > 2000 else prompt)
        print("=" * 60)
        return

    # Call frontier LLM
    print(f"[ModelStackOptimizer] Calling {args.optimizer_model} for analysis...")
    response = call_frontier_llm(prompt, args.optimizer_model)

    # Parse response
    report_md, proposed_yaml = parse_optimizer_response(response)

    # Save outputs
    today = datetime.utcnow().strftime("%Y%m%d")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"MODEL_STACK_RECOMMENDATIONS_{today}.md"
    with open(report_path, "w") as f:
        f.write(f"# Model Stack Recommendations - {today}\n\n")
        f.write(f"Generated by: {args.optimizer_model}\n")
        f.write(f"Log entries analyzed: {len(log_entries)}\n\n")
        f.write("---\n\n")
        f.write(report_md)

    print(f"[ModelStackOptimizer] Wrote report: {report_path}")

    if proposed_yaml:
        yaml_path = output_dir / f"config/models.proposed.{today}.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w") as f:
            yaml.dump(proposed_yaml, f, default_flow_style=False)
        print(f"[ModelStackOptimizer] Wrote proposed config: {yaml_path}")

    print("\n[ModelStackOptimizer] Analysis complete!")
    print("Next steps:")
    print(f"  1. Review {report_path}")
    print("  2. Compare proposed changes with current config/models.yaml")
    print("  3. Apply changes via git after review")


if __name__ == "__main__":
    main()
