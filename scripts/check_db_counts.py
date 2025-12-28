"""Quick database phase count check."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState

session = SessionLocal()
try:
    total = session.query(Phase).count()
    print(f"Total phases: {total}")

    for state in PhaseState:
        count = session.query(Phase).filter(Phase.state == state).count()
        if count > 0:
            print(f"  {state.value}: {count}")
finally:
    session.close()
