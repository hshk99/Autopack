from datetime import datetime

from autopack.research.models.enums import ResearchStage, ValidationStatus
from autopack.research.models.research_intent import ResearchIntent


class ResearchSession:
    def __init__(self, intent: ResearchIntent):
        self.intent = intent
        self.start_time = datetime.now()
        self.end_time = None
        self.current_stage = ResearchStage.INTENT_DEFINITION
        self.validation_status = ValidationStatus.PENDING

    def advance_stage(self):
        """Advance to the next stage of the research pipeline."""
        if self.current_stage == ResearchStage.INTENT_DEFINITION:
            self.current_stage = ResearchStage.EVIDENCE_COLLECTION
        elif self.current_stage == ResearchStage.EVIDENCE_COLLECTION:
            self.current_stage = ResearchStage.ANALYSIS_SYNTHESIS
        elif self.current_stage == ResearchStage.ANALYSIS_SYNTHESIS:
            self.current_stage = ResearchStage.VALIDATION_REVIEW
        elif self.current_stage == ResearchStage.VALIDATION_REVIEW:
            self.current_stage = ResearchStage.PUBLICATION_REPORTING
        else:
            raise ValueError("Research session is already complete.")

    def complete(self):
        """Mark the research session as complete."""
        self.end_time = datetime.now()
        self.validation_status = ValidationStatus.VALIDATED

    def __repr__(self):
        return (
            f"ResearchSession(intent={self.intent}, start_time={self.start_time}, "
            f"end_time={self.end_time}, current_stage={self.current_stage}, "
            f"validation_status={self.validation_status})"
        )


# Example usage:
# intent = ResearchIntent(
#     title="Impact of Climate Change on Marine Life",
#     description="A study to understand the effects of climate change on marine ecosystems.",
#     objectives=["Analyze temperature changes", "Assess species migration patterns"]
# )
# session = ResearchSession(intent)
# session.advance_stage()  # Move to EVIDENCE_COLLECTION
# session.complete()       # Mark as complete

# The ResearchSession class manages the lifecycle of a research project, tracking
# its progress through various stages and ensuring that each stage is completed
# before moving on to the next.
