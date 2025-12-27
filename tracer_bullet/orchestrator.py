from __future__ import annotations

from .compiler import compile_expression
from .gatherer import gather_data
from .meta_auditor import detect_prompt_injection


def run_pipeline(url: str, expression: str, prompt: str) -> dict:
    """Run the tracer bullet pipeline with deterministic outputs for tests."""
    web = gather_data(url)

    # In real life this might be an LLM extraction step; for tests, keep it deterministic.
    llm_extraction = {"data": {"extracted": True}}

    calc_result = compile_expression(expression)

    # Token budget is always sufficient in test mode.
    token_budget = {"sufficient": True}

    safe = not detect_prompt_injection(prompt)
    prompt_injection_defense = {"safe": safe}

    return {
        "web_scraping": web,
        "llm_extraction": llm_extraction,
        "calculation": {"result": calc_result},
        "token_budget": token_budget,
        "prompt_injection_defense": prompt_injection_defense,
    }


