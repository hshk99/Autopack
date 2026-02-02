"""Research gatherers package.

Provides evidence collection from various sources:
- GitHub repositories (github_gatherer.py)
- Twitter/X posts (twitter_gatherer.py)
- Reddit discussions (reddit_gatherer.py)
- Google Trends (public data)
- Product Hunt (public data)
- HackerNews (discussions)
"""

from autopack.research.gatherers.github_gatherer import GitHubGatherer
from autopack.research.gatherers.reddit_gatherer import RedditGatherer
from autopack.research.gatherers.twitter_gatherer import TwitterGatherer

__all__ = [
    "GitHubGatherer",
    "TwitterGatherer",
    "RedditGatherer",
]
