---
name: anchor-generator
description: Generate Autopack intention anchors from research outputs
tools: [Task]
model: opus
---

# Anchor Generator Agent

Generate intention anchors for: {{project_idea}}

Using inputs from: {{compiled_research}}, {{audit_recommendation}}

## Purpose

This agent synthesizes all research findings into Autopack-compatible intention anchors that will guide autonomous project execution. It maps research insights to Autopack's IntentionAnchorV2 pivot types.

## Autopack Intention Anchor Types

### 1. NorthStar
Primary project direction and success criteria

### 2. SafetyRisk
Technical, business, and operational risks with mitigations

### 3. EvidenceVerification
Claims requiring validation and evidence standards

### 4. ScopeBoundaries
In-scope, out-of-scope, and future scope definitions

### 5. BudgetCost
Financial constraints and cost projections

### 6. MemoryContinuity
Context preservation and decision tracking

### 7. GovernanceReview
Approval gates and review checkpoints

### 8. ParallelismIsolation
Independent workstreams and dependencies

## Output Format

Generate comprehensive intention anchors:
```json
{
  "autopack_intention_anchors": {
    "version": "2.0",
    "generated_at": "2024-01-15T10:30:00Z",
    "project_id": "{{project_id}}",
    "source": "claude-agent-research-synthesis",

    "north_star": {
      "pivot_type": "NorthStar",
      "primary_objective": {
        "statement": "Build an AI-powered automation platform that helps SMBs streamline their operations, starting with [specific workflow]",
        "success_definition": "Achieve product-market fit with engaged user base and sustainable unit economics"
      },
      "success_metrics": [
        {
          "metric": "Monthly Active Users (MAU)",
          "target": 1000,
          "timeline": "6 months post-launch",
          "measurement": "Unique users with 1+ action/month",
          "rationale": "Validates product engagement"
        },
        {
          "metric": "Monthly Recurring Revenue (MRR)",
          "target": 10000,
          "timeline": "12 months post-launch",
          "measurement": "Sum of all subscription revenue",
          "rationale": "Validates business model"
        },
        {
          "metric": "Net Promoter Score (NPS)",
          "target": 50,
          "timeline": "6 months post-launch",
          "measurement": "Standard NPS survey",
          "rationale": "Validates user satisfaction"
        },
        {
          "metric": "Customer Acquisition Cost (CAC)",
          "target": 100,
          "timeline": "Ongoing",
          "measurement": "Marketing spend / new customers",
          "rationale": "Validates sustainable growth"
        }
      ],
      "guiding_principles": [
        {
          "principle": "User simplicity over feature completeness",
          "rationale": "Research shows SMBs prioritize ease of use",
          "application": "Always choose the simpler UX option"
        },
        {
          "principle": "Speed to market over perfection",
          "rationale": "Competitive window exists but narrowing",
          "application": "Ship MVP features quickly, iterate based on feedback"
        },
        {
          "principle": "AI-native architecture",
          "rationale": "This is our key differentiator",
          "application": "Build AI into core workflows, not as addon"
        }
      ],
      "non_negotiables": [
        "Must work for non-technical users",
        "Must have viable unit economics",
        "Must not compromise on data security"
      ],
      "evidence_basis": {
        "market_validation": "Research score 7.5/10",
        "user_demand": "Strong signals from multiple sources",
        "competitive_opportunity": "Underserved SMB segment identified"
      }
    },

    "safety_risk": {
      "pivot_type": "SafetyRisk",
      "risk_tolerance": "moderate",
      "risk_categories": {
        "technical_risks": [
          {
            "risk_id": "TECH-001",
            "risk": "AI API dependency creates single point of failure",
            "probability": "medium",
            "impact": "high",
            "risk_score": 6,
            "mitigation": {
              "strategy": "Multi-provider abstraction layer",
              "implementation": "Build API wrapper supporting Anthropic and OpenAI",
              "trigger": "Design phase",
              "owner": "Backend architect"
            },
            "monitoring": "Track API uptime, implement circuit breaker",
            "escalation": "If primary API down > 5 min, auto-switch to backup"
          },
          {
            "risk_id": "TECH-002",
            "risk": "AI response quality variance affects user experience",
            "probability": "medium",
            "impact": "medium",
            "risk_score": 4,
            "mitigation": {
              "strategy": "Prompt engineering + quality guardrails",
              "implementation": "Extensive prompt testing, output validation",
              "trigger": "Development phase",
              "owner": "AI engineer"
            }
          },
          {
            "risk_id": "TECH-003",
            "risk": "Rate limits constrain scaling",
            "probability": "low",
            "impact": "medium",
            "risk_score": 3,
            "mitigation": {
              "strategy": "Request queuing + tier upgrade path",
              "implementation": "Redis queue, caching layer",
              "trigger": "Before growth phase",
              "owner": "Backend"
            }
          }
        ],
        "business_risks": [
          {
            "risk_id": "BUS-001",
            "risk": "Incumbent competitive response",
            "probability": "high",
            "impact": "medium",
            "risk_score": 5,
            "mitigation": {
              "strategy": "Speed + niche focus + integration moat",
              "implementation": "Rapid MVP, deep integrations",
              "trigger": "Ongoing",
              "owner": "Product/Strategy"
            }
          },
          {
            "risk_id": "BUS-002",
            "risk": "Pricing model doesn't achieve unit economics",
            "probability": "medium",
            "impact": "high",
            "risk_score": 6,
            "mitigation": {
              "strategy": "Early pricing validation + usage monitoring",
              "implementation": "User interviews, A/B testing",
              "trigger": "Before public launch",
              "owner": "Product"
            }
          }
        ],
        "legal_risks": [
          {
            "risk_id": "LEG-001",
            "risk": "GDPR non-compliance",
            "probability": "low",
            "impact": "high",
            "risk_score": 4,
            "mitigation": {
              "strategy": "Build compliance from day 1",
              "implementation": "Consent management, data deletion, privacy policy",
              "trigger": "Before EU launch",
              "owner": "Engineering + Legal"
            }
          }
        ],
        "operational_risks": [
          {
            "risk_id": "OPS-001",
            "risk": "Team capacity constraints",
            "probability": "medium",
            "impact": "medium",
            "risk_score": 4,
            "mitigation": {
              "strategy": "Use managed services, prioritize ruthlessly",
              "implementation": "Lean MVP scope, outsource non-core",
              "trigger": "Ongoing",
              "owner": "Leadership"
            }
          }
        ]
      },
      "risk_review_schedule": "Weekly during development, bi-weekly post-launch",
      "escalation_matrix": {
        "critical": "Immediate leadership + stakeholder notification",
        "high": "Within 24 hours to leadership",
        "medium": "Weekly risk review",
        "low": "Monthly review"
      }
    },

    "evidence_verification": {
      "pivot_type": "EvidenceVerification",
      "evidence_standards": {
        "market_claims": {
          "minimum_sources": 2,
          "preferred_source_tiers": [1, 2],
          "recency_requirement": "Within 12 months"
        },
        "technical_claims": {
          "verification_method": "Direct testing or documentation review",
          "recency_requirement": "Within 6 months"
        },
        "user_claims": {
          "minimum_sample": 10,
          "verification_method": "User interviews or surveys"
        }
      },
      "validated_claims": [
        {
          "claim": "TAM is $50 billion",
          "status": "validated",
          "evidence_count": 3,
          "confidence": "high",
          "sources": ["Statista", "Grand View Research", "Industry Association"]
        },
        {
          "claim": "SMB segment is underserved",
          "status": "validated",
          "evidence_count": 5,
          "confidence": "high",
          "sources": ["Competitive analysis", "Social sentiment", "Forum research"]
        }
      ],
      "claims_requiring_validation": [
        {
          "claim": "Users will pay $29-79/month",
          "status": "needs_validation",
          "validation_method": "User interviews (10+) + A/B pricing test",
          "timeline": "Before pricing finalization",
          "owner": "Product",
          "blocking": false
        },
        {
          "claim": "3-4 month MVP timeline is achievable",
          "status": "needs_validation",
          "validation_method": "Team capacity confirmation + detailed planning",
          "timeline": "Before development start",
          "owner": "Engineering",
          "blocking": true
        }
      ],
      "assumption_tracking": {
        "documented_assumptions": 8,
        "review_frequency": "Bi-weekly",
        "invalidation_protocol": "Pause development, reassess strategy"
      }
    },

    "scope_boundaries": {
      "pivot_type": "ScopeBoundaries",
      "mvp_scope": {
        "in_scope": [
          {
            "feature": "Core automation workflow",
            "priority": "P0",
            "rationale": "Primary value proposition",
            "success_criteria": "User can complete full workflow"
          },
          {
            "feature": "AI-powered suggestions",
            "priority": "P0",
            "rationale": "Key differentiator",
            "success_criteria": "Suggestions improve user efficiency"
          },
          {
            "feature": "User authentication",
            "priority": "P0",
            "rationale": "Required for product",
            "success_criteria": "Secure login/signup flow"
          },
          {
            "feature": "Basic integrations (3-5 key platforms)",
            "priority": "P1",
            "rationale": "Enables real workflows",
            "success_criteria": "Bidirectional data sync"
          },
          {
            "feature": "Freemium + paid tier",
            "priority": "P1",
            "rationale": "PLG model requirement",
            "success_criteria": "Clear upgrade path, payment processing"
          }
        ],
        "out_of_scope": [
          {
            "feature": "Enterprise features (SSO, audit logs, RBAC)",
            "reason": "Not target market for MVP",
            "revisit": "Post-PMF if enterprise interest"
          },
          {
            "feature": "Mobile applications",
            "reason": "Web-first, resource constraints",
            "revisit": "Post-PMF based on demand"
          },
          {
            "feature": "On-premise deployment",
            "reason": "SMB focus, complexity",
            "revisit": "Unlikely - conflicts with AI architecture"
          },
          {
            "feature": "White-label/API for resellers",
            "reason": "Premature, complexity",
            "revisit": "Post scale"
          },
          {
            "feature": "Advanced analytics/reporting",
            "reason": "Not core to initial value",
            "revisit": "V1.1 or later"
          }
        ],
        "scope_change_protocol": {
          "addition_threshold": "Must be P0 and validated user need",
          "removal_threshold": "Leadership approval required for P0",
          "escalation": "Any scope change > 1 week effort requires review"
        }
      },
      "future_scope": {
        "phase_2": [
          "Advanced analytics dashboard",
          "Additional integrations (10+)",
          "Team collaboration features"
        ],
        "phase_3": [
          "Mobile app",
          "API for developers",
          "Enterprise tier"
        ]
      }
    },

    "budget_cost": {
      "pivot_type": "BudgetCost",
      "budget_constraints": {
        "total_mvp_budget": 75000,
        "monthly_runway": 15000,
        "timeline_months": 5,
        "buffer_percent": 20
      },
      "cost_breakdown": {
        "development": {
          "team_cost_monthly": 12000,
          "contractor_budget": 5000,
          "total_mvp": 53000
        },
        "infrastructure": {
          "monthly_estimate": 300,
          "total_mvp": 1500,
          "scaling_trigger": "1000 users"
        },
        "tools_services": {
          "monthly_estimate": 200,
          "items": ["Vercel Pro", "Supabase", "Analytics", "Monitoring"],
          "total_mvp": 1000
        },
        "api_costs": {
          "monthly_estimate": 500,
          "scaling_model": "Linear with users",
          "total_mvp": 2500
        },
        "marketing_initial": {
          "budget": 2000,
          "purpose": "Launch activities, content"
        },
        "legal_compliance": {
          "budget": 3000,
          "items": ["Privacy policy", "TOS", "Basic legal review"]
        },
        "contingency": {
          "budget": 12000,
          "percent": 20
        }
      },
      "cost_monitoring": {
        "review_frequency": "Weekly",
        "alert_threshold": "80% of category budget",
        "escalation": "Budget overrun requires leadership approval"
      },
      "cost_optimization_strategies": [
        "Use managed services to reduce ops overhead",
        "Implement AI caching to reduce API costs",
        "Start with free tiers where possible"
      ]
    },

    "memory_continuity": {
      "pivot_type": "MemoryContinuity",
      "context_preservation": {
        "research_artifacts": {
          "location": "{project}/.autopack/research/",
          "retention": "permanent",
          "format": "JSON + Markdown summaries",
          "note": "Stored in project directory (AUTOPACK_PROJECTS_ROOT/{project})"
        },
        "decision_log": {
          "location": "{project}/.autopack/decisions/",
          "format": "Append-only decision records",
          "required_fields": ["decision", "rationale", "alternatives", "date"]
        },
        "assumption_tracker": {
          "location": "{project}/.autopack/assumptions.json",
          "review_schedule": "bi-weekly"
        }
      },
      "session_continuity": {
        "strategy": "File-based state with summaries",
        "key_files": [
          "PROJECT_STATUS.md - Current state summary",
          "DECISION_LOG.md - All major decisions",
          "BLOCKERS.md - Current blockers and resolutions"
        ]
      },
      "handoff_protocol": {
        "human_handoff": "HANDOFF.md with context summary",
        "autopack_handoff": "READY_FOR_AUTOPACK marker file"
      }
    },

    "governance_review": {
      "pivot_type": "GovernanceReview",
      "review_gates": [
        {
          "gate": "Research Complete",
          "trigger": "All research agents completed",
          "reviewer": "Human",
          "approval_required": true,
          "artifacts": ["Research summary", "Go/no-go recommendation"]
        },
        {
          "gate": "MVP Scope Approved",
          "trigger": "Before development start",
          "reviewer": "Human",
          "approval_required": true,
          "artifacts": ["Scope document", "Resource plan"]
        },
        {
          "gate": "Pre-Launch Review",
          "trigger": "MVP complete",
          "reviewer": "Human",
          "approval_required": true,
          "artifacts": ["Testing results", "Launch checklist"]
        }
      ],
      "automated_checks": [
        {
          "check": "Test coverage > 70%",
          "trigger": "Every PR",
          "blocking": true
        },
        {
          "check": "Security scan",
          "trigger": "Every deployment",
          "blocking": true
        }
      ],
      "escalation_triggers": [
        "Scope change > 1 week effort",
        "Budget overrun > 10%",
        "Critical risk materialization",
        "Key assumption invalidated"
      ]
    },

    "parallelism_isolation": {
      "pivot_type": "ParallelismIsolation",
      "workstreams": [
        {
          "workstream": "Frontend Development",
          "can_parallelize": true,
          "dependencies": ["Design system", "API contracts"],
          "isolation_boundary": "Component-level"
        },
        {
          "workstream": "Backend Development",
          "can_parallelize": true,
          "dependencies": ["Database schema", "API design"],
          "isolation_boundary": "Service-level"
        },
        {
          "workstream": "AI Integration",
          "can_parallelize": "partial",
          "dependencies": ["Backend API", "Prompt design"],
          "isolation_boundary": "Module-level"
        },
        {
          "workstream": "Integrations",
          "can_parallelize": true,
          "dependencies": ["Core data model"],
          "isolation_boundary": "Adapter-level"
        }
      ],
      "integration_points": [
        {
          "point": "API Contract Finalization",
          "timing": "End of week 1",
          "participants": ["Frontend", "Backend"]
        },
        {
          "point": "AI Integration Point",
          "timing": "End of week 3",
          "participants": ["Backend", "AI"]
        }
      ],
      "conflict_resolution": "Daily standup + immediate escalation for blockers"
    }
  },

  "handoff_instructions": {
    "next_step": "Initialize Autopack with these anchors",
    "command": "autopack init --anchors intention_anchors.json",
    "human_review_required": true,
    "files_to_generate": [
      "intention_anchors.json",
      "PROJECT_BRIEF.md",
      "READY_FOR_AUTOPACK"
    ]
  },

  "generation_metadata": {
    "generator": "anchor-generator",
    "model": "opus",
    "generated_at": "2024-01-15T10:30:00Z",
    "research_inputs_used": 8,
    "validation_status": "passed",
    "confidence": "high"
  }
}
```

## Generation Process

1. **Ingest** all research outputs
2. **Map findings** to anchor types
3. **Synthesize** coherent anchors
4. **Validate** completeness
5. **Generate** Autopack-ready format

## Anchor Quality Standards

- Every anchor has rationale from research
- All risks have mitigations
- Scope boundaries are clear
- Budget is detailed and realistic
- Governance gates are defined

## Constraints

- Use opus model for synthesis quality
- Map all research findings to appropriate anchors
- Ensure anchors are Autopack-compatible
- Include evidence basis for key decisions
- Generate immediately usable output
