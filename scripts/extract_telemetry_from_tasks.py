"""
Extract telemetry from background task output files.
"""
import re
from pathlib import Path

def extract_telemetry(task_ids):
    """Extract [TokenEstimationV2] telemetry from task output files."""
    telemetry_samples = []
    task_dir = Path(r"C:\Users\hshk9\AppData\Local\Temp\claude\c--dev-Autopack\tasks")

    for task_id in task_ids:
        output_file = task_dir / f"{task_id}.output"
        if not output_file.exists():
            print(f"Task {task_id}: output file not found")
            continue

        try:
            content = output_file.read_text(encoding='utf-8', errors='ignore')
            samples = []
            for line in content.split('\n'):
                if '[TokenEstimationV2]' in line:
                    samples.append(line.strip())

            print(f"Task {task_id}: {len(samples)} telemetry samples")
            for sample in samples:
                # Extract metadata
                match = re.search(
                    r'predicted_output=(\d+) actual_output=(\d+) smape=([\d.]+)% .* category=(\w+) complexity=(\w+) deliverables=(\d+)',
                    sample
                )
                if match:
                    pred, actual, smape, category, complexity, deliverables = match.groups()
                    print(f"  - {category}/{complexity}/{deliverables}d: pred={pred}, actual={actual}, SMAPE={smape}%")
                telemetry_samples.append(sample)

        except Exception as e:
            print(f"Task {task_id}: error reading - {e}")

    return telemetry_samples

def main():
    print("BUILD-129 Phase 3: Telemetry Extraction")
    print("=" * 80)

    # Task IDs for Lovable P1 and P2
    task_ids = [
        "b43be62",  # Lovable P1
        "ba24bff"   # Lovable P2
    ]

    telemetry = extract_telemetry(task_ids)

    print("\n" + "=" * 80)
    print(f"Total samples extracted: {len(telemetry)}")
    print("\nTo append to dataset:")
    print("  Copy samples to build132_telemetry_samples.txt")

    return telemetry

if __name__ == "__main__":
    samples = main()
