#!/usr/bin/env python3
import json
import os
import sys
from typing import Any, Dict, Optional

from vertexai import agent_engines

# Ignore broken GOOGLE_APPLICATION_CREDENTIALS to fall back to ADC
_gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if _gac and not os.path.exists(_gac):
    try:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        print(f"Note: Ignoring missing GOOGLE_APPLICATION_CREDENTIALS at {_gac}")
    except Exception:
        pass


def load_engine_id() -> str:
    env_id = os.getenv("CANVAS_ENGINE_ID")
    if env_id:
        return env_id
    # Try root metadata
    root_meta = os.path.join(os.getcwd(), "deployment_metadata.json")
    if os.path.exists(root_meta):
        try:
            with open(root_meta, "r") as f:
                data = json.load(f)
                rid = data.get("remote_agent_engine_id")
                if isinstance(rid, str) and "/reasoningEngines/" in rid:
                    return rid
        except Exception:
            pass
    # Try module-local metadata
    local_meta = os.path.join(os.path.dirname(__file__), "deployment_metadata.json")
    if os.path.exists(local_meta):
        try:
            with open(local_meta, "r") as f:
                data = json.load(f)
                rid = data.get("remote_agent_engine_id")
                if isinstance(rid, str) and "/reasoningEngines/" in rid:
                    return rid
        except Exception:
            pass
    print("Enter Agent Engine ID (projects/.../reasoningEngines/XXXXXXXX):")
    return input("> ").strip()


def extract_text(chunk: Dict[str, Any]) -> str:
    text = ""
    if not isinstance(chunk, dict):
        return text
    if "text" in chunk and isinstance(chunk["text"], str):
        text += chunk["text"]
    content = chunk.get("content")
    if isinstance(content, dict):
        parts = content.get("parts") or []
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                text += p["text"]
    return text


def _load_canvas_id() -> Optional[str]:
    # Env first
    env_id = os.getenv("TEST_CANVAS_ID")
    if env_id:
        return env_id
    # Local file in module directory
    local_path = os.path.join(os.path.dirname(__file__), ".canvas_id")
    if os.path.exists(local_path):
        try:
            return open(local_path, "r").read().strip()
        except Exception:
            pass
    # Root-level file (repo)
    root_path = os.path.join(os.getcwd(), ".canvas_id")
    if os.path.exists(root_path):
        try:
            return open(root_path, "r").read().strip()
        except Exception:
            pass
    return None


def main() -> int:
    try:
        agent = agent_engines.get(load_engine_id())
    except Exception as e:
        print(f"Failed to init agent: {e}")
        return 1

    default_user = os.getenv("PIPELINE_USER_ID", os.getenv("X_USER_ID", "canvas_orchestrator_engine"))
    canvas_id = _load_canvas_id() or ""
    print("Type 'exit' to quit. Context will be injected if available (canvas_id, user_id).")
    while True:
        try:
            msg = input("You: ").strip()
            if msg.lower() in {"exit", ":q", "quit"}:
                break
            # Inject lightweight context so tools can pick up canvas id, and encourage MVP fast-path
            context_prefix = ""
            if canvas_id:
                context_prefix = f"(context: canvas_id={canvas_id} user_id={default_user}; if route=workout then call tool_workout_stage1_publish)\n"
            enriched = f"{context_prefix}{msg}"
            stream = agent.stream_query(message=enriched, user_id=default_user)
            acc = ""
            for chunk in stream:
                if hasattr(chunk, "to_dict"):
                    chunk = chunk.to_dict()
                acc += extract_text(chunk)
            print(f"Agent: {acc or '(no text)'}\n")
        except KeyboardInterrupt:
            print("\n(Interrupted)")
            continue
        except EOFError:
            print()
            break
        except Exception as e:
            print(f"Error: {e}")
            continue
    return 0


if __name__ == "__main__":
    sys.exit(main())


