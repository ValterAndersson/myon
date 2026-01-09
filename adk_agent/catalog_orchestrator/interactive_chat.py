#!/usr/bin/env python3
"""
Interactive Chat for Catalog Orchestrator.

This script provides an interactive way to test the catalog curation agent
locally. It simulates job execution rather than conversational chat.

Usage:
    python interactive_chat.py

Commands:
    audit <family_slug>     - Run FAMILY_AUDIT job
    normalize <family_slug> - Run FAMILY_NORMALIZE job (dry-run)
    list                    - List families
    exit                    - Exit
"""

import asyncio
import logging
import sys
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_mock_job(job_type: str, family_slug: str = None, mode: str = "dry_run") -> dict:
    """Create a mock job document for testing."""
    job_id = f"test-{uuid.uuid4().hex[:8]}"
    return {
        "id": job_id,
        "type": job_type,
        "queue": "priority",
        "priority": 100,
        "status": "queued",
        "payload": {
            "family_slug": family_slug,
            "mode": mode,
        },
        "created_at": "2025-01-09T00:00:00Z",
    }


async def run_job(job_type: str, family_slug: str = None, mode: str = "dry_run"):
    """Run a job and print results."""
    from app.shell.agent import execute_job
    
    job = create_mock_job(job_type, family_slug, mode)
    worker_id = "interactive-worker"
    
    print(f"\n{'='*60}")
    print(f"Running job: {job_type}")
    print(f"Family: {family_slug or 'N/A'}")
    print(f"Mode: {mode}")
    print(f"{'='*60}\n")
    
    try:
        result = execute_job(job, worker_id)
        print("\nResult:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"\nError: {e}")
        logger.exception("Job execution failed")


def parse_command(cmd: str) -> tuple:
    """Parse a command string into (command, args)."""
    parts = cmd.strip().split()
    if not parts:
        return None, []
    return parts[0].lower(), parts[1:]


async def main():
    """Main interactive loop."""
    print("\n" + "="*60)
    print("Catalog Orchestrator - Interactive Testing")
    print("="*60)
    print("\nCommands:")
    print("  audit <family_slug>     - Run FAMILY_AUDIT job")
    print("  normalize <family_slug> - Run FAMILY_NORMALIZE job (dry-run)")
    print("  list                    - List families")
    print("  help                    - Show this help")
    print("  exit                    - Exit")
    print()
    
    while True:
        try:
            cmd = input("catalog> ").strip()
            if not cmd:
                continue
                
            command, args = parse_command(cmd)
            
            if command == "exit" or command == "quit":
                print("Goodbye!")
                break
                
            elif command == "help":
                print("\nCommands:")
                print("  audit <family_slug>     - Run FAMILY_AUDIT job")
                print("  normalize <family_slug> - Run FAMILY_NORMALIZE job")
                print("  list                    - List families")
                print("  exit                    - Exit")
                
            elif command == "audit":
                if not args:
                    print("Usage: audit <family_slug>")
                else:
                    await run_job("FAMILY_AUDIT", args[0])
                    
            elif command == "normalize":
                if not args:
                    print("Usage: normalize <family_slug>")
                else:
                    await run_job("FAMILY_NORMALIZE", args[0])
                    
            elif command == "list":
                await run_job("MAINTENANCE_SCAN")
                
            else:
                print(f"Unknown command: {command}")
                print("Type 'help' for available commands")
                
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit")
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            logger.exception("Command failed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
