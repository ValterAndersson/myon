#!/usr/bin/env python3
"""Interactive chat for Catalog Admin agent (Agent Engine)."""

import json
import os
import sys
import uuid
import asyncio
from typing import Any, Dict

from vertexai import agent_engines

def load_engine_id() -> str:
    """Load the agent engine ID from various sources."""
    # Priority: env var → local metadata → repo root metadata → prompt
    env_id = os.getenv("CATALOG_ADMIN_ENGINE_ID")
    if env_id:
        return env_id
    
    # Try local metadata
    local_meta = os.path.join(os.path.dirname(__file__), "deployment_metadata.json")
    if os.path.exists(local_meta):
        with open(local_meta, "r") as f:
            return json.load(f)["remote_agent_engine_id"]
    
    # Try repo root metadata
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
    
    # Fallback prompt
    print("Enter Agent Engine ID (e.g., projects/.../reasoningEngines/XXXXXXXXXXXXXX):")
    return input("> ").strip()


def extract_text_from_chunk(chunk: Dict[str, Any]) -> str:
    """Extract text from a response chunk."""
    text = ""
    if not isinstance(chunk, dict):
        return text
    
    # Direct text at root level
    if "text" in chunk and isinstance(chunk["text"], str):
        text += chunk["text"]
    
    # Gemini candidate structure
    content = chunk.get("content")
    if isinstance(content, dict):
        parts = content.get("parts") or []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text += part["text"]
    return text


def extract_tool_calls(chunk: Dict[str, Any]) -> list[str]:
    """Extract tool calls from a response chunk."""
    calls: list[str] = []
    if not isinstance(chunk, dict):
        return calls
    
    content = chunk.get("content")
    if isinstance(content, dict):
        parts = content.get("parts") or []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("function_call"), dict):
                name = part["function_call"].get("name")
                if isinstance(name, str):
                    calls.append(name)
    return calls


def main() -> int:
    """Main entry point for interactive chat."""
    try:
        # If GOOGLE_APPLICATION_CREDENTIALS points to a missing file, drop it
        gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if gac and not os.path.exists(gac):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        agent_id = load_engine_id()
        if not agent_id:
            print("No Agent Engine ID provided. Exiting.")
            return 1
        
        # Initialize agent
        agent = agent_engines.get(agent_id)
        
        # Try to initialize session service
        session_service = None
        try:
            from google.adk.sessions import VertexAiSessionService
            PROJECT_ID = agent_id.split("/")[1]  # extract project from agent resource name
            LOCATION = agent_id.split("/")[3]
            AGENT_ENGINE_ID = agent_id.split("/")[-1]
            session_service = VertexAiSessionService(PROJECT_ID, LOCATION)
            print(f"Session service initialized for project {PROJECT_ID}, location {LOCATION}")
        except Exception as e:
            print(f"Warning: Session service unavailable: {e}")
            print("Chat will be stateless.\n")
        
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        return 1

    default_user = os.getenv("CATALOG_ADMIN_USER_ID", "catalog_admin_user")
    user_id = input(f"User ID [{default_user}]: ").strip() or default_user
    
    # Session management
    session_id = None
    if session_service:
        choice = input("Start new session or continue existing? [new/existing] (default: new): ").strip().lower()
        if choice == "existing":
            try:
                async def _list():
                    return await session_service.list_sessions(app_name=AGENT_ENGINE_ID, user_id=user_id)
                
                try:
                    resp = asyncio.run(_list())
                except RuntimeError:
                    # event loop already running
                    resp = asyncio.get_event_loop().run_until_complete(_list())
                
                sessions = getattr(resp, "sessions", []) or []
                if not sessions:
                    print("No existing sessions. Starting a new one.")
                else:
                    print("Existing sessions:")
                    for idx, s in enumerate(sessions):
                        print(f"  [{idx}] {s.id} (updated: {getattr(s, 'last_update_time', 'n/a')})")
                    sel = input("Select session number or press Enter for new: ").strip()
                    if sel and sel.isdigit():
                        try:
                            session_id = sessions[int(sel)].id
                            print(f"Resuming session: {session_id}")
                        except (ValueError, IndexError):
                            print("Invalid choice – starting new session.")
            except Exception as e:
                print(f"Failed to list sessions: {e}. Starting new session.")
        
        if not session_id and choice != "existing":
            # Create new session
            try:
                async def _create():
                    return await session_service.create_session(app_name=AGENT_ENGINE_ID, user_id=user_id)
                
                try:
                    session_obj = asyncio.run(_create())
                except RuntimeError:
                    session_obj = asyncio.get_event_loop().run_until_complete(_create())
                
                session_id = session_obj.id if hasattr(session_obj, 'id') else session_obj.get("id")
                print(f"Created new session: {session_id}")
            except Exception as e:
                print(f"Failed to create session: {e}. Using local UUID.")
                session_id = str(uuid.uuid4())
    
    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"Using local session ID: {session_id}")
    
    print(f"\nSession ID: {session_id}")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            message = input("You: ").strip()
            if message.lower() in {"exit", ":q", "quit"}:
                break

            # Send query with session support
            try:
                # Stream query with session ID
                stream = agent.stream_query(
                    message=message, 
                    user_id=user_id,
                    session_id=session_id
                )
            except Exception as api_error:
                print(f"API error: {api_error}")
                # Retry without session if it fails
                try:
                    print("Retrying without session...")
                    stream = agent.stream_query(message=message, user_id=user_id)
                except Exception as retry_error:
                    print(f"Retry failed: {retry_error}")
                    continue

            full_text = ""
            tools_used = []
            
            for chunk in stream:
                # Normalize event to dict
                if hasattr(chunk, "to_dict"):
                    chunk = chunk.to_dict()
                if isinstance(chunk, dict):
                    # Extract tool calls
                    tcalls = extract_tool_calls(chunk)
                    if tcalls:
                        tools_used.extend(tcalls)
                    # Extract text
                    full_text += extract_text_from_chunk(chunk)

            # Display response
            if full_text:
                print(f"Agent: {full_text}")
            else:
                print("Agent: (no response)")
            
            if tools_used:
                print(f"[Tools used: {', '.join(set(tools_used))}]")
            
            print()
            
        except KeyboardInterrupt:
            print("\n(Interrupted) Type 'exit' to quit.")
            continue
        except EOFError:
            print()
            break
        except Exception as e:
            print(f"Error: {e}")
            continue

    print("Goodbye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())