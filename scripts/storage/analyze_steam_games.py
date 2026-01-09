"""
Steam Game Analysis CLI (BUILD-151 Phase 4)

Detect Steam games and find large unplayed/unused games for storage optimization.

Addresses user's original request: "detect and suggest moving large uninstalled games"

Usage:
    # Find large unplayed games (defaults: >10GB, not updated in 6 months)
    python scripts/storage/analyze_steam_games.py

    # Custom size and age thresholds
    python scripts/storage/analyze_steam_games.py --min-size 50 --min-age 365

    # List all installed games
    python scripts/storage/analyze_steam_games.py --all

    # Save results to JSON
    python scripts/storage/analyze_steam_games.py --output steam_games.json

    # Save to database for cleanup workflow integration
    python scripts/storage/analyze_steam_games.py --save-to-db
"""

import sys
import argparse
import json
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from autopack.storage_optimizer.steam_detector import SteamGameDetector, SteamGame


def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def print_game_table(games: List[SteamGame], show_all: bool = False):
    """Print games in formatted table."""
    if not games:
        print("\nNo games found matching criteria.")
        return

    print(f"\n{'='*100}")
    print(f"{'Game Name':<50} {'Size':<12} {'Last Updated':<20} {'Age (days)':<12}")
    print(f"{'='*100}")

    total_size = 0
    for game in games:
        size_str = format_size(game.size_bytes)
        total_size += game.size_bytes

        last_updated = game.last_updated.strftime('%Y-%m-%d %H:%M') if game.last_updated else 'Unknown'
        age_str = f"{game.age_days} days" if game.age_days else "Unknown"

        # Truncate long names
        name = game.name[:47] + "..." if len(game.name) > 50 else game.name

        print(f"{name:<50} {size_str:<12} {last_updated:<20} {age_str:<12}")

        if show_all:
            print(f"  Path: {game.install_path}")
            if game.app_id:
                print(f"  App ID: {game.app_id}")

    print(f"{'='*100}")
    print(f"Total: {len(games)} games, {format_size(total_size)} ({total_size:,} bytes)")
    print(f"{'='*100}\n")


def save_to_json(games: List[SteamGame], output_path: str):
    """Save games to JSON file."""
    data = {
        "total_games": len(games),
        "total_size_bytes": sum(g.size_bytes for g in games),
        "total_size_gb": round(sum(g.size_bytes for g in games) / (1024**3), 2),
        "games": [
            {
                "app_id": g.app_id,
                "name": g.name,
                "install_path": str(g.install_path),
                "size_bytes": g.size_bytes,
                "size_gb": round(g.size_bytes / (1024**3), 2),
                "last_updated": g.last_updated.isoformat() if g.last_updated else None,
                "age_days": g.age_days
            }
            for g in games
        ]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved {len(games)} games to {output_path}")


def save_to_database(games: List[SteamGame]):
    """Save games to database as cleanup candidates."""
    from autopack.database import SessionLocal
    from autopack.models import StorageScan, CleanupCandidateDB
    from datetime import datetime, timezone

    session = SessionLocal()

    try:
        # Create a scan record
        scan = StorageScan(
            timestamp=datetime.now(timezone.utc),
            scan_type='steam_games',
            scan_target='Steam Library',
            max_depth=None,
            max_items=None,
            policy_version='BUILD-151',
            total_items_scanned=len(games),
            total_size_bytes=sum(g.size_bytes for g in games),
            cleanup_candidates_count=len(games),
            potential_savings_bytes=sum(g.size_bytes for g in games),
            scan_duration_seconds=0,
            created_by='cli_steam_analyzer',
            notes='Steam game detection for storage optimization'
        )
        session.add(scan)
        session.flush()

        # Add games as cleanup candidates
        for game in games:
            candidate = CleanupCandidateDB(
                scan_id=scan.id,
                path=str(game.install_path),
                size_bytes=game.size_bytes,
                age_days=game.age_days,
                last_modified=game.last_updated,
                category='steam_games',
                reason=f"Large Steam game: {game.name} ({format_size(game.size_bytes)})",
                requires_approval=True,
                approval_status='pending'
            )
            session.add(candidate)

        session.commit()

        print(f"\n✓ Saved {len(games)} games to database (scan_id={scan.id})")
        print(f"  View via API: GET /storage/scans/{scan.id}")
        print(f"  Approve via: POST /storage/scans/{scan.id}/approve")

        return scan.id

    except Exception as e:
        session.rollback()
        print(f"\n✗ Failed to save to database: {e}")
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Steam games for storage optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--min-size',
        type=float,
        default=10.0,
        help='Minimum game size in GB (default: 10.0)'
    )

    parser.add_argument(
        '--min-age',
        type=int,
        default=180,
        help='Minimum days since last update (default: 180 = 6 months)'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all games regardless of size/age'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Save results to JSON file'
    )

    parser.add_argument(
        '--save-to-db',
        action='store_true',
        help='Save results to database for cleanup workflow integration'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed information (paths, app IDs)'
    )

    args = parser.parse_args()

    # Initialize detector
    print("Detecting Steam installation...")
    detector = SteamGameDetector()

    if not detector.is_available():
        print("\n✗ Steam not detected on this system")
        print("  Steam must be installed and registry entries present")
        return 1

    print(f"✓ Steam detected at: {detector.steam_path}")

    if detector.library_folders:
        print(f"✓ Found {len(detector.library_folders)} library folder(s):")
        for folder in detector.library_folders:
            print(f"  - {folder}")

    # Detect games
    print("\nScanning for games...")

    if args.all:
        print("  Mode: All installed games")
        games = detector.detect_installed_games()
    else:
        print("  Mode: Large unplayed games")
        print(f"  Filters: Size >= {args.min_size} GB, Age >= {args.min_age} days")
        games = detector.find_unplayed_games(
            min_size_gb=args.min_size,
            min_age_days=args.min_age
        )

    # Display results
    print_game_table(games, show_all=args.verbose)

    # Save results
    if args.output:
        save_to_json(games, args.output)

    if args.save_to_db:
        scan_id = save_to_database(games)

    # Recommendations
    if games and not args.all:
        total_size_gb = sum(g.size_bytes for g in games) / (1024**3)
        print("\n💡 Recommendations:")
        print(f"  - You could free up to {total_size_gb:.2f} GB by removing these games")
        print("  - Games can be re-downloaded from Steam library anytime")
        print("  - Consider uninstalling games you haven't played in 6+ months")
        print("\n  To approve for deletion:")
        if args.save_to_db:
            print(f"    1. Review candidates: GET /storage/scans/{scan_id}")
            print(f"    2. Approve: POST /storage/scans/{scan_id}/approve")
            print(f"    3. Execute: POST /storage/scans/{scan_id}/execute")
        else:
            print("    Run with --save-to-db to integrate with cleanup workflow")

    return 0


if __name__ == '__main__':
    sys.exit(main())
