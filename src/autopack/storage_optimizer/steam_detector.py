"""
Steam Game Detector for Storage Optimizer (BUILD-151 Phase 4)

Detects installed Steam games and identifies cleanup opportunities.
Addresses user's original request: "detect and suggest moving large uninstalled games"
"""

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
    last_updated: Optional[datetime]
    installed: bool = True

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024**3)

    @property
    def age_days(self) -> Optional[int]:
        """Days since last update/play."""
        if not self.last_updated:
            return None
        return (datetime.now() - self.last_updated).days


class SteamGameDetector:
    """
    Detect Steam games and analyze usage patterns.

    Addresses user's original request for detecting large uninstalled/unused games.
    """

    def __init__(self):
        self.steam_path = self._find_steam_installation()
        self.library_folders = self._find_library_folders()

    def _find_steam_installation(self) -> Optional[Path]:
        """Find Steam installation via Windows registry."""
        try:
            # Try HKEY_CURRENT_USER first (most common)
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            winreg.CloseKey(key)
            return Path(steam_path)
        except (FileNotFoundError, OSError):
            pass

        # Try HKEY_LOCAL_MACHINE as fallback
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            install_path = winreg.QueryValueEx(key, "InstallPath")[0]
            winreg.CloseKey(key)
            return Path(install_path)
        except (FileNotFoundError, OSError):
            return None

    def _find_library_folders(self) -> List[Path]:
        """Find all Steam library folders (including external drives)."""
        if not self.steam_path:
            return []

        library_folders = [self.steam_path / "steamapps"]

        # Parse libraryfolders.vdf for additional libraries
        vdf_path = self.steam_path / "steamapps" / "libraryfolders.vdf"
        if vdf_path.exists():
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Simple VDF parsing (format: "path"    "C:\\SteamLibrary")
                for line in content.split("\n"):
                    if '"path"' in line.lower():
                        # Extract path between quotes
                        parts = line.split('"')
                        if len(parts) >= 4:
                            path_str = parts[3].replace("\\\\", "\\")
                            lib_path = Path(path_str) / "steamapps"
                            if lib_path.exists() and lib_path not in library_folders:
                                library_folders.append(lib_path)
            except Exception as e:
                print(f"Warning: Failed to parse libraryfolders.vdf: {e}")

        return library_folders

    def detect_installed_games(self) -> List[SteamGame]:
        """
        Detect all installed Steam games.

        Returns list of SteamGame objects with metadata.
        """
        if not self.steam_path:
            return []

        games = []

        for library in self.library_folders:
            if not library.exists():
                continue

            # Scan for .acf manifest files (appmanifest_<appid>.acf)
            try:
                for acf_file in library.glob("appmanifest_*.acf"):
                    game = self._parse_manifest(acf_file, library)
                    if game:
                        games.append(game)
            except PermissionError:
                print(f"Warning: No permission to read {library}")
                continue

        return games

    def _parse_manifest(self, acf_path: Path, library_path: Path) -> Optional[SteamGame]:
        """
        Parse Steam .acf manifest file.

        Format example:
        "AppState"
        {
            "appid"        "271590"
            "name"         "Grand Theft Auto V"
            "installdir"   "Grand Theft Auto V"
            "LastUpdated"  "1609459200"
        }
        """
        try:
            with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Extract key fields using simple VDF parsing
            app_id = self._extract_vdf_value(content, "appid")
            name = self._extract_vdf_value(content, "name")
            install_dir = self._extract_vdf_value(content, "installdir")
            last_updated = self._extract_vdf_value(content, "LastUpdated")

            if not all([app_id, name, install_dir]):
                return None

            # Calculate game size
            game_path = library_path / "common" / install_dir
            if not game_path.exists():
                return None

            size_bytes = self._calculate_directory_size(game_path)

            # Convert timestamp to datetime
            last_updated_dt = None
            if last_updated:
                try:
                    last_updated_dt = datetime.fromtimestamp(int(last_updated))
                except (ValueError, OSError):
                    pass

            return SteamGame(
                app_id=app_id,
                name=name,
                install_dir=game_path,
                size_bytes=size_bytes,
                last_updated=last_updated_dt,
                installed=True,
            )

        except Exception as e:
            print(f"Warning: Failed to parse {acf_path.name}: {e}")
            return None

    def _extract_vdf_value(self, content: str, key: str) -> Optional[str]:
        """Extract value from VDF key-value pair."""
        # Look for: "key"    "value"
        for line in content.split("\n"):
            if f'"{key}"' in line:
                # Split by quotes and get the value (4th element)
                parts = line.split('"')
                if len(parts) >= 4:
                    return parts[3]
        return None

    def _calculate_directory_size(self, path: Path) -> int:
        """Calculate total size of directory in bytes."""
        total_size = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except (PermissionError, FileNotFoundError):
                        continue
        except PermissionError:
            pass
        return total_size

    def find_unplayed_games(
        self, min_size_gb: float = 10.0, min_age_days: int = 180
    ) -> List[SteamGame]:
        """
        Find large games not played/updated in a while.

        Args:
            min_size_gb: Minimum game size in GB (default 10GB)
            min_age_days: Minimum days since last update (default 180 days = 6 months)

        Returns:
            List of games sorted by size descending (largest first)
        """
        games = self.detect_installed_games()
        cutoff = datetime.now() - timedelta(days=min_age_days)
        min_size_bytes = min_size_gb * 1024**3

        candidates = []
        for game in games:
            # Check size threshold
            if game.size_bytes < min_size_bytes:
                continue

            # Check last updated/played
            if game.last_updated and game.last_updated < cutoff:
                candidates.append(game)
            elif not game.last_updated:
                # No timestamp = very old or never played
                candidates.append(game)

        # Sort by size descending (largest games first)
        candidates.sort(key=lambda g: g.size_bytes, reverse=True)
        return candidates

    def generate_cleanup_recommendation(
        self,
        games: Optional[List[SteamGame]] = None,
        min_size_gb: float = 10.0,
        min_age_days: int = 180,
    ) -> Dict:
        """
        Generate cleanup recommendation for Steam games.

        Returns dict with recommendation details suitable for display.
        """
        if games is None:
            games = self.find_unplayed_games(min_size_gb, min_age_days)

        if not games:
            return {
                "category": "steam_games_unused",
                "description": "No unused Steam games found",
                "count": 0,
                "total_size_gb": 0.0,
                "games": [],
                "recommendation": "All Steam games are recent or below size threshold",
                "action": None,
                "requires_approval": False,
            }

        total_size = sum(g.size_bytes for g in games)
        total_size_gb = total_size / (1024**3)

        return {
            "category": "steam_games_unused",
            "description": f"Steam games not updated in {min_age_days}+ days",
            "count": len(games),
            "total_size_gb": total_size_gb,
            "games": [
                {
                    "name": g.name,
                    "app_id": g.app_id,
                    "size_gb": g.size_gb,
                    "last_updated": g.last_updated.isoformat() if g.last_updated else None,
                    "age_days": g.age_days,
                    "install_dir": str(g.install_dir),
                }
                for g in games[:20]  # Limit to top 20
            ],
            "recommendation": (
                f"Consider uninstalling {len(games)} Steam games to free up {total_size_gb:.1f} GB. "
                f"Games can be reinstalled later from your Steam library at any time."
            ),
            "action": "suggest_uninstall",
            "requires_approval": True,
            "safety_note": "Uninstalling from Steam is safe - all games remain in your library and can be reinstalled",
        }

    def is_available(self) -> bool:
        """Check if Steam is installed and accessible."""
        return self.steam_path is not None and self.steam_path.exists()

    def get_total_steam_size(self) -> int:
        """Get total size of all installed Steam games in bytes."""
        games = self.detect_installed_games()
        return sum(g.size_bytes for g in games)


