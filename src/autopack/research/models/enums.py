from enum import Enum

class EvidenceType(Enum):
    EMPIRICAL = "empirical"
    THEORETICAL = "theoretical"
    STATISTICAL = "statistical"
    ANECDOTAL = "anecdotal"

class ResearchStage(Enum):
    INTENT_DEFINITION = "intent_definition"
    EVIDENCE_COLLECTION = "evidence_collection"
    ANALYSIS_SYNTHESIS = "analysis_synthesis"
    VALIDATION_REVIEW = "validation_review"
    PUBLICATION_REPORTING = "publication_reporting"

class ValidationStatus(Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED = "failed"

