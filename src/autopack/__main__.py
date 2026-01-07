"""Main entry point for the Autopack Framework.

Usage:
    python -m autopack serve        # Start the API server (default)
    python -m autopack run <run-id> # Run the autonomous executor
    python -m autopack --help       # Show help
"""

import argparse
import sys


def main():
    """Main CLI entry point for Autopack."""
    parser = argparse.ArgumentParser(
        prog="autopack",
        description="Autopack - Autonomous Build Framework",
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'serve' command - start the API server
    serve_parser = subparsers.add_parser("serve", help="Start the Autopack API server")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    serve_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )

    # 'run' command - run the autonomous executor
    run_parser = subparsers.add_parser("run", help="Run the autonomous executor")
    run_parser.add_argument("run_id", help="Run ID for the autonomous execution")

    args = parser.parse_args()

    if args.version:
        from .version import __version__

        print(f"Autopack {__version__}")
        return 0

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "autopack.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    elif args.command == "run":
        from .autonomous_executor import main as executor_main

        # autonomous_executor.main() expects sys.argv-style arguments
        sys.argv = ["autopack-run", "--run-id", args.run_id]
        return executor_main()

    else:
        # Default: show help
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
