#!/usr/bin/env python3
"""StrengthOS Chat CLI (LOCAL DEV)

Runs the StrengthOS agent LOCALLY via ADK Runner (not the deployed Agent Engine),
with helpful slash-commands to exercise Active Workout, Preferences, and Catalog tools.

Usage:
  PYTHONPATH=adk_agent python3 strengthos_chat_cli.py

Environment (optional):
  - GOOGLE_CLOUD_PROJECT (default: myon-53d85)
  - GOOGLE_CLOUD_LOCATION (default: us-central1)
  - FIREBASE_API_KEY (if your agent relies on it at runtime)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any, Dict, Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from google import adk
from google.adk.sessions import VertexAiSessionService
from google.adk.memory import InMemoryMemoryService
try:
    from google.adk.memory import VertexAiMemoryService  # ADK >=1.0
except ImportError:
    VertexAiMemoryService = None

# Import our local agent
from app.agent import root_agent

console = Console()


def _app_name() -> str:
    return os.getenv("STRENGTHOS_APP_NAME", "strengthos-v2-local")

def _load_engine_id() -> Optional[str]:
    env_id = os.getenv("STRENGTHOS_ENGINE_ID")
    if env_id:
        # Accept full resource or bare id
        return env_id.split("/")[-1]
    try:
        with open("deployment_metadata.json", "r") as f:
            rid = json.load(f).get("remote_agent_engine_id")
            if isinstance(rid, str) and "/reasoningEngines/" in rid:
                return rid.split("/")[-1]
    except Exception:
        pass
    return None


def _parse_json_arg(s: Optional[str]) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _macro_to_message(cmd: str, args: list[str], user_id: str) -> Optional[str]:
    # Return a natural prompt that strongly nudges the agent to call a specific tool.
    # We explicitly mention tool names/params for determinism.
    c = cmd.lower()
    if c == "/help":
        return None

    if c == "/health":
        return f"My user id is {user_id}. Call health() and return status and timestamp only."

    if c == "/propose":
        constraints = _parse_json_arg(" ".join(args)) or {}
        return (
            f"My user id is {user_id}. Call propose_session with constraints: {json.dumps(constraints)}. "
            "Then summarize the proposed session in ≤5 bullets."
        )

    if c == "/start":
        plan = _parse_json_arg(" ".join(args)) or {}
        return (
            f"My user id is {user_id}. Call start_active_workout with plan: {json.dumps(plan)}. "
            "Return the new workout_id and a brief summary."
        )

    if c == "/aw":
        return f"My user id is {user_id}. Call get_active_workout and summarize current status in ≤4 bullets."

    if c == "/prescribe" and len(args) >= 3:
        workout_id, exercise_id, set_index = args[0], args[1], args[2]
        context = _parse_json_arg(" ".join(args[3:])) or {}
        return (
            f"My user id is {user_id}. Call prescribe_set with workout_id='{workout_id}', exercise_id='{exercise_id}', "
            f"set_index={int(set_index)}, context={json.dumps(context)}. Return just the set prescription."
        )

    if c == "/log" and len(args) >= 4:
        workout_id, exercise_id, set_index = args[0], args[1], args[2]
        actual = _parse_json_arg(" ".join(args[3:])) or {}
        return (
            f"My user id is {user_id}. Call log_set with workout_id='{workout_id}', exercise_id='{exercise_id}', "
            f"set_index={int(set_index)}, actual={json.dumps(actual)}. Return confirmation only."
        )

    if c == "/score" and len(args) >= 1:
        actual = _parse_json_arg(" ".join(args)) or {}
        return f"My user id is {user_id}. Call score_set with actual={json.dumps(actual)}. Return the score only."

    if c == "/swap" and len(args) >= 3:
        workout_id, from_id, to_id = args[0], args[1], args[2]
        reason = " ".join(args[3:]) if len(args) > 3 else ""
        reason_part = f", reason='{reason}'" if reason else ""
        return (
            f"My user id is {user_id}. Call swap_exercise with workout_id='{workout_id}', from_exercise_id='{from_id}', "
            f"to_exercise_id='{to_id}'{reason_part}. Return confirmation only."
        )

    if c == "/note" and len(args) >= 2:
        workout_id, note = args[0], " ".join(args[1:])
        return f"My user id is {user_id}. Call note_active_workout with workout_id='{workout_id}', note='{note}'. Return confirmation only."

    if c == "/complete" and len(args) >= 1:
        workout_id = args[0]
        return f"My user id is {user_id}. Call complete_active_workout with workout_id='{workout_id}'. Return confirmation only."

    if c == "/cancel" and len(args) >= 1:
        workout_id = args[0]
        return f"My user id is {user_id}. Call cancel_active_workout with workout_id='{workout_id}'. Return confirmation only."

    if c == "/prefs" and args:
        sub = args[0].lower()
        if sub == "get":
            uid = args[1] if len(args) > 1 else user_id
            return f"My user id is {user_id}. Call get_user_preferences for user_id='{uid}'. Return the preferences JSON only."
        if sub == "set" and len(args) >= 3:
            uid = args[1]
            prefs = _parse_json_arg(" ".join(args[2:])) or {}
            return (
                f"My user id is {user_id}. Call update_user_preferences for user_id='{uid}' with preferences={json.dumps(prefs)}. "
                "Return the updated preferences summary."
            )

    if c == "/resolve" and args:
        q = " ".join(args)
        return f"My user id is {user_id}. Call resolve_exercise with q='{q}'. Return top match id, name, family, variant."

    if c == "/ensure" and args:
        name = " ".join(args)
        return f"My user id is {user_id}. Call ensure_exercise_exists with name='{name}'. Return id and name."

    if c == "/alias" and len(args) >= 1:
        sub = args[0].lower()
        if sub == "upsert" and len(args) >= 3:
            alias_slug, exercise_id = args[1], args[2]
            family_slug = args[3] if len(args) > 3 else None
            fam = f", family_slug='{family_slug}'" if family_slug else ""
            return (
                f"My user id is {user_id}. Call upsert_alias with alias_slug='{alias_slug}', exercise_id='{exercise_id}'{fam}. "
                "Return confirmation only."
            )

    if c == "/families":
        return f"My user id is {user_id}. Call list_families with min_size=1, limit=20. Return a short list (slug and count)."

    if c == "/normpage":
        page_size = 50
        start_after = None
        if len(args) >= 1 and args[0].isdigit():
            page_size = int(args[0])
            start_after = args[1] if len(args) > 1 else None
        elif len(args) >= 1:
            start_after = args[0]
        return (
            f"My user id is {user_id}. Call normalize_catalog_page with pageSize={page_size}"
            + (f", startAfterName='{start_after}'" if start_after else "")
            + ". Return counts only."
        )

    if c == "/backfill" and len(args) >= 1:
        family = args[0]
        apply = (args[1].lower() == "true") if len(args) > 1 else False
        limit = int(args[2]) if len(args) > 2 and args[2].isdigit() else 1000
        return (
            f"My user id is {user_id}. Call backfill_normalize_family with family='{family}', apply={str(apply).lower()}, limit={limit}. "
            "Return merges count only."
        )

    if c == "/approve" and len(args) >= 1:
        exid = args[0]
        return f"My user id is {user_id}. Call approve_exercise with exercise_id='{exid}'. Return confirmation only."

    if c == "/refine" and len(args) >= 2:
        exid = args[0]
        updates = _parse_json_arg(" ".join(args[1:])) or {}
        return (
            f"My user id is {user_id}. Call refine_exercise with exercise_id='{exid}', updates={json.dumps(updates)}. "
            "Return changed fields only."
        )

    if c == "/merge" and len(args) >= 2:
        src, tgt = args[0], args[1]
        return f"My user id is {user_id}. Call merge_exercises with source_id='{src}', target_id='{tgt}'. Return confirmation only."

    return None


def print_help() -> None:
    console.print("\n[bold]Slash commands[/bold]")
    console.print("- /health")
    console.print("- /propose {json}")
    console.print("- /start {json}")
    console.print("- /aw (active workout status)")
    console.print("- /prescribe <workout_id> <exercise_id> <set_index> {context_json}")
    console.print("- /log <workout_id> <exercise_id> <set_index> {actual_json}")
    console.print("- /score {actual_json}")
    console.print("- /swap <workout_id> <from_exercise_id> <to_exercise_id> [reason]")
    console.print("- /note <workout_id> <note text>")
    console.print("- /complete <workout_id> | /cancel <workout_id>")
    console.print("- /prefs get [user_id] | /prefs set <user_id> {json}")
    console.print("- /resolve <query> | /ensure <name>")
    console.print("- /alias upsert <alias_slug> <exercise_id> [family_slug]")
    console.print("- /families | /normpage [pageSize] [startAfterName] | /backfill <family> [apply] [limit]")
    console.print("- /approve <exercise_id> | /refine <exercise_id> {updates_json} | /merge <source_id> <target_id>\n")


def main() -> int:
    console.print(Panel("🏋️ StrengthOS Chat CLI (Local)", style="bold magenta"))

    # Project/location for Vertex AI Sessions service (used for session persistence)
    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "myon-53d85")
    LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    # Ensure Vertex AI backend is selected for google-genai used by ADK LLM
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    # Ensure project/location are visible to underlying clients
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
    os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

    # Create services
    engine_id = _load_engine_id()
    try:
        session_service = VertexAiSessionService(PROJECT_ID, LOCATION) if engine_id else None
    except Exception:
        session_service = None

    if VertexAiMemoryService is not None:
        memory_service = VertexAiMemoryService(PROJECT_ID, LOCATION)
    else:
        memory_service = InMemoryMemoryService()

    # Create local runner
    runner = adk.Runner(
        agent=root_agent,
        app_name=(engine_id or _app_name()),
        session_service=session_service,
        memory_service=memory_service,
    )

    user_id = Prompt.ask("Enter your user ID", default="Y4SJuNPOasaltF7TuKm1QCT7JIA3")

    # Prepare session
    session_id: Optional[str] = None
    if session_service is not None and engine_id:
        mode = Prompt.ask("Start new session or continue existing? [new/existing]", choices=["new", "existing"], default="new")
        if mode == "existing":
            try:
                async def _list():
                    return await session_service.list_sessions(app_name=engine_id, user_id=user_id)
                try:
                    resp = asyncio.run(_list())
                except RuntimeError:
                    resp = asyncio.get_event_loop().run_until_complete(_list())
                sessions = getattr(resp, "sessions", []) or []
                if sessions:
                    console.print("Existing sessions:")
                    for idx, s in enumerate(sessions):
                        console.print(f"  [{idx}] {s.id} (updated: {getattr(s, 'last_update_time', 'n/a')})")
                    sel = Prompt.ask("Select session number or press Enter for new", default="")
                    if sel.isdigit():
                        try:
                            session_id = sessions[int(sel)].id
                        except Exception:
                            pass
            except Exception as e:
                console.print(f"[yellow]Session listing failed: {e}[/yellow]")
        if not session_id:
            try:
                async def _create():
                    return await session_service.create_session(app_name=engine_id, user_id=user_id)
                try:
                    obj = asyncio.run(_create())
                except RuntimeError:
                    obj = asyncio.get_event_loop().run_until_complete(_create())
                session_id = obj.id if hasattr(obj, "id") else obj.get("id")
            except Exception:
                session_id = str(uuid.uuid4())
    else:
        session_id = str(uuid.uuid4())

    console.print(f"[dim]Session: {session_id}[/dim]")
    console.print("Type '/help' for commands. Type 'exit' to quit.\n")

    while True:
        try:
            raw = Prompt.ask("[green]You[/green]")
            if not raw:
                continue
            if raw.strip().lower() == "exit":
                break
            if raw.strip().lower() == "/help":
                print_help()
                continue

            # Slash macros → convert to targeted prompts
            if raw.startswith("/"):
                parts = raw.strip().split()
                cmd, args = parts[0], parts[1:]
                message = _macro_to_message(cmd, args, user_id)
                if not message:
                    console.print("[yellow]Unknown command. Type /help[/yellow]")
                    continue
            else:
                # Normal free-form chat; inject user id hint
                message = raw
                if f"user id is {user_id}" not in raw.lower():
                    message = f"My user id is {user_id}. {raw}"

            # Local run via ADK Runner
            class Part:  # minimal shim
                def __init__(self, text: str):
                    self.text = text
            class Content:  # minimal shim
                def __init__(self, role: str, parts: list):
                    self.role = role
                    self.parts = parts

            content = Content(role="user", parts=[Part(text=message)])

            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                try:
                    events = runner.run(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=content,
                    )
                except Exception as api_error:
                    console.print(f"\n[red]Run error:[/red] {api_error}")
                    continue

                full_text = ""
                tools_used: list[str] = []
                for event in events:
                    # Final response text
                    if hasattr(event, "is_final_response") and event.is_final_response():
                        if getattr(event, "content", None) and getattr(event.content, "parts", None):
                            try:
                                full_text = event.content.parts[0].text
                            except Exception:
                                pass
                    # Tool calls (during stream)
                    if getattr(event, "content", None) and getattr(event.content, "parts", None):
                        for part in event.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                try:
                                    tools_used.append(part.function_call.name)
                                except Exception:
                                    pass

            # Output
            console.print(f"\n[blue]Agent:[/blue] {full_text if full_text else '[dim](no response)[/dim]'}")
            if tools_used:
                console.print(f"[dim]Tools used: {', '.join(sorted(set(tools_used)))}[/dim]")
            console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]\n")
            continue
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}\n")
            continue

    console.print("\n[bold]Goodbye! 💪[/bold]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


