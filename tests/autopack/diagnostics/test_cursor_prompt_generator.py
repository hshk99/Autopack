import unittest
from autopack.diagnostics.cursor_prompt_generator import generate_cursor_prompt

class TestCursorPromptGenerator(unittest.TestCase):

    def setUp(self):
        self.handoff_bundle_path = "/path/to/handoff/bundle"
        self.error_message = "Cannot import name 'format_rules_for_prompt' from 'autopack.learned_rules'"
        self.file_list = [
            "src/autopack/diagnostics/cursor_prompt_generator.py",
            "src/autopack/dashboard/server.py"
        ]
        self.constraints = {
            "protected paths": "/src/autopack/protected/",
            "allowed paths": "/src/autopack/diagnostics/",
            "deliverables": "If available, include the generated summary.md"
        }

    def test_generate_cursor_prompt(self):
        expected_output = (
            "Diagnostics Handoff Bundle Reference: /path/to/handoff/bundle\n"
            "\nCurrent Failure:\n"
            "- Error: Cannot import name 'format_rules_for_prompt' from 'autopack.learned_rules'\n"
            "\nFiles to Attach/Open:\n"
            "- src/autopack/diagnostics/cursor_prompt_generator.py\n"
            "- src/autopack/dashboard/server.py\n"
            "\nConstraints:\n"
            "- Protected paths: /src/autopack/protected/\n"
            "- Allowed paths: /src/autopack/diagnostics/\n"
            "- Deliverables: If available, include the generated summary.md"
        )
        result = generate_cursor_prompt(
            self.handoff_bundle_path,
            self.error_message,
            self.file_list,
            self.constraints
        )
        self.assertEqual(result, expected_output)

if __name__ == '__main__':
    unittest.main()
