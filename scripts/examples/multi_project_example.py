"""
Multi-Project Autonomous Build Example

This demonstrates how to use Autopack to build multiple isolated projects.
Each project has its own directory and .autonomous_runs tracking.

Usage:
    python examples/multi_project_example.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.supervisor import Supervisor


def create_project_if_not_exists(project_path: str) -> None:
    """Create project directory and initialize git if it doesn't exist"""
    project = Path(project_path)

    if not project.exists():
        print(f"[Setup] Creating project directory: {project_path}")
        project.mkdir(parents=True, exist_ok=True)

        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=project_path, check=True)

        # Create README
        (project / "README.md").write_text(f"# {project.name}\n\nAutonomous build project\n")
        subprocess.run(["git", "add", "README.md"], cwd=project_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_path, check=True)

        print("[Setup] ✅ Project initialized with git")
    else:
        print(f"[Setup] Project already exists: {project_path}")


def build_project_a():
    """Build Project A: Simple FastAPI web service"""

    project_path = "c:\\Projects\\web-service"
    create_project_if_not_exists(project_path)

    supervisor = Supervisor(
        api_url="http://localhost:8000",
        target_repo_path=project_path  # ← Isolated to this project
    )

    # Define build plan
    tiers = [
        {
            "tier_id": "T1",
            "tier_index": 0,
            "name": "Foundation",
            "description": "Basic FastAPI setup",
        }
    ]

    phases = [
        {
            "phase_id": "P1.1",
            "phase_index": 0,
            "tier_id": "T1",
            "name": "Create FastAPI App",
            "description": "Create a basic FastAPI application with main.py, health check endpoint, and uvicorn server setup",
            "task_category": "feature_scaffolding",
            "complexity": "low",
            "acceptance_criteria": [
                "main.py exists with FastAPI app",
                "/health endpoint returns 200",
                "Can start with: uvicorn main:app"
            ],
        },
        {
            "phase_id": "P1.2",
            "phase_index": 1,
            "tier_id": "T1",
            "name": "Add Logging",
            "description": "Add structured logging to the application using Python's logging module",
            "task_category": "feature_scaffolding",
            "complexity": "low",
            "acceptance_criteria": [
                "Logging configured in main.py",
                "Logs to console with timestamps",
                "Log levels configured (INFO, DEBUG, ERROR)"
            ],
        },
    ]

    # Run autonomous build
    result = supervisor.run_autonomous_build(
        run_id="web-service-v1",
        tiers=tiers,
        phases=phases,
        safety_profile="normal",
    )

    return result


def build_project_b():
    """Build Project B: Data processing pipeline"""

    project_path = "c:\\Projects\\data-pipeline"
    create_project_if_not_exists(project_path)

    supervisor = Supervisor(
        api_url="http://localhost:8000",
        target_repo_path=project_path  # ← Isolated to this project
    )

    # Define build plan
    tiers = [
        {
            "tier_id": "T1",
            "tier_index": 0,
            "name": "Pipeline Foundation",
            "description": "Basic data pipeline structure",
        }
    ]

    phases = [
        {
            "phase_id": "P1.1",
            "phase_index": 0,
            "tier_id": "T1",
            "name": "Create Pipeline Class",
            "description": "Create a DataPipeline class with extract, transform, load methods and CSV file reading capability",
            "task_category": "feature_scaffolding",
            "complexity": "medium",
            "acceptance_criteria": [
                "pipeline.py exists with DataPipeline class",
                "extract() method reads CSV files",
                "transform() method processes data",
                "load() method writes output"
            ],
        },
    ]

    # Run autonomous build
    result = supervisor.run_autonomous_build(
        run_id="data-pipeline-v1",
        tiers=tiers,
        phases=phases,
        safety_profile="normal",
    )

    return result


def main():
    """Run multiple isolated autonomous builds"""

    print("="*70)
    print("Multi-Project Autonomous Build Example")
    print("="*70)
    print()
    print("This will create two isolated projects:")
    print("  1. c:\\Projects\\web-service     - FastAPI web service")
    print("  2. c:\\Projects\\data-pipeline   - Data processing pipeline")
    print()
    print("Each project will have:")
    print("  - Its own git repository")
    print("  - Its own .autonomous_runs/ directory")
    print("  - Its own source code")
    print()

    choice = input("Which project to build? (1=web-service, 2=data-pipeline, 3=both): ")

    if choice == "1":
        print("\n[Building] Project A: Web Service")
        result_a = build_project_a()
        print(f"\n✅ Project A completed: {result_a['run_id']}")

    elif choice == "2":
        print("\n[Building] Project B: Data Pipeline")
        result_b = build_project_b()
        print(f"\n✅ Project B completed: {result_b['run_id']}")

    elif choice == "3":
        print("\n[Building] Both projects")

        print("\n--- Project A: Web Service ---")
        result_a = build_project_a()
        print(f"✅ Project A completed: {result_a['run_id']}")

        print("\n--- Project B: Data Pipeline ---")
        result_b = build_project_b()
        print(f"✅ Project B completed: {result_b['run_id']}")

        print("\n" + "="*70)
        print("Both projects built successfully!")
        print("="*70)

    else:
        print("Invalid choice. Exiting.")


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    main()
