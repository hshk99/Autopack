class TrustTiers:
    """
    The TrustTiers class defines the levels of trust for sources.
    """

    HIGH_TRUST = "high"
    MEDIUM_TRUST = "medium"
    LOW_TRUST = "low"

    @staticmethod
    def evaluate_source(source):
        """
        Evaluates a source and assigns a trust level.

        :param source: The source to evaluate.
        :return: The trust level of the source.
        """
        # Placeholder for trust evaluation logic
        if source.get("reputation") > 8:
            return TrustTiers.HIGH_TRUST
        elif source.get("reputation") > 5:
            return TrustTiers.MEDIUM_TRUST
        else:
            return TrustTiers.LOW_TRUST

    @staticmethod
    def is_trustworthy(source):
        """
        Determines if a source is trustworthy based on its trust level.

        :param source: The source to evaluate.
        :return: True if the source is trustworthy, False otherwise.
        """
        trust_level = TrustTiers.evaluate_source(source)
        return trust_level in [TrustTiers.HIGH_TRUST, TrustTiers.MEDIUM_TRUST]
