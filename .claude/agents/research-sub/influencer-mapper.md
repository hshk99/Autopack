---
name: influencer-mapper
description: Identify and profile relevant influencers
tools: [WebSearch, WebFetch]
model: haiku
---

# Influencer Mapper Sub-Agent

Map influencers for: {{topic}}

Platforms: {{platforms}}

## Search Strategy

### Influencer Discovery
```
WebSearch: "{{topic}}" influencer
WebSearch: "{{topic}}" thought leader
WebSearch: best "{{topic}}" accounts to follow
WebSearch: "{{topic}}" experts twitter
```

### Content Creators
```
WebSearch: "{{topic}}" youtube channel
WebSearch: "{{topic}}" podcast host
WebSearch: "{{topic}}" newsletter author
```

### Community Leaders
```
WebSearch: "{{topic}}" community founder
WebSearch: "{{topic}}" discord server creator
WebSearch: "{{topic}}" subreddit moderator
```

## Influencer Categories

### By Platform
- **Twitter/X**: Thought leaders, commentators
- **YouTube**: Tutorial creators, reviewers
- **LinkedIn**: B2B influencers, executives
- **TikTok**: Short-form educators
- **Podcasts**: Interview hosts, educators
- **Newsletters**: Curators, analysts

### By Tier (Followers)
- **Mega**: 1M+ followers
- **Macro**: 100K-1M followers
- **Micro**: 10K-100K followers
- **Nano**: 1K-10K followers

### By Type
- **Individual**: Personal brands
- **Company**: Brand accounts
- **Publication**: Media outlets
- **Community**: Group accounts

## Evaluation Criteria

### Quantitative
- Follower count
- Engagement rate
- Posting frequency
- Growth rate

### Qualitative
- Content quality
- Relevance to topic
- Authenticity
- Audience demographics

### Collaboration Potential
- Past brand deals
- Openness to partnerships
- Content alignment
- Pricing indicators

## Output Format

Return JSON to parent agent:
```json
{
  "influencer_summary": {
    "total_identified": 50,
    "profiled": 25,
    "by_tier": {
      "mega": 2,
      "macro": 5,
      "micro": 12,
      "nano": 6
    },
    "by_platform": {
      "twitter": 15,
      "youtube": 5,
      "linkedin": 3,
      "podcast": 2
    }
  },
  "influencers": {
    "mega_tier": [
      {
        "name": "Display Name",
        "handle": "@username",
        "platform": "twitter",
        "url": "https://twitter.com/username",
        "followers": 1500000,
        "engagement_rate": 2.5,
        "posting_frequency": "3x daily",
        "content_focus": ["{{topic}}", "related topic"],
        "typical_content": "Commentary, threads, news sharing",
        "audience_demographics": {
          "primary": "Tech professionals 25-45",
          "geography": "Global, US-heavy"
        },
        "sentiment_toward_topic": "positive",
        "verification": true,
        "influence_type": "thought_leader",
        "recent_relevant_content": [
          {
            "url": "https://twitter.com/.../status/...",
            "summary": "Thread about {{topic}} trends",
            "engagement": 5000,
            "date": "2024-01-10"
          }
        ],
        "collaboration_indicators": {
          "past_brand_deals": true,
          "openness": "Selective partnerships",
          "estimated_cost": "$5000-10000 per post",
          "contact_method": "DM or email in bio"
        },
        "relevance_score": 9,
        "partnership_potential": "high"
      }
    ],
    "macro_tier": [...],
    "micro_tier": [
      {
        "name": "Niche Expert",
        "handle": "@nicheexpert",
        "platform": "twitter",
        "url": "https://twitter.com/nicheexpert",
        "followers": 45000,
        "engagement_rate": 5.5,
        "posting_frequency": "daily",
        "content_focus": ["{{topic}} deep dives"],
        "typical_content": "Tutorials, tips, case studies",
        "audience_demographics": {
          "primary": "Practitioners and learners",
          "geography": "English-speaking"
        },
        "sentiment_toward_topic": "enthusiastic",
        "verification": false,
        "influence_type": "educator",
        "relevance_score": 10,
        "partnership_potential": "high",
        "why_notable": "Highly engaged niche audience, authentic voice"
      }
    ],
    "nano_tier": [...]
  },
  "content_creators": {
    "youtube": [
      {
        "channel": "Channel Name",
        "url": "https://youtube.com/...",
        "subscribers": 250000,
        "typical_views": 50000,
        "content_type": "Tutorials and reviews",
        "relevance": "high",
        "collaboration_type": "Sponsored video, product review"
      }
    ],
    "podcasts": [
      {
        "name": "Podcast Name",
        "url": "https://...",
        "listeners": "50K estimated",
        "frequency": "Weekly",
        "guest_interviews": true,
        "relevance": "high",
        "collaboration_type": "Guest appearance, sponsorship"
      }
    ],
    "newsletters": [
      {
        "name": "Newsletter Name",
        "url": "https://...",
        "subscribers": "25K",
        "frequency": "Weekly",
        "relevance": "high",
        "collaboration_type": "Sponsored mention, feature"
      }
    ]
  },
  "community_leaders": [
    {
      "name": "Community Name",
      "platform": "Discord",
      "url": "https://discord.gg/...",
      "members": 15000,
      "activity": "high",
      "leader": "@leadername",
      "relevance": "high",
      "engagement_opportunity": "AMA, community partnership"
    }
  ],
  "strategic_recommendations": {
    "top_partnership_targets": [
      {
        "influencer": "@username",
        "rationale": "High relevance, engaged audience, reasonable cost",
        "suggested_approach": "Offer early access, case study collaboration",
        "priority": "high"
      }
    ],
    "content_collaboration_ideas": [
      "Guest post exchange with newsletter authors",
      "Tutorial series with micro-influencers",
      "Podcast tour for launch"
    ],
    "budget_recommendations": {
      "low_budget": "Focus on nano/micro influencers, offer product access",
      "medium_budget": "Add micro influencer paid partnerships",
      "high_budget": "Include macro tier for reach"
    }
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Profile minimum 15 influencers across tiers
- Verify follower counts are current
- Focus on genuine engagement over vanity metrics
- Note any red flags (fake followers, controversy)
