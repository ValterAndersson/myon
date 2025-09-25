#!/usr/bin/env python3
"""
Run the Catalog Admin Agent Engine once with a single instruction.

Usage:
  python adk_agent/catalog_admin/multi_agent_system/scripts/run_engine_once.py --limit 25 --verbose-output

Env:
  - CATALOG_ADMIN_ENGINE_ID (projects/.../reasoningEngines/XXXXXXXX)
  - GOOGLE ADC required (gcloud auth application-default login)
  - Optional: PIPELINE_USER_ID
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from vertexai import agent_engines


def _extract_text_from_chunk(chunk: Dict[str, Any]) -> str:
    text = ""
    if not isinstance(chunk, dict):
        return text
    if isinstance(chunk.get("text"), str):
        text += chunk["text"]
    content = chunk.get("content")
    if isinstance(content, dict):
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text += part["text"]
    return text


def _extract_tool_calls(chunk: Dict[str, Any]) -> List[str]:
    calls: List[str] = []
    if not isinstance(chunk, dict):
        return calls
    content = chunk.get("content")
    if isinstance(content, dict):
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("function_call"), dict):
                name = part["function_call"].get("name")
                if isinstance(name, str):
                    calls.append(name)
    return calls


def _load_engine_id() -> str:
    env_id = os.getenv("CATALOG_ADMIN_ENGINE_ID")
    if env_id:
        return env_id
    # Try deployment metadata in catalog_admin
    here = os.path.dirname(os.path.abspath(__file__))
    ca_root = os.path.abspath(os.path.join(here, "..", ".."))
    meta_path = os.path.join(ca_root, "deployment_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            data = json.load(f)
            rid = data.get("remote_agent_engine_id")
            if isinstance(rid, str) and "/reasoningEngines/" in rid:
                return rid
    # Try repository root metadata
    root_meta = os.path.join(os.getcwd(), "deployment_metadata.json")
    if os.path.exists(root_meta):
        with open(root_meta, "r") as f:
            data = json.load(f)
            rid = data.get("remote_agent_engine_id")
            if isinstance(rid, str) and "/reasoningEngines/" in rid:
                return rid
    raise RuntimeError("CATALOG_ADMIN_ENGINE_ID not set and no deployment metadata found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Catalog Admin Agent Engine once")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--verbose-output", action="store_true")
    args = parser.parse_args()

    try:
        engine_id = _load_engine_id()
    except Exception as e:
        print(f"❌ {e}")
        return 1

    try:
        agent = agent_engines.get(engine_id)
    except Exception as e:
        print(f"❌ Failed to get Agent Engine: {e}")
        return 1

    message = (
        "Run the catalog pipeline end-to-end without stopping early: 1) fetch (canonical-only), 2) analyst on fetched items,"
        " 3) route to specialists by role if issues exist, 4) re-run analyst to verify, 5) approver with auto-apply. "
        f"Limit processing to {args.limit} exercise(s). Use safe, idempotent writes. Summarize actions at the end."
    )
    if args.verbose_output:
        message += (
            "\nProvide a readable summary with: steps executed, counts per step, approvals, remaining issues, and follow-ups. "
            "Print the report as plain text with short bullet points."
        )

    print(f"Running engine: {engine_id}")
    user_id = os.getenv("PIPELINE_USER_ID", "pipeline_cli")

    try:
        stream = agent.stream_query(message=message, user_id=user_id)
        full_text = ""
        tools_used: List[str] = []
        for chunk in stream:
            if hasattr(chunk, "to_dict"):
                chunk = chunk.to_dict()
            tools_used.extend(_extract_tool_calls(chunk))
            text = _extract_text_from_chunk(chunk)
            if text:
                full_text += text
                print(text, end="", flush=True)
        if not full_text and tools_used:
            print(f"[Tools used: {', '.join(sorted(set(tools_used)))}]")
    except Exception as e:
        print(f"❌ Agent query failed: {e}")
        return 1

    print("\n✅ Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())


