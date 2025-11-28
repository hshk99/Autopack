"""
Scenario Pack Service - Load and manage YAML pack templates
"""
import yaml
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.scenario_pack import ScenarioPack
from app.models.category import Category
from app.services.cache_service import cache


class ScenarioPackService:
    def __init__(self, db: Session):
        self.db = db
        self.packs_dir = Path("packs")
        self.packs_dir.mkdir(exist_ok=True)

    def load_pack_from_yaml(self, yaml_path: Path) -> ScenarioPack:
        """
        Load scenario pack from YAML file
        """
        with open(yaml_path, 'r') as f:
            pack_data = yaml.safe_load(f)

        # Create or update scenario pack
        pack = self.db.query(ScenarioPack).filter(
            ScenarioPack.name == pack_data['name']
        ).first()

        if not pack:
            pack = ScenarioPack(
                name=pack_data['name'],
                description=pack_data.get('description', ''),
                template_path=str(yaml_path)
            )
            self.db.add(pack)
            self.db.commit()
            self.db.refresh(pack)

        # Create categories
        for cat_data in pack_data.get('categories', []):
            category = self.db.query(Category).filter(
                Category.name == cat_data['name'],
                Category.scenario_pack_id == pack.id
            ).first()

            if not category:
                category = Category(
                    name=cat_data['name'],
                    description=cat_data.get('description', ''),
                    scenario_pack_id=pack.id,
                    example_documents=str(cat_data.get('examples', []))
                )
                self.db.add(category)

        self.db.commit()
        return pack

    def list_packs(self) -> list[ScenarioPack]:
        """List all available scenario packs (with caching)"""
        cached = cache.get('all_packs')
        if cached:
            return cached

        packs = self.db.query(ScenarioPack).all()
        cache.set('all_packs', packs, ttl_seconds=600)  # Cache for 10 minutes
        return packs

    def _list_packs_uncached(self) -> list[ScenarioPack]:
        """List all available scenario packs"""
        return self.db.query(ScenarioPack).all()

    def get_pack(self, pack_id: int) -> ScenarioPack:
        """Get scenario pack by ID"""
        return self.db.query(ScenarioPack).filter(ScenarioPack.id == pack_id).first()

    def get_pack_categories(self, pack_id: int) -> list[Category]:
        """Get all categories for a pack"""
        return self.db.query(Category).filter(Category.scenario_pack_id == pack_id).all()
