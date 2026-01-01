---
build: BUILD-151
phase: Phase 4 - Intelligence & Auto-Learning
status: Planned
date: 2026-01-02
author: AI Assistant (Claude Sonnet 4.5)
---

# Storage Optimizer Phase 4 Implementation Plan

## Executive Summary

**BUILD-151** will extend Storage Optimizer with intelligent features that learn from user approval patterns, provide strategic cleanup recommendations, and automatically detect specialized cleanup opportunities like uninstalled Steam games.

### Goals

1. **Category Auto-Learning** - Suggest new policy rules based on approval patterns
2. **LLM-Powered Smart Categorization** - Intelligent category detection for edge cases (~2K tokens per 100 files)
3. **Steam Game Detection** - Specialized detection of uninstalled/unused games (addresses user's original request)
4. **Approval Pattern Analysis** - Learn which categories user typically approves/rejects
5. **Strategic Recommendations** - Provide context-aware cleanup suggestions

### Key Metrics

| Metric | Target |
|--------|--------|
| Rule suggestion accuracy | ≥ 80% |
| LLM token efficiency | ≤ 2K tokens / 100 files |
| Steam game detection accuracy | ≥ 95% |
| Auto-learning policy improvement | 20% reduction in manual approvals |

---

## Phase 4 Components

### Component 1: Approval Pattern Analyzer

**Purpose**: Learn from user approval/rejection patterns to suggest policy improvements.

**Database Schema Extension**:
```sql
-- Add to cleanup_candidates table
ALTER TABLE cleanup_candidates
ADD COLUMN user_feedback TEXT,  -- Why approved/rejected (optional)
ADD COLUMN learned_rule_id INTEGER REFERENCES learned_rules(id);

-- New table for learned rules
CREATE TABLE learned_rules (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Pattern learned from
    pattern_type VARCHAR(50) NOT NULL,  -- 'path_pattern', 'file_type', 'age_threshold', 'size_threshold'
    pattern_value TEXT NOT NULL,  -- e.g., '**/node_modules/**/*.log', '*.tmp', 'age > 180', 'size > 5GB'

    -- Classification
    suggested_category VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(3, 2) NOT NULL,  -- 0.00-1.00

    -- Evidence
    based_on_approvals INTEGER NOT NULL,  -- Number of approvals supporting this rule
    based_on_rejections INTEGER NOT NULL,  -- Number of rejections contradicting this rule
    sample_paths TEXT[],  -- Example paths that triggered this learning

    -- Lifecycle
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'approved', 'rejected', 'applied'
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP,
    applied_to_policy_version VARCHAR(50),

    -- Notes
    description TEXT,  -- Human-readable explanation of the rule
    notes TEXT
);

CREATE INDEX idx_learned_rules_status ON learned_rules(status);
CREATE INDEX idx_learned_rules_confidence ON learned_rules(confidence_score DESC);
```

**Implementation**:

**File**: `src/autopack/storage_optimizer/approval_analyzer.py` (NEW, ~400 lines)

```python
from typing import List, Dict, Optional
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from autopack.models import CleanupCandidate, ApprovalDecision, LearnedRule
from autopack.storage_optimizer.policy import StoragePolicy


@dataclass
class ApprovalPattern:
    """Represents a learned approval pattern."""
    pattern_type: str  # 'path_pattern', 'file_type', 'age_threshold', 'size_threshold'
    pattern_value: str
    category: str
    approval_rate: float  # 0.0-1.0
    sample_count: int
    sample_paths: List[str]


class ApprovalPatternAnalyzer:
    """Analyzes approval history to suggest policy improvements."""

    def __init__(self, db: Session, policy: StoragePolicy):
        self.db = db
        self.policy = policy

    def analyze_approval_history(
        self,
        min_samples: int = 5,
        min_confidence: float = 0.80,
        lookback_days: int = 90
    ) -> List[ApprovalPattern]:
        """
        Analyze approval/rejection history to find patterns.

        Returns patterns that could become policy rules.
        """
        cutoff = datetime.now() - timedelta(days=lookback_days)

        # Get all approved/rejected candidates from recent scans
        candidates = self.db.query(CleanupCandidate).join(
            ApprovalDecision
        ).filter(
            ApprovalDecision.approved_at >= cutoff,
            CleanupCandidate.approval_status.in_(['approved', 'rejected'])
        ).all()

        # Group by different pattern types
        patterns = []
        patterns.extend(self._find_path_patterns(candidates, min_samples, min_confidence))
        patterns.extend(self._find_file_type_patterns(candidates, min_samples, min_confidence))
        patterns.extend(self._find_age_patterns(candidates, min_samples, min_confidence))
        patterns.extend(self._find_size_patterns(candidates, min_samples, min_confidence))

        return patterns

    def _find_path_patterns(
        self,
        candidates: List[CleanupCandidate],
        min_samples: int,
        min_confidence: float
    ) -> List[ApprovalPattern]:
        """Find patterns in file paths."""
        # Group by path components
        path_groups = defaultdict(lambda: {'approved': [], 'rejected': []})

        for candidate in candidates:
            # Extract path segments (e.g., node_modules, .cache, build, dist)
            path_parts = candidate.path.replace('\\', '/').split('/')

            # Check each interesting path component
            for part in path_parts:
                if part and not part[0].isdigit():  # Skip version numbers
                    key = f"*/{part}/*"
                    if candidate.approval_status == 'approved':
                        path_groups[key]['approved'].append(candidate.path)
                    else:
                        path_groups[key]['rejected'].append(candidate.path)

        # Find patterns with high approval rates
        patterns = []
        for path_pattern, paths in path_groups.items():
            approved_count = len(paths['approved'])
            rejected_count = len(paths['rejected'])
            total = approved_count + rejected_count

            if total >= min_samples:
                approval_rate = approved_count / total
                if approval_rate >= min_confidence or approval_rate <= (1 - min_confidence):
                    # Determine most common category for approved items
                    if approved_count > 0:
                        approved_candidates = [
                            c for c in candidates
                            if c.path in paths['approved']
                        ]
                        category_counts = Counter(c.category for c in approved_candidates)
                        most_common_category = category_counts.most_common(1)[0][0]

                        patterns.append(ApprovalPattern(
                            pattern_type='path_pattern',
                            pattern_value=path_pattern,
                            category=most_common_category,
                            approval_rate=approval_rate,
                            sample_count=total,
                            sample_paths=paths['approved'][:10]  # Keep top 10 examples
                        ))

        return patterns

    def _find_file_type_patterns(self, candidates, min_samples, min_confidence):
        """Find patterns in file extensions."""
        # Group by file extension
        ext_groups = defaultdict(lambda: {'approved': [], 'rejected': []})

        for candidate in candidates:
            ext = candidate.path.split('.')[-1].lower() if '.' in candidate.path else ''
            if ext:
                if candidate.approval_status == 'approved':
                    ext_groups[f"*.{ext}"]["approved'].append(candidate)
                else:
                    ext_groups[f"*.{ext}"]["rejected'].append(candidate)

        # Similar pattern detection logic as path patterns
        # ... (implementation omitted for brevity)
        return []

    def _find_age_patterns(self, candidates, min_samples, min_confidence):
        """Find patterns in file age thresholds."""
        # Group by age buckets (30, 60, 90, 180, 365 days)
        # ... (implementation omitted for brevity)
        return []

    def _find_size_patterns(self, candidates, min_samples, min_confidence):
        """Find patterns in file size thresholds."""
        # Group by size buckets (1MB, 10MB, 100MB, 1GB)
        # ... (implementation omitted for brevity)
        return []

    def suggest_policy_rules(self, patterns: List[ApprovalPattern]) -> List[Dict]:
        """
        Convert approval patterns into suggested policy rules.

        Returns list of rule suggestions in policy YAML format.
        """
        suggestions = []

        for pattern in patterns:
            suggestion = {
                'pattern_type': pattern.pattern_type,
                'pattern_value': pattern.pattern_value,
                'category': pattern.category,
                'confidence': pattern.approval_rate,
                'evidence': {
                    'sample_count': pattern.sample_count,
                    'sample_paths': pattern.sample_paths,
                },
                'proposed_rule': self._generate_yaml_rule(pattern)
            }
            suggestions.append(suggestion)

        return suggestions

    def _generate_yaml_rule(self, pattern: ApprovalPattern) -> str:
        """Generate YAML policy rule from pattern."""
        if pattern.pattern_type == 'path_pattern':
            return f"""
  - name: "Auto-learned: {pattern.pattern_value}"
    path_pattern: "{pattern.pattern_value}"
    category: {pattern.category}
    min_age_days: 30
    requires_approval: false
    notes: "Learned from {pattern.sample_count} approvals ({pattern.approval_rate:.0%} approval rate)"
"""
        # ... other pattern types
        return ""

    def save_learned_rules(self, patterns: List[ApprovalPattern]) -> List[int]:
        """Save learned rules to database for review."""
        rule_ids = []

        for pattern in patterns:
            rule = LearnedRule(
                pattern_type=pattern.pattern_type,
                pattern_value=pattern.pattern_value,
                suggested_category=pattern.category,
                confidence_score=pattern.approval_rate,
                based_on_approvals=len([p for p in pattern.sample_paths]),
                based_on_rejections=0,  # TODO: track rejections
                sample_paths=pattern.sample_paths,
                status='pending',
                description=self._generate_description(pattern)
            )
            self.db.add(rule)
            self.db.commit()
            rule_ids.append(rule.id)

        return rule_ids

    def _generate_description(self, pattern: ApprovalPattern) -> str:
        """Generate human-readable description of learned rule."""
        return f"Files matching {pattern.pattern_value} are typically approved as '{pattern.category}' ({pattern.approval_rate:.0%} of {pattern.sample_count} samples)"
```

---

### Component 2: LLM-Powered Smart Categorization

**Purpose**: Use LLM for edge cases where rule-based classification fails.

**Token Budget**: ~2K tokens per 100 files (conservative estimate)

**Implementation**:

**File**: `src/autopack/storage_optimizer/smart_categorizer.py` (NEW, ~350 lines)

```python
from typing import List, Dict, Optional
from anthropic import Anthropic
from dataclasses import dataclass
import json

from autopack.storage_optimizer.models import ScanResult
from autopack.storage_optimizer.policy import StoragePolicy


@dataclass
class SmartCategorizationResult:
    """Result of LLM categorization."""
    path: str
    suggested_category: str
    confidence: float  # 0.0-1.0
    reasoning: str
    alternative_categories: List[tuple[str, float]]  # [(category, confidence)]


class SmartCategorizer:
    """LLM-powered categorization for edge cases."""

    def __init__(self, policy: StoragePolicy, api_key: Optional[str] = None):
        self.policy = policy
        self.client = Anthropic(api_key=api_key) if api_key else None

    def categorize_batch(
        self,
        uncategorized_items: List[ScanResult],
        max_items: int = 100
    ) -> List[SmartCategorizationResult]:
        """
        Categorize a batch of files using LLM.

        Uses efficient batching to minimize token usage.
        Target: ~2K tokens for 100 files.
        """
        if not self.client:
            raise ValueError("LLM API key not configured")

        # Prepare batch (limit to max_items)
        batch = uncategorized_items[:max_items]

        # Build compact representation
        file_list = self._build_compact_file_list(batch)

        # Build prompt
        prompt = self._build_categorization_prompt(file_list)

        # Call LLM
        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response
        results = self._parse_categorization_response(response.content[0].text, batch)

        return results

    def _build_compact_file_list(self, items: List[ScanResult]) -> str:
        """Build compact representation of files for LLM."""
        lines = []
        for i, item in enumerate(items, 1):
            # Extract key info: path, size, age
            size_mb = item.size_bytes / (1024 * 1024)
            age_days = item.age_days if hasattr(item, 'age_days') else '?'

            # Compact format: ID | Size | Age | Path
            line = f"{i}. {size_mb:.1f}MB | {age_days}d | {item.path}"
            lines.append(line)

        return "\n".join(lines)

    def _build_categorization_prompt(self, file_list: str) -> str:
        """Build LLM prompt for categorization."""
        categories = ", ".join(self.policy.get_category_names())

        return f"""You are a file categorization assistant. Categorize each file into one of these categories:

Categories: {categories}

Files to categorize:
{file_list}

For each file, provide:
1. Category (from list above)
2. Confidence (0.0-1.0)
3. Brief reasoning (1 sentence)

Output format (JSON array):
[
  {{"id": 1, "category": "dev_caches", "confidence": 0.95, "reasoning": "node_modules is a dev cache"}},
  ...
]

Be concise. Focus on path patterns, file types, and common dev/system conventions."""

    def _parse_categorization_response(
        self,
        response_text: str,
        original_items: List[ScanResult]
    ) -> List[SmartCategorizationResult]:
        """Parse LLM JSON response into results."""
        try:
            categorizations = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback: extract JSON from markdown code blocks
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0]
                categorizations = json.loads(json_text)
            else:
                raise

        results = []
        for cat in categorizations:
            item_id = cat['id'] - 1  # Convert 1-indexed to 0-indexed
            if item_id < len(original_items):
                item = original_items[item_id]
                results.append(SmartCategorizationResult(
                    path=item.path,
                    suggested_category=cat['category'],
                    confidence=cat['confidence'],
                    reasoning=cat['reasoning'],
                    alternative_categories=[]  # Could be extended
                ))

        return results
```

---

### Component 3: Steam Game Detector

**Purpose**: Detect uninstalled/unused Steam games for strategic cleanup (addresses user's original request).

**Implementation**:

**File**: `src/autopack/storage_optimizer/steam_detector.py` (NEW, ~300 lines)

```python
import os
import json
import winreg
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SteamGame:
    """Represents a Steam game installation."""
    app_id: str
    name: str
    install_dir: Path
    size_bytes: int
    last_played: Optional[datetime]
    play_time_hours: float
    installed: bool


class SteamGameDetector:
    """Detect Steam games and analyze usage patterns."""

    def __init__(self):
        self.steam_path = self._find_steam_installation()
        self.library_folders = self._find_library_folders()

    def _find_steam_installation(self) -> Optional[Path]:
        """Find Steam installation via registry."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Valve\Steam"
            )
            steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            return Path(steam_path)
        except FileNotFoundError:
            return None

    def _find_library_folders(self) -> List[Path]:
        """Find all Steam library folders."""
        if not self.steam_path:
            return []

        library_folders = [self.steam_path / "steamapps"]

        # Parse libraryfolders.vdf for additional libraries
        vdf_path = self.steam_path / "steamapps" / "libraryfolders.vdf"
        if vdf_path.exists():
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Simple VDF parsing (could use vdf library for robustness)
                for line in content.split('\n'):
                    if '"path"' in line:
                        path = line.split('"')[3].replace('\\\\', '\\')
                        library_folders.append(Path(path) / "steamapps")

        return library_folders

    def detect_installed_games(self) -> List[SteamGame]:
        """Detect all installed Steam games."""
        games = []

        for library in self.library_folders:
            if not library.exists():
                continue

            # Scan for .acf manifest files
            for acf_file in library.glob("appmanifest_*.acf"):
                game = self._parse_manifest(acf_file, library)
                if game:
                    games.append(game)

        return games

    def _parse_manifest(self, acf_path: Path, library_path: Path) -> Optional[SteamGame]:
        """Parse Steam .acf manifest file."""
        try:
            with open(acf_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract app_id, name, installdir
            app_id = self._extract_vdf_value(content, 'appid')
            name = self._extract_vdf_value(content, 'name')
            install_dir = self._extract_vdf_value(content, 'installdir')
            last_updated = self._extract_vdf_value(content, 'LastUpdated')

            if not all([app_id, name, install_dir]):
                return None

            # Calculate game size
            game_path = library_path / "common" / install_dir
            if not game_path.exists():
                return None

            size_bytes = self._calculate_directory_size(game_path)

            # Get play time from Steam API or local cache (simplified)
            last_played = datetime.fromtimestamp(int(last_updated)) if last_updated else None

            return SteamGame(
                app_id=app_id,
                name=name,
                install_dir=game_path,
                size_bytes=size_bytes,
                last_played=last_played,
                play_time_hours=0.0,  # Would need Steam API for accurate data
                installed=True
            )
        except Exception as e:
            print(f"Error parsing {acf_path}: {e}")
            return None

    def _extract_vdf_value(self, content: str, key: str) -> Optional[str]:
        """Extract value from VDF key-value pair."""
        for line in content.split('\n'):
            if f'"{key}"' in line:
                parts = line.split('"')
                if len(parts) >= 4:
                    return parts[3]
        return None

    def _calculate_directory_size(self, path: Path) -> int:
        """Calculate total size of directory."""
        total_size = 0
        try:
            for item in path.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except PermissionError:
            pass
        return total_size

    def find_unplayed_games(
        self,
        min_size_gb: float = 10.0,
        min_age_days: int = 180
    ) -> List[SteamGame]:
        """Find large games not played in a while."""
        games = self.detect_installed_games()
        cutoff = datetime.now() - timedelta(days=min_age_days)
        min_size_bytes = min_size_gb * 1024**3

        candidates = []
        for game in games:
            # Check size threshold
            if game.size_bytes < min_size_bytes:
                continue

            # Check last played (or installation date)
            if game.last_played and game.last_played < cutoff:
                candidates.append(game)
            elif not game.last_played:
                # Never played (based on manifest update time)
                candidates.append(game)

        # Sort by size descending
        candidates.sort(key=lambda g: g.size_bytes, reverse=True)
        return candidates

    def generate_cleanup_recommendation(self, games: List[SteamGame]) -> Dict:
        """Generate cleanup recommendation for Steam games."""
        total_size = sum(g.size_bytes for g in games)
        total_size_gb = total_size / (1024**3)

        return {
            'category': 'steam_games_unused',
            'description': f'Steam games not played in 6+ months',
            'count': len(games),
            'total_size_gb': total_size_gb,
            'games': [
                {
                    'name': g.name,
                    'size_gb': g.size_bytes / (1024**3),
                    'last_played': g.last_played.isoformat() if g.last_played else None,
                    'install_dir': str(g.install_dir)
                }
                for g in games
            ],
            'recommendation': (
                f"Consider uninstalling {len(games)} Steam games to free up {total_size_gb:.1f} GB. "
                "Games can be reinstalled later from your Steam library."
            ),
            'action': 'suggest_uninstall',  # Not automatic deletion
            'requires_approval': True
        }
```

---

### Component 4: Strategic Recommendation Engine

**Purpose**: Provide context-aware cleanup suggestions based on multiple intelligence sources.

**File**: `src/autopack/storage_optimizer/recommendations.py` (NEW, ~250 lines)

```python
from typing import List, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from autopack.storage_optimizer.approval_analyzer import ApprovalPatternAnalyzer
from autopack.storage_optimizer.steam_detector import SteamGameDetector
from autopack.models import StorageScan


class RecommendationEngine:
    """Generate strategic cleanup recommendations."""

    def __init__(self, db: Session):
        self.db = db
        self.approval_analyzer = ApprovalPatternAnalyzer(db, policy)
        self.steam_detector = SteamGameDetector()

    def generate_recommendations(
        self,
        scan: StorageScan
    ) -> List[Dict]:
        """Generate all recommendations for a scan."""
        recommendations = []

        # 1. Policy improvement recommendations
        policy_recs = self._recommend_policy_improvements()
        recommendations.extend(policy_recs)

        # 2. Steam game cleanup
        steam_recs = self._recommend_steam_cleanup()
        recommendations.extend(steam_recs)

        # 3. Disk usage trends
        trend_recs = self._recommend_based_on_trends()
        recommendations.extend(trend_recs)

        # Sort by potential impact
        recommendations.sort(
            key=lambda r: r.get('potential_savings_gb', 0),
            reverse=True
        )

        return recommendations

    def _recommend_policy_improvements(self) -> List[Dict]:
        """Recommend policy rule additions based on approval patterns."""
        patterns = self.approval_analyzer.analyze_approval_history(
            min_samples=5,
            min_confidence=0.80
        )

        suggestions = self.approval_analyzer.suggest_policy_rules(patterns)

        return [{
            'type': 'policy_improvement',
            'title': f"Add rule for {s['pattern_value']}",
            'description': s['proposed_rule'],
            'confidence': s['confidence'],
            'potential_benefit': 'Reduce manual approvals by ~20%',
            'action': 'review_rule'
        } for s in suggestions]

    def _recommend_steam_cleanup(self) -> List[Dict]:
        """Recommend Steam game cleanup."""
        unused_games = self.steam_detector.find_unplayed_games(
            min_size_gb=10.0,
            min_age_days=180
        )

        if not unused_games:
            return []

        recommendation = self.steam_detector.generate_cleanup_recommendation(unused_games)

        return [{
            'type': 'steam_cleanup',
            'title': f"Uninstall {recommendation['count']} unused Steam games",
            'description': recommendation['recommendation'],
            'potential_savings_gb': recommendation['total_size_gb'],
            'details': recommendation['games'],
            'action': 'suggest_uninstall'
        }]

    def _recommend_based_on_trends(self) -> List[Dict]:
        """Recommend cleanup based on disk usage trends."""
        # Compare current scan with previous scans
        previous_scans = self.db.query(StorageScan).order_by(
            StorageScan.timestamp.desc()
        ).limit(5).all()

        if len(previous_scans) < 2:
            return []

        # Analyze growth rate
        # ... (implementation omitted for brevity)

        return []
```

---

## Integration with Existing Components

### API Endpoints

**File**: `src/autopack/main.py` (+150 lines)

```python
# New endpoints for Phase 4

@app.get("/storage/recommendations/{scan_id}")
async def get_storage_recommendations(
    scan_id: int,
    db: Session = Depends(get_db)
):
    """Get intelligent recommendations for a scan."""
    scan = db.query(StorageScan).filter(StorageScan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    engine = RecommendationEngine(db)
    recommendations = engine.generate_recommendations(scan)

    return {"scan_id": scan_id, "recommendations": recommendations}


@app.get("/storage/learned-rules")
async def get_learned_rules(
    status: Optional[str] = None,
    min_confidence: float = 0.0,
    db: Session = Depends(get_db)
):
    """Get learned rules pending review."""
    query = db.query(LearnedRule)

    if status:
        query = query.filter(LearnedRule.status == status)

    query = query.filter(LearnedRule.confidence_score >= min_confidence)

    rules = query.order_by(LearnedRule.confidence_score.desc()).all()
    return {"rules": [rule_to_dict(r) for r in rules]}


@app.post("/storage/learned-rules/{rule_id}/approve")
async def approve_learned_rule(
    rule_id: int,
    approved_by: str = Query(...),
    db: Session = Depends(get_db)
):
    """Approve a learned rule and apply to policy."""
    rule = db.query(LearnedRule).filter(LearnedRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Update rule status
    rule.status = 'approved'
    rule.reviewed_by = approved_by
    rule.reviewed_at = datetime.now()

    # TODO: Apply to policy YAML file
    # This would require policy hot-reload mechanism

    db.commit()
    return {"status": "approved", "rule_id": rule_id}


@app.get("/storage/steam/games")
async def get_steam_games(
    min_size_gb: float = 0.0,
    max_age_days: Optional[int] = None
):
    """Get Steam games with optional filters."""
    detector = SteamGameDetector()

    if not detector.steam_path:
        raise HTTPException(status_code=404, detail="Steam not installed")

    games = detector.detect_installed_games()

    # Apply filters
    if min_size_gb > 0:
        games = [g for g in games if g.size_bytes >= min_size_gb * 1024**3]

    if max_age_days:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        games = [g for g in games if g.last_played and g.last_played < cutoff]

    return {
        "total_games": len(games),
        "total_size_gb": sum(g.size_bytes for g in games) / (1024**3),
        "games": [game_to_dict(g) for g in games]
    }
```

---

## CLI Integration

**File**: `scripts/storage/analyze_approvals.py` (NEW, ~150 lines)

```bash
# Analyze approval patterns and suggest policy improvements
python scripts/storage/analyze_approvals.py --min-samples 5 --min-confidence 0.80

# Generate recommendations for latest scan
python scripts/storage/analyze_approvals.py --recommendations --scan-id 123

# Detect unused Steam games
python scripts/storage/analyze_approvals.py --steam-games --min-size-gb 10 --max-age-days 180
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_approval_analyzer.py` (NEW, ~200 lines)
- Test pattern detection (path, file type, age, size)
- Test rule suggestion generation
- Test confidence scoring
- Test edge cases (low sample count, conflicting patterns)

**File**: `tests/test_smart_categorizer.py` (NEW, ~150 lines)
- Test LLM categorization (mocked)
- Test token efficiency
- Test batch processing
- Test error handling

**File**: `tests/test_steam_detector.py` (NEW, ~180 lines)
- Test Steam installation detection
- Test library folder parsing
- Test .acf manifest parsing
- Test game size calculation
- Test unused game detection

### Integration Tests

**File**: `tests/integration/test_recommendations.py` (NEW, ~120 lines)
- Test full recommendation pipeline
- Test learned rule approval workflow
- Test API endpoints

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Learning Accuracy** | ≥ 80% | User approval rate for suggested rules |
| **Token Efficiency** | ≤ 2K/100 files | Average tokens per LLM categorization batch |
| **Steam Detection Accuracy** | ≥ 95% | Correctly identified Steam games |
| **Manual Approval Reduction** | 20% | Decrease in manual approvals after rule learning |
| **Recommendation Relevance** | ≥ 70% | User-reported usefulness of recommendations |

---

## Phase 4 Timeline

1. **Database Schema Extension** (2 hours)
   - Add learned_rules table
   - Add user_feedback column
   - Create indexes

2. **Approval Pattern Analyzer** (6 hours)
   - Implement pattern detection
   - Implement rule suggestion
   - Implement database persistence

3. **LLM Smart Categorizer** (4 hours)
   - Implement batch categorization
   - Optimize token usage
   - Implement response parsing

4. **Steam Game Detector** (5 hours)
   - Implement Steam installation detection
   - Implement manifest parsing
   - Implement unused game detection

5. **Recommendation Engine** (3 hours)
   - Integrate analyzers
   - Implement ranking logic
   - Implement API endpoints

6. **Testing** (4 hours)
   - Write 18 unit tests
   - Write 4 integration tests
   - Manual testing

**Total**: ~24 hours (3 days focused work)

---

## Next Steps After Phase 4

### Phase 5 (Visualization)
- HTML reports with charts
- Treemap visualization of disk usage
- Timeline view of cleanup history
- Before/after comparisons

### Phase 6 (Cloud)
- Cloud storage integration
- Remote execution triggers
- Multi-device sync
- Centralized policy management

---

## Conclusion

Phase 4 transforms Storage Optimizer from a rule-based tool into an intelligent assistant that:
- Learns from user behavior
- Provides strategic recommendations
- Detects specialized cleanup opportunities (Steam games)
- Minimizes manual approval burden

This addresses the user's original request for Steam game detection while adding broader intelligence capabilities that improve the overall user experience.
