---
name: sdk-evaluator
description: Evaluate SDK quality and options
tools: [WebSearch, WebFetch]
model: haiku
---

# SDK Evaluator Sub-Agent

Evaluate SDKs for: {{apis}}

Languages: {{languages}}

## Search Strategy

### SDK Discovery
```
WebSearch: "{{api}}" SDK {{language}}
WebSearch: "{{api}}" client library {{language}}
WebSearch: "{{api}}" {{language}} package
```

### SDK Quality
```
WebSearch: "{{sdk}}" github stars
WebSearch: "{{sdk}}" issues problems
WebSearch: "{{sdk}}" vs alternative
```

### Package Registries
```
WebFetch: https://pypi.org/project/{{package}}
WebFetch: https://www.npmjs.com/package/{{package}}
WebSearch: "{{package}}" download stats
```

## Evaluation Criteria

### Maintenance Status
- Last commit/release date
- Commit frequency
- Issue response time
- Maintainer activity

### Code Quality
- TypeScript/type definitions
- Test coverage
- Documentation
- Code style

### Developer Experience
- Installation simplicity
- API design clarity
- Error messages
- Examples quality

### Reliability
- Stability history
- Breaking changes frequency
- Version compatibility
- Production usage

### Community
- GitHub stars
- NPM/PyPI downloads
- Stack Overflow activity
- Community contributions

## SDK Types

### Official SDKs
- Maintained by API provider
- Typically best supported
- Most reliable

### Community SDKs
- Maintained by community
- May have better DX
- Risk of abandonment

### Generated SDKs
- Auto-generated from OpenAPI
- Comprehensive but verbose
- May lack polish

## Output Format

Return JSON to parent agent:
```json
{
  "sdk_summary": {
    "total_evaluated": 20,
    "by_language": {
      "python": 8,
      "typescript": 8,
      "go": 4
    },
    "official_available": 15,
    "community_only": 3,
    "no_sdk": 2
  },
  "by_api": [
    {
      "api": "Anthropic",
      "sdks": {
        "python": {
          "recommended": {
            "package_name": "anthropic",
            "install": "pip install anthropic",
            "repository": "https://github.com/anthropics/anthropic-sdk-python",
            "registry_url": "https://pypi.org/project/anthropic/",
            "version": "0.18.0",
            "official": true,
            "maintainer": "Anthropic",
            "metrics": {
              "github_stars": 500,
              "weekly_downloads": 100000,
              "open_issues": 15,
              "last_release": "2024-01-15",
              "commit_frequency": "Weekly"
            },
            "quality_assessment": {
              "type_hints": true,
              "async_support": true,
              "documentation": "excellent",
              "examples": "comprehensive",
              "test_coverage": "high",
              "code_style": "clean"
            },
            "features": {
              "streaming": true,
              "retries": true,
              "rate_limiting": "built-in",
              "error_handling": "typed exceptions"
            },
            "compatibility": {
              "python_versions": "3.7+",
              "dependencies": "minimal (httpx)",
              "conflicts": "none known"
            },
            "recommendation": "Excellent SDK, use this",
            "score": 9.5
          },
          "alternatives": []
        },
        "typescript": {
          "recommended": {
            "package_name": "@anthropic-ai/sdk",
            "install": "npm install @anthropic-ai/sdk",
            "repository": "https://github.com/anthropics/anthropic-sdk-typescript",
            "registry_url": "https://www.npmjs.com/package/@anthropic-ai/sdk",
            "version": "0.17.0",
            "official": true,
            "maintainer": "Anthropic",
            "metrics": {
              "github_stars": 300,
              "weekly_downloads": 50000,
              "open_issues": 10,
              "last_release": "2024-01-10"
            },
            "quality_assessment": {
              "typescript_native": true,
              "types_quality": "excellent",
              "documentation": "good",
              "examples": "good"
            },
            "features": {
              "streaming": true,
              "retries": true,
              "browser_support": false
            },
            "compatibility": {
              "node_versions": "18+",
              "esm_support": true,
              "cjs_support": true
            },
            "recommendation": "Good SDK, production ready",
            "score": 8.5
          }
        },
        "go": {
          "recommended": null,
          "status": "no_official_sdk",
          "alternatives": [
            {
              "package_name": "github.com/user/anthropic-go",
              "official": false,
              "maintainer": "Community",
              "metrics": {
                "github_stars": 50,
                "last_commit": "2024-01-01"
              },
              "quality_assessment": {
                "documentation": "basic",
                "test_coverage": "low"
              },
              "risk": "medium - community maintained",
              "recommendation": "Use with caution or use REST directly"
            }
          ]
        }
      }
    }
  ],
  "sdk_gaps": [
    {
      "api": "Some API",
      "language": "go",
      "gap_type": "no_sdk",
      "workaround": "Use REST API directly",
      "effort": "medium",
      "recommendation": "Create thin wrapper or use generated client"
    }
  ],
  "installation_commands": {
    "python": [
      "pip install anthropic",
      "pip install stripe",
      "pip install sendgrid"
    ],
    "typescript": [
      "npm install @anthropic-ai/sdk",
      "npm install stripe",
      "npm install @sendgrid/mail"
    ]
  },
  "compatibility_matrix": {
    "python": {
      "minimum_version": "3.8",
      "recommended_version": "3.11+",
      "dependency_conflicts": "None identified"
    },
    "node": {
      "minimum_version": "18",
      "recommended_version": "20 LTS",
      "dependency_conflicts": "None identified"
    }
  },
  "recommendations": {
    "stack_alignment": "All required SDKs available for Python and TypeScript",
    "language_recommendation": "Python for backend (best AI SDK support)",
    "sdk_concerns": [
      {
        "concern": "Go SDK gaps for AI APIs",
        "impact": "Would require REST API usage",
        "recommendation": "Use Python for AI services"
      }
    ]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Check actual package registries
- Verify version recency
- Note official vs community SDKs
- Score based on maintenance + quality
