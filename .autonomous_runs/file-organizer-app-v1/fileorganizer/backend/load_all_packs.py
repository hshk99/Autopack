#!/usr/bin/env python3
"""
Load all pack templates into database
"""
from pathlib import Path
from app.db.session import SessionLocal, init_db
from app.services.pack_service import ScenarioPackService

def main():
    print("Initializing database...")
    init_db()

    db = SessionLocal()
    service = ScenarioPackService(db)

    packs_dir = Path("packs")
    yaml_files = list(packs_dir.glob("*.yaml"))

    print(f"\nFound {len(yaml_files)} pack templates:\n")

    for yaml_file in yaml_files:
        try:
            pack = service.load_pack_from_yaml(yaml_file)
            categories = service.get_pack_categories(pack.id)
            print(f"[OK] Loaded: {pack.name} ({len(categories)} categories)")
        except Exception as e:
            print(f"[ERROR] Failed to load {yaml_file.name}: {str(e)}")

    db.close()
    print("\n[OK] Pack loading complete!")

if __name__ == "__main__":
    main()
