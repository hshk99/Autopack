"""
Tests for Steam Game Detector (BUILD-151 Phase 4)

Tests Steam installation detection, game discovery, and filtering logic.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime, timedelta


class TestSteamDetection:
    """Test Steam installation detection."""

    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    @patch("winreg.CloseKey")
    def test_find_steam_via_hkcu_registry(self, mock_close, mock_query, mock_open):
        """Test finding Steam via HKEY_CURRENT_USER registry."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        # Mock registry reads
        mock_query.return_value = ("c:/program files (x86)/steam", 1)

        detector = SteamGameDetector()

        assert detector.steam_path == Path("c:/program files (x86)/steam")
        assert detector.is_available()
        mock_open.assert_called_once()
        mock_query.assert_called_once()

    @patch("winreg.OpenKey")
    def test_find_steam_via_hklm_fallback(self, mock_open):
        """Test finding Steam via HKEY_LOCAL_MACHINE as fallback."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        # Mock HKCU failing, HKLM succeeding
        def open_key_side_effect(hkey, subkey):
            if "CURRENT_USER" in str(hkey):
                raise FileNotFoundError()
            else:
                # HKLM succeeds
                mock_key = MagicMock()
                return mock_key

        mock_open.side_effect = open_key_side_effect

        with patch("winreg.QueryValueEx", return_value=("c:/steam", 1)):
            with patch("winreg.CloseKey"):
                detector = SteamGameDetector()

                # Should fall back to HKLM
                assert detector.steam_path == Path("c:/steam")

    @patch("winreg.OpenKey", side_effect=FileNotFoundError())
    def test_steam_not_found(self, mock_open):
        """Test when Steam is not installed."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        detector = SteamGameDetector()

        assert detector.steam_path is None
        assert not detector.is_available()


class TestLibraryFolderParsing:
    """Test Steam library folder VDF parsing."""

    def test_parse_libraryfolders_vdf(self):
        """Test parsing libraryfolders.vdf file."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        vdf_content = """
        "libraryfolders"
        {
            "0"
            {
                "path"    "C:\\\\Program Files (x86)\\\\Steam"
                "label"    ""
                "contentid"    "1234567890"
            }
            "1"
            {
                "path"    "D:\\\\SteamLibrary"
                "label"    "Games"
                "contentid"    "9876543210"
            }
        }
        """

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = vdf_content

                folders = detector._parse_library_folders_vdf(
                    Path("c:/steam/steamapps/libraryfolders.vdf")
                )

                assert len(folders) == 2
                assert Path("C:/Program Files (x86)/Steam/steamapps") in folders
                assert Path("D:/SteamLibrary/steamapps") in folders

    def test_parse_empty_libraryfolders(self):
        """Test parsing empty libraryfolders.vdf."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        vdf_content = """
        "libraryfolders"
        {
        }
        """

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = vdf_content

                folders = detector._parse_library_folders_vdf(
                    Path("c:/steam/steamapps/libraryfolders.vdf")
                )

                assert len(folders) == 0


class TestGameDetection:
    """Test game manifest detection and parsing."""

    def test_parse_game_manifest(self):
        """Test parsing app manifest (acf) file."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        manifest_content = """
        "AppState"
        {
            "appid"    "570"
            "name"    "Dota 2"
            "installdir"    "dota 2 beta"
            "StateFlags"    "4"
            "LastUpdated"    "1640995200"
            "SizeOnDisk"    "50000000000"
        }
        """

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        with patch("pathlib.Path.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = manifest_content

            game = detector._parse_game_manifest(Path("c:/steam/steamapps/appmanifest_570.acf"))

            assert game is not None
            assert game.app_id == "570"
            assert game.name == "Dota 2"
            assert game.size_bytes == 50000000000
            assert game.last_updated is not None

    def test_parse_malformed_manifest(self):
        """Test parsing malformed manifest returns None."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        manifest_content = """
        "AppState"
        {
            "appid"    "570"
            # Missing required fields
        }
        """

        detector = SteamGameDetector()

        with patch("pathlib.Path.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = manifest_content

            game = detector._parse_game_manifest(Path("c:/steam/steamapps/appmanifest_570.acf"))

            # Should gracefully handle missing fields
            assert game is None or game.name == "Unknown"

    @patch("pathlib.Path.glob")
    def test_detect_installed_games(self, mock_glob):
        """Test detecting all installed games."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector, SteamGame

        # Mock manifest files
        mock_manifests = [
            Path("c:/steam/steamapps/appmanifest_570.acf"),
            Path("c:/steam/steamapps/appmanifest_730.acf"),
        ]
        mock_glob.return_value = mock_manifests

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")
        detector.library_folders = [Path("c:/steam/steamapps")]

        # Mock parsing results
        def parse_side_effect(manifest_path):
            if "570" in str(manifest_path):
                return SteamGame(
                    app_id="570",
                    name="Dota 2",
                    install_path=Path("c:/steam/steamapps/common/dota 2 beta"),
                    size_bytes=50_000_000_000,
                    last_updated=datetime(2022, 1, 1),
                    age_days=100,
                )
            elif "730" in str(manifest_path):
                return SteamGame(
                    app_id="730",
                    name="Counter-Strike 2",
                    install_path=Path("c:/steam/steamapps/common/Counter-Strike Global Offensive"),
                    size_bytes=30_000_000_000,
                    last_updated=datetime(2023, 1, 1),
                    age_days=30,
                )
            return None

        with patch.object(detector, "_parse_game_manifest", side_effect=parse_side_effect):
            games = detector.detect_installed_games()

            assert len(games) == 2
            assert games[0].name == "Dota 2"
            assert games[1].name == "Counter-Strike 2"


