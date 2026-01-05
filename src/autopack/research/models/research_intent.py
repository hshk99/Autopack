class ResearchIntent:
    def __init__(self, title: str, description: str, objectives: list):
        self.title = title
        self.description = description
        self.objectives = objectives

    def is_clear(self) -> bool:
        """Check if the research intent is clearly defined."""
        return bool(self.title and self.description and self.objectives)

    def __repr__(self):
        return (
            f"ResearchIntent(title={self.title}, description={self.description}, "
            f"objectives={self.objectives})"
        )


# Example usage:
# intent = ResearchIntent(
#     title="Impact of Climate Change on Marine Life",
#     description="A study to understand the effects of climate change on marine ecosystems.",
#     objectives=["Analyze temperature changes", "Assess species migration patterns"]
# )
# print(intent.is_clear())  # True if all fields are filled

# This model captures the initial intent of the research, ensuring that the goals
# and objectives are clearly defined and understood before proceeding with the research.

# The ResearchIntent class is a foundational component of the research pipeline,
# guiding the direction and focus of the entire research process.
