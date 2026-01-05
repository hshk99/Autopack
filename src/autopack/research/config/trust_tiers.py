"""
Trust Tiers Configuration

This module defines the trust tiers used to categorize information sources based on their
reliability and credibility.
"""

TRUST_TIERS = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


def get_trust_tier(source_id: str) -> int:
    """
    Get the trust tier for a given source identifier.

    :param source_id: The identifier of the source.
    :return: The trust tier as an integer.
    """
    # Placeholder for logic to determine the trust tier of a source
    # This could involve looking up a database or configuration file
    return TRUST_TIERS.get(source_id, 0)


def is_trusted(source_id: str, minimum_tier: int = 2) -> bool:
    """
    Check if a source meets the minimum trust tier requirement.

    :param source_id: The identifier of the source.
    :param minimum_tier: The minimum trust tier required.
    :return: True if the source meets the requirement, False otherwise.
    """
    return get_trust_tier(source_id) >= minimum_tier