class TestGameFiltering:
    """Test filtering games by size and age."""

    def test_find_unplayed_games_by_size(self):
        """Test filtering games by minimum size."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector, SteamGame

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        # Mock games with different sizes
        all_games = [
            SteamGame("1", "Big Game", Path("/big"), 50 * 1024**3, datetime(2020, 1, 1), 365),
            SteamGame("2", "Small Game", Path("/small"), 5 * 1024**3, datetime(2020, 1, 1), 365),
            SteamGame("3", "Medium Game", Path("/medium"), 15 * 1024**3, datetime(2020, 1, 1), 365),
        ]

        with patch.object(detector, "detect_installed_games", return_value=all_games):
            games = detector.find_unplayed_games(min_size_gb=10.0, min_age_days=0)

            # Should only return games >= 10GB
            assert len(games) == 2
            assert games[0].name == "Big Game"  # Sorted by size descending
            assert games[1].name == "Medium Game"

    def test_find_unplayed_games_by_age(self):
        """Test filtering games by minimum age."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector, SteamGame

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        # Mock games with different ages
        old_date = datetime.now() - timedelta(days=400)
        recent_date = datetime.now() - timedelta(days=30)

        all_games = [
            SteamGame("1", "Old Game", Path("/old"), 50 * 1024**3, old_date, 400),
            SteamGame("2", "Recent Game", Path("/recent"), 50 * 1024**3, recent_date, 30),
        ]

        with patch.object(detector, "detect_installed_games", return_value=all_games):
            games = detector.find_unplayed_games(min_size_gb=0, min_age_days=180)

            # Should only return games not updated in 180+ days
            assert len(games) == 1
            assert games[0].name == "Old Game"

    def test_find_unplayed_games_sorted_by_size(self):
        """Test games are sorted by size descending."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector, SteamGame

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        all_games = [
            SteamGame("1", "Medium", Path("/m"), 20 * 1024**3, datetime(2020, 1, 1), 365),
            SteamGame("2", "Largest", Path("/l"), 100 * 1024**3, datetime(2020, 1, 1), 365),
            SteamGame("3", "Smallest", Path("/s"), 10 * 1024**3, datetime(2020, 1, 1), 365),
        ]

        with patch.object(detector, "detect_installed_games", return_value=all_games):
            games = detector.find_unplayed_games(min_size_gb=5, min_age_days=0)

            # Should be sorted largest first
            assert len(games) == 3
            assert games[0].name == "Largest"
            assert games[1].name == "Medium"
            assert games[2].name == "Smallest"

    def test_find_unplayed_games_no_last_updated(self):
        """Test handling games with no last_updated timestamp."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector, SteamGame

        detector = SteamGameDetector()
        detector.steam_path = Path("c:/steam")

        # Game with no last_updated should be included (unknown age = risky)
        all_games = [
            SteamGame("1", "Unknown Age", Path("/u"), 50 * 1024**3, None, None),
        ]

        with patch.object(detector, "detect_installed_games", return_value=all_games):
            games = detector.find_unplayed_games(min_size_gb=10, min_age_days=180)

            # Should include games with unknown age
            assert len(games) == 1
            assert games[0].name == "Unknown Age"


class TestIntegration:
    """Integration tests with real Steam data (if available)."""

    @pytest.mark.skipif(
        not Path("c:/program files (x86)/steam").exists(), reason="Steam not installed"
    )
    def test_real_steam_detection(self):
        """Test detection on real Steam installation."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        detector = SteamGameDetector()

        # Should detect Steam
        assert detector.is_available()
        assert detector.steam_path is not None
        assert detector.steam_path.exists()

        # Should find at least one library folder
        assert len(detector.library_folders) > 0

    @pytest.mark.skipif(
        not Path("c:/program files (x86)/steam").exists(), reason="Steam not installed"
    )
    def test_real_game_detection(self):
        """Test detecting real installed games."""
        from autopack.storage_optimizer.steam_detector import SteamGameDetector

        detector = SteamGameDetector()

        if not detector.is_available():
            pytest.skip("Steam not available")

        games = detector.detect_installed_games()

        # If Steam is installed, should find at least some games
        # (may be 0 if no games installed)
        assert isinstance(games, list)
        assert all(hasattr(g, "name") for g in games)
        assert all(hasattr(g, "size_bytes") for g in games)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
