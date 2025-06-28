#!/usr/bin/env python3
"""Interactive chat with StrengthOS using Agent Engine Sessions for memory persistence."""

from vertexai import agent_engines
import json
import uuid, asyncio
from datetime import datetime
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table

console = Console()

# Load deployment info
with open('deployment_metadata.json', 'r') as f:
    metadata = json.load(f)
    agent_id = metadata['remote_agent_engine_id']

# Initialize agent
agent = agent_engines.get(agent_id)

try:
    from google.adk.sessions import VertexAiSessionService
    PROJECT_ID = agent_id.split("/")[1]  # extract project from agent resource name
    LOCATION = agent_id.split("/")[3]
    session_service = VertexAiSessionService(PROJECT_ID, LOCATION)
except Exception:
    session_service = None

if session_service is None:
    console.print("[yellow]Warning: Session service unavailable – chat will be stateless.[/yellow]\n")

def chat_session(user_id: str, session_id: str = None):
    """Run an interactive chat session with memory persistence."""
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
        console.print(f"[dim]Created new session: {session_id}[/dim]\n")
    else:
        console.print(f"[dim]Resuming session: {session_id}[/dim]\n")
    
    console.print(Panel(f"💬 Chatting as: {user_id}", style="bold green"))
    console.print("Commands: 'exit' to quit, 'clear' to clear screen, 'info' for session info\n")
    
    while True:
        try:
            message = Prompt.ask("[green]You[/green]")
            
            if message.lower() == 'exit':
                break
            elif message.lower() == 'clear':
                console.clear()
                continue
            elif message.lower() == 'info':
                # Show session info
                table = Table(title="Session Information")
                table.add_column("Field", style="cyan")
                table.add_column("Value", style="white")
                table.add_row("User ID", user_id)
                table.add_row("Session ID", session_id)
                table.add_row("Agent ID", agent_id.split('/')[-1])
                console.print(table)
                console.print()
                continue
            
            # Always include user_id in the message
            if f"user id is {user_id}" not in message.lower():
                message = f"My user id is {user_id}. {message}"
            
            # Show thinking indicator
            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                # Query agent - temporarily without session_id until we fix the issue
                try:
                    # Note: session_id currently returns 0 chunks, investigating...
                    response = agent.stream_query(
                        message=message,
                        user_id=user_id,
                        session_id=session_id
                    )
                except Exception as api_error:
                    console.print(f"\n[red]API Error:[/red] {str(api_error)}")
                    continue
                
                # Collect response
                full_response = ""
                tools_used = []
                
                # Handle the dict response format
                for chunk in response:
                    # Some SDKs yield Event objects; others dicts. Normalize to dict.
                    if hasattr(chunk, 'to_dict'):
                        chunk = chunk.to_dict()

                    # Direct text at root level
                    if isinstance(chunk, dict):
                        if 'text' in chunk:
                            full_response += chunk['text']

                        # Gemini candidate structure
                        if 'content' in chunk:
                            content = chunk['content']
                            if 'parts' in content:
                                for part in content['parts']:
                                    if isinstance(part, dict):
                                        if 'function_call' in part:
                                            tools_used.append(part['function_call'].get('name', 'unknown'))
                                        if 'text' in part and isinstance(part['text'], str):
                                            full_response += part['text']
            
            # Display response
            if full_response:
                console.print(f"\n[blue]Agent:[/blue] {full_response}")
            else:
                console.print("\n[yellow]Agent:[/yellow] [dim](No response)[/dim]")
            
            if tools_used:
                console.print(f"[dim]Tools used: {', '.join(set(tools_used))}[/dim]")
            
            console.print()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]\n")
            continue
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {str(e)}\n")
            continue

def main():
    """Main entry point."""
    console.print(Panel("🏋️ StrengthOS Interactive Chat", style="bold magenta"))
    
    user_id = Prompt.ask(
        "Enter your user ID",
        default="Y4SJuNPOasaltF7TuKm1QCT7JIA3"
    )

    session_id = None
    if session_service:
        choice = Prompt.ask("Start new session or continue existing? [new/existing]", choices=["new", "existing"], default="new")
        if choice == "existing":
            try:
                async def _list():
                    return await session_service.list_sessions(app_name=agent_id.split("/")[-1], user_id=user_id)

                try:
                    resp = asyncio.run(_list())
                except RuntimeError:
                    # event loop already running – create new loop
                    resp = asyncio.get_event_loop().run_until_complete(_list())

                sessions = getattr(resp, "sessions", []) or []
                if not sessions:
                    console.print("[yellow]No existing sessions. Starting a new one.[/yellow]")
                else:
                    console.print("Existing sessions:")
                    for idx, s in enumerate(sessions):
                        console.print(f"  [{idx}] {s.id} (updated: {getattr(s, 'last_update_time', 'n/a')})")
                    sel = Prompt.ask("Select session number or type 'exit' to cancel", default="0")
                    if sel.lower() == 'exit':
                        console.print("Starting a new session instead.")
                    else:
                        try:
                            session_id = sessions[int(sel)].id
                        except (ValueError, IndexError):
                            console.print("[red]Invalid choice – starting new session.[/red]")
            except Exception as e:
                console.print(f"[red]Failed to list sessions: {e}. Starting new session.[/red]")
        elif choice == "new":
            try:
                session_obj = asyncio.get_event_loop().run_until_complete(
                    session_service.create_session(app_name=agent_id.split('/')[-1], user_id=user_id)
                )
                session_id = session_obj.id if hasattr(session_obj, 'id') else session_obj["id"]
            except Exception as e:
                console.print(f"[red]Failed to create session remotely: {e}. Using local uuid.[/red]")
                session_id = str(uuid.uuid4())

    if session_id is None:
        session_id = str(uuid.uuid4())  # fallback when session_service unavailable

    chat_session(user_id, session_id)
    
    console.print("\n[bold]Goodbye! 💪[/bold]")

if __name__ == "__main__":
    main() 