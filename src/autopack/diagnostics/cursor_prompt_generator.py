import os

def generate_cursor_prompt(handoff_bundle_path, error_message, file_list, constraints):
    """
    Generate a cursor-ready prompt for diagnostics handoff.

    :param handoff_bundle_path: Path to the handoff bundle directory.
    :param error_message: Description of the current failure.
    :param file_list: List of files to attach or open.
    :param constraints: Dictionary containing constraints like protected paths, allowed paths, and deliverables.
    :return: A formatted string containing the diagnostics prompt.
    """
    prompt = []
    prompt.append(f"Diagnostics Handoff Bundle Reference: {handoff_bundle_path}")
    prompt.append("\nCurrent Failure:")
    prompt.append(f"- Error: {error_message}")
    prompt.append("\nFiles to Attach/Open:")
    for file in file_list:
        prompt.append(f"- {file}")
    prompt.append("\nConstraints:")
    for key, value in constraints.items():
        prompt.append(f"- {key.capitalize()}: {value}")
    return "\n".join(prompt)

if __name__ == "__main__":
    # Example usage
    handoff_bundle_path = "/path/to/handoff/bundle"
    error_message = "Cannot import name 'format_rules_for_prompt' from 'autopack.learned_rules'"
    file_list = [
        "src/autopack/diagnostics/cursor_prompt_generator.py",
        "src/autopack/dashboard/server.py"
    ]
    constraints = {
        "protected paths": "/src/autopack/protected/",
        "allowed paths": "/src/autopack/diagnostics/",
        "deliverables": "If available, include the generated summary.md"
    }
    prompt = generate_cursor_prompt(handoff_bundle_path, error_message, file_list, constraints)
    print(prompt)
