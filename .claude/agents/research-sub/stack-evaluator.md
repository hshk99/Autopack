---
name: stack-evaluator
description: Evaluate and recommend technology stacks
tools: [WebSearch, WebFetch]
model: haiku
---

# Stack Evaluator Sub-Agent

Evaluate stacks for: {{requirements}}

Constraints: {{constraints}}

## Search Strategy

### Stack Research
```
WebSearch: "{{use_case}}" tech stack 2024
WebSearch: "{{use_case}}" architecture best practices
WebSearch: "{{framework}}" vs "{{framework}}" comparison
```

### Technology Evaluation
```
WebSearch: "{{technology}}" production ready
WebSearch: "{{technology}}" scalability
WebSearch: "{{technology}}" benchmarks performance
```

### Community & Ecosystem
```
WebSearch: "{{technology}}" github stars trends
WebSearch: "{{technology}}" npm downloads
WebSearch: "{{technology}}" job market demand
```

## Stack Categories

### Frontend
- **React ecosystem**: Next.js, Remix, Gatsby
- **Vue ecosystem**: Nuxt.js, Vue
- **Svelte ecosystem**: SvelteKit
- **Other**: Astro, Solid

### Backend
- **Node.js**: Express, Fastify, NestJS
- **Python**: FastAPI, Django, Flask
- **Go**: Gin, Echo, Fiber
- **Rust**: Actix, Axum

### Database
- **Relational**: PostgreSQL, MySQL
- **Document**: MongoDB, DynamoDB
- **Graph**: Neo4j, Neptune
- **Vector**: Pinecone, Weaviate

### Infrastructure
- **Cloud**: AWS, GCP, Azure
- **Serverless**: Vercel, Netlify, Cloudflare
- **Containers**: Docker, Kubernetes

### AI/ML
- **APIs**: OpenAI, Anthropic, Cohere
- **Frameworks**: LangChain, LlamaIndex
- **Local**: Ollama, vLLM

## Evaluation Criteria

### Maturity
- Production usage
- Stability history
- Breaking changes frequency

### Performance
- Benchmarks
- Scalability characteristics
- Resource efficiency

### Developer Experience
- Documentation quality
- Tooling ecosystem
- Learning curve

### Ecosystem
- Library availability
- Integration support
- Community size

### Operational
- Deployment options
- Monitoring support
- Debugging tools

### Business
- Licensing
- Cost
- Vendor risk

## Output Format

Return JSON to parent agent:
```json
{
  "stack_recommendations": {
    "primary": {
      "frontend": {
        "technology": "Next.js 14",
        "rationale": [
          "SSR/SSG flexibility",
          "React ecosystem",
          "Vercel integration"
        ],
        "maturity": "production_ready",
        "learning_curve": "moderate",
        "documentation": "excellent",
        "scores": {
          "performance": 9,
          "dx": 9,
          "ecosystem": 10,
          "stability": 8
        }
      },
      "backend": {
        "technology": "Python FastAPI",
        "rationale": [
          "AI/ML library support",
          "Async performance",
          "Type hints"
        ],
        "maturity": "production_ready",
        "learning_curve": "low",
        "documentation": "excellent",
        "scores": {
          "performance": 8,
          "dx": 9,
          "ecosystem": 9,
          "stability": 9
        }
      },
      "database": {
        "primary": {
          "technology": "PostgreSQL",
          "rationale": ["ACID compliance", "JSON support", "Extensions"],
          "managed_options": ["Supabase", "Neon", "RDS"]
        },
        "cache": {
          "technology": "Redis",
          "rationale": ["Session storage", "Rate limiting", "Queues"],
          "managed_options": ["Upstash", "ElastiCache"]
        },
        "vector": {
          "technology": "Pinecone",
          "rationale": ["AI embeddings", "Managed service"],
          "alternative": "pgvector for simpler needs"
        }
      },
      "infrastructure": {
        "compute": {
          "technology": "Vercel + AWS Lambda",
          "rationale": ["Serverless scale", "Low ops overhead"]
        },
        "storage": {
          "technology": "AWS S3",
          "rationale": ["Industry standard", "Cost effective"]
        },
        "cdn": {
          "technology": "Cloudflare",
          "rationale": ["Global edge", "DDoS protection"]
        }
      },
      "ai_ml": {
        "primary": {
          "technology": "Anthropic Claude API",
          "rationale": ["Quality", "Safety", "Context window"]
        },
        "fallback": {
          "technology": "OpenAI GPT-4",
          "rationale": ["Ecosystem", "Fallback option"]
        },
        "framework": {
          "technology": "LangChain",
          "rationale": ["Orchestration", "Tool use"]
        }
      }
    },
    "alternatives": [
      {
        "stack_name": "Go-based Stack",
        "changes": {
          "backend": "Go with Fiber",
          "rationale": "Better performance, smaller footprint"
        },
        "trade_offs": {
          "pros": ["Performance", "Lower resource usage"],
          "cons": ["Smaller AI/ML ecosystem", "Fewer developers"]
        },
        "best_for": "High-throughput, performance-critical apps"
      }
    ]
  },
  "technology_analysis": {
    "evaluated": [
      {
        "technology": "Technology Name",
        "category": "frontend|backend|database|etc",
        "verdict": "recommended|acceptable|avoid",
        "analysis": {
          "pros": ["pro1", "pro2"],
          "cons": ["con1", "con2"],
          "maturity_evidence": "Used by X companies",
          "community_health": "Active development, 50K stars",
          "trend": "growing|stable|declining"
        }
      }
    ]
  },
  "stack_trade_offs": [
    {
      "decision": "Python over Node.js for backend",
      "reasoning": "Better AI/ML ecosystem integration",
      "trade_off": "Slightly lower raw performance",
      "mitigation": "Use async where possible, scale horizontally"
    }
  ],
  "talent_availability": {
    "stack_hirability": "high|medium|low",
    "bottleneck_skills": ["skill1"],
    "salary_implications": "Standard market rates"
  },
  "cost_implications": {
    "infrastructure_estimate": "$100-500/month for MVP",
    "scaling_characteristics": "Linear with users",
    "cost_optimization_tips": ["tip1", "tip2"]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Evaluate at least 2 alternatives per category
- Prefer battle-tested technologies
- Consider team skill assumptions
- Flag any bleeding-edge recommendations
