"""Research gatherers package.

Provides evidence collection from various sources:
- GitHub repositories (github_gatherer.py)
- Twitter/X posts (twitter_gatherer.py)
- Reddit discussions (reddit_gatherer.py)
- LinkedIn professional content (linkedin_gatherer.py)
"""

from autopack.research.gatherers.github_gatherer import GitHubGatherer
from autopack.research.gatherers.linkedin_gatherer import LinkedInGatherer
from autopack.research.gatherers.reddit_gatherer import RedditGatherer
from autopack.research.gatherers.twitter_gatherer import TwitterGatherer

__all__ = [
    "GitHubGatherer",
    "TwitterGatherer",
    "RedditGatherer",
    "LinkedInGatherer",
]
