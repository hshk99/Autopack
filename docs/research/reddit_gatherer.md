# Reddit Gatherer Documentation

## Overview

The Reddit Gatherer is a component of the research system designed to collect data from Reddit communities. It extracts relevant information with proper citation, adheres to rate limiting policies, and includes error handling mechanisms.

## Features

- **Data Extraction**: Collects subreddit posts, comments, and user information.
- **Rate Limiting**: Implements Reddit API rate limiting to avoid exceeding usage limits.
- **Error Handling**: Robust error handling to manage API failures and retries.

## Usage

To use the Reddit Gatherer, instantiate the `RedditGatherer` class and call its methods to fetch data.

```python
from src/autopack.research.gatherers.reddit_gatherer import RedditGatherer

gatherer = RedditGatherer()
data = gatherer.fetch_subreddit_data('subreddit_name')
```

## Configuration

Ensure that you have valid Reddit API credentials set in your environment variables for authentication.
