---
name: forum-discovery
description: Discover discussions on Hacker News, Product Hunt, Stack Overflow, and niche forums
tools: [WebSearch, WebFetch]
model: haiku
---

# Forum Discovery Sub-Agent

Find forum discussions for: {{search_terms}}

Forums to search: {{forums}}

## Search Strategy

### Hacker News
```
WebSearch: site:news.ycombinator.com "{{search_term}}"
WebSearch: site:hn.algolia.com "{{search_term}}"
```

### Product Hunt
```
WebSearch: site:producthunt.com "{{search_term}}"
WebSearch: "{{search_term}}" product hunt launch
```

### Stack Overflow
```
WebSearch: site:stackoverflow.com "{{search_term}}"
WebSearch: site:stackexchange.com "{{search_term}}"
```

### Indie Hackers
```
WebSearch: site:indiehackers.com "{{search_term}}"
```

## Content Prioritization

### Hacker News
- Posts with 100+ points
- Active discussions (50+ comments)
- "Show HN" posts (product showcases)
- "Ask HN" posts (community questions)

### Product Hunt
- Launched products (competitors/alternatives)
- Maker discussions
- Collection/list posts

### Stack Overflow
- Questions with accepted answers
- Highly upvoted answers
- Recent activity

## Output Format

Return JSON to parent agent:
```json
{
  "hacker_news": {
    "posts": [
      {
        "title": "Post title",
        "url": "https://news.ycombinator.com/item?id=...",
        "points": 234,
        "comments": 89,
        "submitted_at": "2024-01-10",
        "post_type": "show_hn|ask_hn|link|discussion",
        "top_comment_insight": "Key insight from top comment..."
      }
    ],
    "total": 15
  },
  "product_hunt": {
    "products": [
      {
        "name": "Product Name",
        "url": "https://producthunt.com/posts/...",
        "tagline": "Product tagline",
        "upvotes": 500,
        "comments": 45,
        "launched_at": "2024-01-05",
        "topics": ["SaaS", "Automation"]
      }
    ],
    "total": 10
  },
  "stack_overflow": {
    "questions": [
      {
        "title": "Question title",
        "url": "https://stackoverflow.com/questions/...",
        "votes": 50,
        "answers": 5,
        "accepted_answer": true,
        "tags": ["python", "api"],
        "asked_at": "2023-06-15"
      }
    ],
    "total": 20
  },
  "indie_hackers": {
    "posts": [...],
    "total": 5
  },
  "key_insights": {
    "technical_challenges": ["challenge1", "challenge2"],
    "market_signals": ["signal1", "signal2"],
    "competitor_launches": ["product1", "product2"]
  }
}
```

## Constraints

- Use haiku model for cost efficiency
- Maximum 15 HN posts
- Maximum 10 PH products
- Maximum 20 SO questions
- Focus on content from last 24 months
- Prioritize highly-engaged content
