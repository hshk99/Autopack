import unittest
from datetime import datetime
from autopack.research.models.evidence import Evidence
from autopack.research.models.enums import EvidenceType


class TestEvidenceModel(unittest.TestCase):

    def setUp(self):
        self.evidence = Evidence(
            source="https://example.com/research-paper",
            evidence_type=EvidenceType.EMPIRICAL,
            relevance=0.8,
            publication_date=datetime(2023, 5, 17),
        )

    def test_is_recent(self):
        self.assertTrue(self.evidence.is_recent())

    def test_is_valid(self):
        self.assertTrue(self.evidence.is_valid())

    def test_invalid_relevance(self):
        evidence = Evidence(
            source="https://example.com/research-paper",
            evidence_type=EvidenceType.EMPIRICAL,
            relevance=0.4,
            publication_date=datetime(2023, 5, 17),
        )
        self.assertFalse(evidence.is_valid())


if __name__ == "__main__":
    unittest.main()

# This test suite validates the functionality of the Evidence model,
# ensuring that evidence is correctly identified as recent and valid
# based on its attributes.

# The tests cover scenarios for recent evidence, valid relevance scores,
# and invalid relevance scores, providing comprehensive coverage of the
# Evidence model's behavior.
