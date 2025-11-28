
from app.db.session import SessionLocal, init_db
from app.services.pack_service import ScenarioPackService
from pathlib import Path

init_db()
db = SessionLocal()
service = ScenarioPackService(db)
pack = service.load_pack_from_yaml(Path("packs/tax_generic.yaml"))
print(f"[OK] Loaded pack: {pack.name}")
db.close()
