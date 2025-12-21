# Tracer Bullet - End-to-End Pipeline Validation

## Overview

This tracer bullet implementation validates the feasibility of a complete pipeline:

1. **Web Scraping** - Fetch content with robots.txt compliance and rate limiting
2. **LLM Extraction** - Extract structured data with prompt injection defenses
3. **Python Calculators** - Perform safe mathematical operations
4. **Token Budget Tracking** - Monitor and enforce token limits

## Components

### Web Scraper (`web_scraper.py`)

- Respects robots.txt rules
- Enforces configurable rate limits per domain
- Implements retry logic with exponential backoff
- Proper user-agent identification

```python
from tracer_bullet import WebScraper, ScraperConfig

config = ScraperConfig(
    user_agent="MyBot/1.0",
    rate_limit_seconds=2.0,
    max_retries=3
)
scraper = WebScraper(config=config)
content = scraper.fetch("https://example.com/page")
```

### LLM Extractor (`llm_extractor.py`)

- Uses Claude for structured data extraction
- Detects and blocks prompt injection attempts
- Validates output against JSON schema
- Tracks token usage

```python
from tracer_bullet import LLMExtractor

extractor = LLMExtractor(model="claude-sonnet-4-5")
schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "value": {"type": "number"}
    }
}
result = extractor.extract(text, schema, max_tokens=4096)
```

### Calculator (`calculator.py`)

- Safe mathematical operations with type validation
- Common calculations: sum, average, percentage, min/max
- Comprehensive error handling

```python
from tracer_bullet import Calculator

calc = Calculator()
sum_result = calc.sum([1, 2, 3, 4, 5])
avg_result = calc.average([10, 20, 30])
pct_result = calc.percentage(25, 100)
```

### Pipeline (`pipeline.py`)

- Integrates all components into end-to-end flow
- Handles errors at each stage
- Returns comprehensive results

```python
from tracer_bullet import TracerBulletPipeline

pipeline = TracerBulletPipeline()
result = pipeline.execute(
    url="https://example.com/data",
    extraction_schema=schema,
    calculations={"total": "sum", "average": "avg"},
    max_tokens=4096
)

if result.success:
    print(f"Extracted: {result.extracted_data}")
    print(f"Calculations: {result.calculations}")
    print(f"Tokens used: {result.tokens_used}")
```

## Validation Criteria

### ✅ Web Scraping Feasibility

- Robots.txt parsing and compliance
- Rate limiting per domain
- Retry logic with backoff
- User-agent identification

### ✅ LLM Extraction Quality

- Structured JSON output
- Schema validation
- Prompt injection detection
- Token budget tracking

### ✅ Calculator Correctness

- Type validation
- Error handling
- Common operations (sum, avg, pct, min/max)

### ✅ Token Budget Management

- Track tokens per extraction
- Cumulative token counting
- Configurable limits

### ✅ Prompt Injection Defenses

- Pattern-based detection
- Blocks malicious inputs
- Logs security events

## Testing

Run the test suite:

```bash
pytest tests/test_tracer_bullet.py -v
```

Tests cover:
- Robots.txt blocking
- Rate limiting enforcement
- Retry logic
- Prompt injection detection
- JSON parsing
- Calculator operations
- End-to-end pipeline
- Token tracking

## Dependencies

```
anthropic>=0.8.0
requests>=2.31.0
```

Install with:

```bash
pip install anthropic requests
```

## Environment Variables

- `ANTHROPIC_API_KEY` - Required for LLM extraction

## Next Steps

This tracer bullet validates:

1. ✅ Web scraping is feasible with proper safety measures
2. ✅ LLM extraction produces structured, validated data
3. ✅ Python calculators work correctly with type safety
4. ✅ Token budgets can be tracked and enforced
5. ✅ Prompt injection defenses are effective

Ready to proceed with full implementation!
