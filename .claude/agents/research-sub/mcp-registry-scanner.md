---
name: mcp-registry-scanner
description: Scan MCP (Model Context Protocol) registry for available servers and tools
tools: [WebSearch, WebFetch, Read, Write]
model: haiku
---

# MCP Registry Scanner Sub-Agent

Scan MCP ecosystem for: {{project_requirements}}

## What is MCP?

Model Context Protocol (MCP) is a standard for connecting AI assistants to external tools and data sources. MCP servers provide capabilities that can be used by Claude and other AI systems.

## Research Targets

### Official Registry
- Anthropic MCP Registry
- GitHub MCP repositories
- NPM packages with @modelcontextprotocol

### Community Sources
- Awesome MCP lists
- MCP Discord/community
- Developer blog posts

### Integration Platforms
- Existing MCP server collections
- Pre-built integrations

## Search Queries

```
"MCP server" "[capability]"
"@modelcontextprotocol" npm
site:github.com "MCP server" "[service]"
"Model Context Protocol" "[integration]"
"claude mcp" "[tool]"
```

## Output Format

```json
{
  "required_capabilities": [
    {
      "capability": "Database access",
      "purpose": "Store user data",
      "priority": "critical|high|medium|low"
    }
  ],
  "available_mcp_servers": [
    {
      "name": "mcp-server-postgres",
      "repository": "GitHub URL",
      "npm_package": "@modelcontextprotocol/server-postgres",
      "description": "PostgreSQL database access",
      "capabilities_provided": [
        "query",
        "insert",
        "update",
        "schema inspection"
      ],
      "maturity": "stable|beta|experimental",
      "last_updated": "2024-01-15",
      "stars": 234,
      "maintainer": "official|community",
      "documentation": "URL",
      "matches_requirement": "Database access",
      "setup_complexity": "low|medium|high",
      "notes": "Well-maintained, good documentation"
    }
  ],
  "coverage_analysis": {
    "requirements_covered": [
      {
        "requirement": "Database access",
        "covered_by": ["mcp-server-postgres", "mcp-server-sqlite"],
        "recommended": "mcp-server-postgres",
        "recommendation_rationale": "Better for production use"
      }
    ],
    "requirements_not_covered": [
      {
        "requirement": "Custom API X integration",
        "alternatives": [
          "Build custom MCP server",
          "Use generic HTTP MCP server"
        ],
        "build_complexity": "medium",
        "estimated_effort": "1-2 days"
      }
    ],
    "coverage_percentage": 75
  },
  "recommended_mcp_stack": [
    {
      "server": "mcp-server-filesystem",
      "purpose": "File operations",
      "required": true
    },
    {
      "server": "mcp-server-postgres",
      "purpose": "Database",
      "required": true
    },
    {
      "server": "mcp-server-fetch",
      "purpose": "HTTP requests",
      "required": false,
      "alternative": "Built-in WebFetch"
    }
  ],
  "custom_servers_needed": [
    {
      "purpose": "Integration with Service X",
      "capabilities_needed": ["auth", "read", "write"],
      "reference_implementation": "Similar to mcp-server-Y",
      "estimated_effort": "2-3 days",
      "complexity": "medium"
    }
  ],
  "mcp_ecosystem_insights": {
    "ecosystem_maturity": "growing|mature|early",
    "active_development": true,
    "community_size": "medium",
    "documentation_quality": "good|fair|poor",
    "key_resources": [
      {
        "resource": "MCP Documentation",
        "url": "URL",
        "usefulness": "Essential for building servers"
      }
    ]
  },
  "integration_considerations": {
    "authentication": {
      "pattern": "Environment variables for API keys",
      "security_notes": "Don't hardcode secrets"
    },
    "rate_limiting": {
      "handled_by": "Individual servers or wrapper",
      "recommendation": "Implement at MCP server level"
    },
    "error_handling": {
      "pattern": "MCP error protocol",
      "best_practice": "Return structured errors"
    }
  },
  "build_vs_use_recommendation": {
    "use_existing": ["mcp-server-postgres", "mcp-server-filesystem"],
    "build_custom": ["Service X integration"],
    "rationale": "Good coverage for standard needs, custom needed for specific APIs"
  }
}
```

## Constraints

- Use haiku for cost efficiency
- Focus on actively maintained servers
- Note maturity/stability level
- Check last update date
- Identify official vs community maintained
- Flag any security considerations
