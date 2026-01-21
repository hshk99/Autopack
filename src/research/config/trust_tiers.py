"""Trust Tier Configuration.

This module defines trust tiers for different source domains and provides
configuration for source evaluation.
"""

from typing import Dict, List

# Trust tier definitions
TRUST_TIERS: Dict[str, List[str]] = {
    # Tier 1: Official documentation and authoritative sources
    "tier1_official": [
        # Programming languages
        "docs.python.org",
        "doc.rust-lang.org",
        "go.dev",
        "docs.oracle.com",  # Java
        "learn.microsoft.com",  # .NET, C#
        # Web technologies
        "developer.mozilla.org",  # MDN
        "www.w3.org",  # W3C standards
        "html.spec.whatwg.org",
        # Frameworks and libraries
        "react.dev",
        "vuejs.org",
        "angular.io",
        "svelte.dev",
        "nextjs.org",
        "docs.djangoproject.com",
        "flask.palletsprojects.com",
        "fastapi.tiangolo.com",
        "expressjs.com",
        "spring.io",
        # Databases
        "postgresql.org",
        "dev.mysql.com",
        "mongodb.com",
        "redis.io",
        # Cloud platforms
        "docs.aws.amazon.com",
        "cloud.google.com",
        "docs.microsoft.com",  # Azure
        # Operating systems
        "kernel.org",
        "docs.freebsd.org",
    ],
    # Tier 2: Verified community sources and established platforms
    "tier2_verified": [
        # Code repositories
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        # Q&A platforms
        "stackoverflow.com",
        "stackexchange.com",
        "serverfault.com",
        "superuser.com",
        # Academic and research
        "arxiv.org",
        "scholar.google.com",
        "ieee.org",
        "acm.org",
        # Package registries
        "pypi.org",
        "npmjs.com",
        "crates.io",
        "rubygems.org",
        # Documentation hosting
        "readthedocs.io",
        "readthedocs.org",
    ],
    # Tier 3: Community platforms and blogs
    "tier3_community": [
        # Developer communities
        "dev.to",
        "hashnode.com",
        "medium.com",
        "reddit.com",
        # Tech news
        "news.ycombinator.com",
        "lobste.rs",
        # Tutorial platforms
        "freecodecamp.org",
        "codecademy.com",
        "udemy.com",
        "coursera.org",
        # Wiki platforms
        "wikipedia.org",
        "wikimedia.org",
    ],
    # Tier 4: General web sources
    "tier4_general": [
        # Tech news sites
        "techcrunch.com",
        "arstechnica.com",
        "theverge.com",
        "wired.com",
        "zdnet.com",
        # Company blogs
        "blog.google",
        "engineering.fb.com",
        "netflixtechblog.com",
        "eng.uber.com",
    ],
    # Tier 5: Untrusted or suspicious sources
    "tier5_untrusted": [
        # Known problematic domains can be added here
    ],
}


# Domain patterns for automatic classification
DOMAIN_PATTERNS: Dict[str, List[str]] = {
    "official_docs": [
        r"^docs?\..*",
        r".*\.readthedocs\.io$",
        r".*\.readthedocs\.org$",
    ],
    "academic": [
        r".*\.edu$",
        r".*\.ac\..*$",
        r"^arxiv\.org$",
        r"^scholar\.google\.com$",
    ],
    "github": [
        r"^github\.com$",
        r"^raw\.githubusercontent\.com$",
        r"^gist\.github\.com$",
    ],
    "stackoverflow": [
        r"^stackoverflow\.com$",
        r"^.*\.stackexchange\.com$",
    ],
}


# Content type trust modifiers
CONTENT_TYPE_MODIFIERS: Dict[str, float] = {
    "official_documentation": 1.0,
    "academic_paper": 0.95,
    "github_repository": 0.85,
    "stackoverflow_answer": 0.80,
    "blog_post": 0.70,
    "forum_post": 0.60,
    "social_media": 0.50,
    "unknown": 0.50,
}


# Recency scoring (days old -> score multiplier)
RECENCY_SCORING: Dict[str, tuple] = {
    "very_recent": (0, 30, 1.0),  # 0-30 days: full score
    "recent": (31, 180, 0.95),  # 31-180 days: 95%
    "moderate": (181, 365, 0.90),  # 181-365 days: 90%
    "old": (366, 730, 0.80),  # 1-2 years: 80%
    "very_old": (731, 1825, 0.70),  # 2-5 years: 70%
    "outdated": (1826, 999999, 0.50),  # 5+ years: 50%
}


# Engagement metrics weights
ENGAGEMENT_WEIGHTS: Dict[str, float] = {
    "stars": 0.3,
    "forks": 0.2,
    "upvotes": 0.25,
    "comments": 0.15,
    "views": 0.10,
}


def get_domain_tier(domain: str) -> str:
    """Get the trust tier for a domain.

    Args:
        domain: Domain name

    Returns:
        Tier identifier
    """
    domain_lower = domain.lower()

    for tier, domains in TRUST_TIERS.items():
        if domain_lower in domains:
            return tier

    return "tier4_general"


def get_tier_score(tier: str) -> float:
    """Get numeric score for a trust tier.

    Args:
        tier: Tier identifier

    Returns:
        Numeric score (0.0-1.0)
    """
    tier_scores = {
        "tier1_official": 1.0,
        "tier2_verified": 0.85,
        "tier3_community": 0.70,
        "tier4_general": 0.50,
        "tier5_untrusted": 0.20,
    }
    return tier_scores.get(tier, 0.50)


def is_trusted_domain(domain: str, min_tier: str = "tier3_community") -> bool:
    """Check if a domain meets minimum trust requirements.

    Args:
        domain: Domain name
        min_tier: Minimum required tier

    Returns:
        True if domain meets requirements
    """
    tier = get_domain_tier(domain)
    tier_order = [
        "tier1_official",
        "tier2_verified",
        "tier3_community",
        "tier4_general",
        "tier5_untrusted",
    ]

    try:
        domain_index = tier_order.index(tier)
        min_index = tier_order.index(min_tier)
        return domain_index <= min_index
    except ValueError:
        return False
