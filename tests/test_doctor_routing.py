import unittest
from src.autopack.error_recovery import (
    DoctorRequest,
    DoctorResponse,
    is_complex_failure,
    choose_doctor_model,
    should_escalate_doctor_model,
    DoctorContextSummary
)


class TestDoctorRouting(unittest.TestCase):

    def test_is_complex_failure(self):
        # Single category, 1 attempt, healthy budget -> False
        req = DoctorRequest(
            phase_id="phase1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 2, "total_cap": 25},
            patch_errors=[]
        )
        ctx_summary = DoctorContextSummary(distinct_error_categories_for_phase=1)
        self.assertFalse(is_complex_failure(req, ctx_summary))

        # 2+ error categories -> True
        ctx_summary.distinct_error_categories_for_phase = 2
        self.assertTrue(is_complex_failure(req, ctx_summary))

        # 2+ patch errors -> True
        req.patch_errors = [{"error": "patch_error_1"}, {"error": "patch_error_2"}]
        self.assertTrue(is_complex_failure(req, ctx_summary))

        # Many attempts (>=4) -> True
        req.builder_attempts = 4
        self.assertTrue(is_complex_failure(req, ctx_summary))

        # Health ratio >= 0.8 -> True
        req.health_budget = {"total_failures": 20, "total_cap": 25}
        self.assertTrue(is_complex_failure(req, ctx_summary))

        # Prior escalated action -> True
        ctx_summary.prior_doctor_action = "replan"
        self.assertTrue(is_complex_failure(req, ctx_summary))

    def test_choose_doctor_model(self):
        # Health ratio >= 0.8 always returns strong model
        req = DoctorRequest(
            phase_id="phase1",
            error_category="network",
            builder_attempts=1,
            health_budget={"total_failures": 20, "total_cap": 25},
            patch_errors=[]
        )
        self.assertEqual(choose_doctor_model(req), "claude-sonnet-4-5")

        # Routine failure returns cheap model
        req.health_budget = {"total_failures": 2, "total_cap": 25}
        ctx_summary = DoctorContextSummary(distinct_error_categories_for_phase=1)
        self.assertEqual(choose_doctor_model(req, ctx_summary), "glm-4.6-20250101")

        # Complex failure returns strong model
        ctx_summary.distinct_error_categories_for_phase = 2
        self.assertEqual(choose_doctor_model(req, ctx_summary), "claude-sonnet-4-5")

    def test_should_escalate_doctor_model(self):
        # Cheap model + low confidence + attempts >= 2 -> True
        response = DoctorResponse(action="retry_with_fix", confidence=0.6, rationale="")
        self.assertTrue(should_escalate_doctor_model(response, "glm-4.6-20250101", 2))

        # Strong model -> False (already escalated)
        self.assertFalse(should_escalate_doctor_model(response, "claude-sonnet-4-5", 2))

        # High confidence -> False
        response.confidence = 0.8
        self.assertFalse(should_escalate_doctor_model(response, "glm-4.6-20250101", 2))

    def test_doctor_context_summary(self):
        # Verify DoctorContextSummary.from_context() creates correct summary
        ctx_summary = DoctorContextSummary(
            distinct_error_categories_for_phase=2,
            prior_doctor_action="replan",
            prior_doctor_confidence=0.75
        )
        self.assertEqual(ctx_summary.distinct_error_categories_for_phase, 2)
        self.assertEqual(ctx_summary.prior_doctor_action, "replan")
        self.assertEqual(ctx_summary.prior_doctor_confidence, 0.75)

        # Verify to_dict() produces expected JSON
        expected_dict = {
            "distinct_error_categories_for_phase": 2,
            "prior_doctor_action": "replan",
            "prior_doctor_confidence": 0.75
        }
        self.assertEqual(ctx_summary.__dict__, expected_dict)


if __name__ == '__main__':
    unittest.main()
