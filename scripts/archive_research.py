#!/usr/bin/env python3
import shutil
from pathlib import Path

# Repo root detection for dynamic paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def archive_research_files():
    base_dir = REPO_ROOT
    research_dir = base_dir / ".autonomous_runs/file-organizer-app-v1/docs/research"
    superseded_dir = research_dir / "superseded"
    superseded_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing {research_dir}...")
    
    for file_path in research_dir.glob("*"):
        if file_path.name == "superseded":
            continue
            
        if file_path.is_file():
            dest = superseded_dir / file_path.name
            print(f"  Moving {file_path.name} -> superseded/")
            shutil.move(str(file_path), str(dest))

if __name__ == "__main__":
    archive_research_files()

