
import shutil
from pathlib import Path

def archive_specific_files():
    base_dir = Path("c:/dev/Autopack")
    target_dir = base_dir / ".autonomous_runs/file-organizer-app-v1/archive"
    superseded_dir = target_dir / "superseded"
    superseded_dir.mkdir(parents=True, exist_ok=True)
    
    files_to_move = [
        "CONSOLIDATED_DEBUG_AND_ERRORS.md",
        "CONSOLIDATED_BUILD_HISTORY.md",
        "CONSOLIDATED_STRATEGIC_ANALYSIS.md"
    ]
    
    for filename in files_to_move:
        src = target_dir / filename
        if src.exists():
            dest = superseded_dir / filename
            print(f"Moving {filename} -> superseded/")
            shutil.move(str(src), str(dest))
        else:
            print(f"File not found: {filename}")

if __name__ == "__main__":
    archive_specific_files()

