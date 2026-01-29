---
name: reddit-discovery
description: Discover relevant Reddit discussions and subreddits
tools: [WebSearch, WebFetch]
model: haiku
---

# Reddit Discovery Sub-Agent

Find Reddit discussions for: {{search_terms}}

Subreddits to search: {{subreddits}}

## Search Strategy

### Subreddit Discovery
```
WebSearch: "{{topic}}" site:reddit.com best subreddit
WebSearch: reddit communities for "{{topic}}"
```

### Post Discovery
For each subreddit in {{subreddits}}:
```
WebSearch: site:reddit.com/r/{{subreddit}} "{{search_term}}"
```

### High-Value Post Types
- "What's the best..." posts
- "Looking for..." posts
- "I built..." posts (show-and-tell)
- "Why doesn't..." posts (pain points)
- AMAs with industry experts

## Engagement Filtering

Prioritize posts with:
- 50+ upvotes
- 10+ comments
- Awards/gold
- Marked as "useful" or "answered"

## Output Format

Return JSON to parent agent:
```json
{
  "subreddits": [
    {
      "name": "r/subreddit",
      "url": "https://reddit.com/r/subreddit",
      "subscribers": 150000,
      "description": "Community description",
      "relevance": "high|medium|low",
      "post_frequency": "high|medium|low"
    }
  ],
  "posts": [
    {
      "title": "Post title",
      "url": "https://reddit.com/r/.../comments/...",
      "subreddit": "r/subreddit",
      "score": 234,
      "upvote_ratio": 0.95,
      "comments": 45,
      "created_at": "2024-01-10",
      "flair": "Discussion",
      "post_type": "question|discussion|showcase|recommendation",
      "top_comment_preview": "First 200 chars of top comment..."
    }
  ],
  "insights": {
    "common_questions": ["question1", "question2"],
    "frequently_mentioned_tools": ["tool1", "tool2"],
    "sentiment_indicators": {
      "positive_keywords": ["love", "amazing", "helpful"],
      "negative_keywords": ["frustrating", "broken", "expensive"]
    }
  },
  "total_posts": 30
}
```

## Constraints

- Use haiku model for cost efficiency
- Maximum 30 posts
- Focus on posts from last 12 months
- Prioritize posts with substantive discussions (10+ comments)
- Exclude low-effort posts and memes