def main():
    """CLI demo of Steam game detection."""
    detector = SteamGameDetector()

    if not detector.is_available():
        print("Steam not found on this system")
        print("Install Steam from: https://store.steampowered.com/about/")
        return

    print("Steam Game Detector")
    print("=" * 80)
    print(f"Steam path: {detector.steam_path}")
    print(f"Library folders: {len(detector.library_folders)}")
    for lib in detector.library_folders:
        print(f"  - {lib}")
    print("")

    print("Detecting installed games...")
    games = detector.detect_installed_games()
    print(f"Found {len(games)} installed games")
    print("")

    total_size = sum(g.size_bytes for g in games)
    print(f"Total installed: {total_size / (1024**3):.1f} GB")
    print("")

    print("Analyzing cleanup opportunities...")
    unused = detector.find_unplayed_games(min_size_gb=10.0, min_age_days=180)

    if unused:
        print(f"\nFound {len(unused)} games not updated in 6+ months (≥10GB):")
        print("=" * 80)
        for i, game in enumerate(unused[:10], 1):
            age_str = f"{game.age_days}d ago" if game.age_days else "unknown"
            print(f"{i:2d}. {game.name:40s} {game.size_gb:6.1f} GB  ({age_str})")

        recommendation = detector.generate_cleanup_recommendation(unused)
        print("")
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        print(recommendation["recommendation"])
        print(f"Potential savings: {recommendation['total_size_gb']:.1f} GB")
    else:
        print("No cleanup opportunities found (all games recent or small)")


if __name__ == "__main__":
    main()
