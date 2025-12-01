#!/usr/bin/env python3
"""Analyze token usage for a specific run"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import get_db
from autopack.usage_service import UsageService
from autopack.usage_recorder import LlmUsageEvent
from sqlalchemy import func

def analyze_run(run_id: str):
    """Analyze usage for a specific run"""
    db = next(get_db())
    service = UsageService(db)
    
    # Get total usage
    total_usage = service.get_run_usage(run_id)
    
    # Get usage by model
    model_usage = (
        db.query(
            LlmUsageEvent.provider,
            LlmUsageEvent.model,
            LlmUsageEvent.role,
            func.sum(LlmUsageEvent.prompt_tokens).label("prompt_tokens"),
            func.sum(LlmUsageEvent.completion_tokens).label("completion_tokens"),
        )
        .filter(LlmUsageEvent.run_id == run_id)
        .group_by(LlmUsageEvent.provider, LlmUsageEvent.model, LlmUsageEvent.role)
        .all()
    )
    
    print(f"\n=== Usage Analysis for Run: {run_id} ===\n")
    print(f"Total Tokens: {total_usage['total_tokens']:,}")
    print(f"  Prompt: {total_usage['prompt_tokens']:,}")
    print(f"  Completion: {total_usage['completion_tokens']:,}")
    if total_usage['completion_tokens'] > 0:
        print(f"  Ratio: {total_usage['prompt_tokens']/total_usage['completion_tokens']:.2f}:1\n")
    else:
        print(f"  Ratio: N/A (no completion tokens)\n")
    
    print("Breakdown by Model and Role:")
    print("-" * 80)
    for provider, model, role, prompt, completion in model_usage:
        total = prompt + completion
        print(f"{provider:12} | {model:25} | {role:15} | {prompt:>10,} + {completion:>10,} = {total:>12,}")
    
    return {
        'total': total_usage,
        'by_model': [
            {
                'provider': provider,
                'model': model,
                'role': role,
                'prompt_tokens': prompt,
                'completion_tokens': completion,
                'total_tokens': prompt + completion
            }
            for provider, model, role, prompt, completion in model_usage
        ]
    }

if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "fileorg-phase2-resume-20251130-165300"
    analyze_run(run_id)

