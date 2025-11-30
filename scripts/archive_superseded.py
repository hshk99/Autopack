
import os
import shutil
from pathlib import Path

def archive_files(directory):
    directory = Path(directory)
    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    superseded_dir = directory / "superseded"
    superseded_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {directory}...")
    
    # Files to KEEP
    keep_patterns = ["CONSOLIDATED_*.md", "ARCHIVE_INDEX.md", "README.md", "superseded"]
    
    for file_path in directory.glob("*"):
        if file_path.name == "superseded":
            continue
            
        is_consolidated = file_path.name.startswith("CONSOLIDATED_")
        is_index = file_path.name == "ARCHIVE_INDEX.md"
        is_readme = file_path.name == "README.md"
        
        if is_consolidated or is_index or is_readme:
            print(f"  Keeping: {file_path.name}")
            continue
            
        if file_path.is_file():
            dest = superseded_dir / file_path.name
            print(f"  Moving {file_path.name} -> superseded/")
            shutil.move(str(file_path), str(dest))

if __name__ == "__main__":
    base_dir = Path("c:/dev/Autopack")
    archive_files(base_dir / "archive")
    archive_files(base_dir / ".autonomous_runs/file-organizer-app-v1/archive")

