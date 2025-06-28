#!/usr/bin/env python3
"""Local chat interface using ADK Runner with proper session support."""

import asyncio
import json
import os
from datetime import datetime
from google import adk
from google.adk.sessions import VertexAiSessionService
from google.adk.events import Event, EventActions
from google.adk.memory import InMemoryMemoryService
try:
    from google.adk.memory import VertexAiMemoryService  # ADK >=1.0
except ImportError:
    VertexAiMemoryService = None
import time
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

# Import our agent
from app.agent import root_agent

console = Console()

# Simple Content and Part classes to match ADK expectations
class Part:
    def __init__(self, text: str):
        self.text = text

class Content:
    def __init__(self, role: str, parts: list):
        self.role = role
        self.parts = parts

# Load deployment metadata
with open('deployment_metadata.json', 'r') as f:
    metadata = json.load(f)
    AGENT_ENGINE_ID = metadata['remote_agent_engine_id'].split('/')[-1]

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "myon-53d85")
LOCATION = "us-central1"

# Set environment variables for Vertex AI
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

async def run_chat_session():
    """Run an interactive chat session with proper session management."""
    
    console.print(Panel("🏋️ StrengthOS Local Chat with Sessions", style="bold magenta"))
    console.print("[dim]This runs the agent locally with full session support[/dim]\n")
    
    # Get user ID
    user_id = Prompt.ask(
        "Enter your user ID",
        default="Y4SJuNPOasaltF7TuKm1QCT7JIA3"
    )
    
    # Create services
    session_service = VertexAiSessionService(PROJECT_ID, LOCATION)

    # Memory service: use Vertex AI if available, else fallback to in-memory
    if VertexAiMemoryService is not None:
        memory_service = VertexAiMemoryService(PROJECT_ID, LOCATION)
    else:
        memory_service = InMemoryMemoryService()
    
    # Create ADK runner with session service
    runner = adk.Runner(
        agent=root_agent,
        app_name=AGENT_ENGINE_ID,
        session_service=session_service,
        memory_service=memory_service
    )
    
    # Create or resume session
    use_existing = Prompt.ask(
        "Start new session or continue existing?",
        choices=["new", "existing"],
        default="new"
    )
    
    if use_existing == "existing":
        # List existing sessions
        sessions_response = await session_service.list_sessions(
            app_name=AGENT_ENGINE_ID,
            user_id=user_id
        )
        
        sessions_list = sessions_response.sessions or []
        if sessions_list:
            console.print("\nExisting sessions:")
            for idx, session in enumerate(sessions_list):
                last_updated = getattr(session, "last_update_time", getattr(session, "lastUpdateTime", "n/a"))
                console.print(f"  [{idx}] {session.id} (last updated: {last_updated})")
            
            choice = Prompt.ask("Select session number", default="0")
            session_id = sessions_list[int(choice)].id
            
            # Get the session
            session = await session_service.get_session(
                app_name=AGENT_ENGINE_ID,
                user_id=user_id,
                session_id=session_id
            )
            console.print(f"[green]Resumed session: {session_id}[/green]")
            console.print(f"Current state: {session.state}\n")
        else:
            console.print("[yellow]No existing sessions found. Creating new one.[/yellow]")
            session = await session_service.create_session(
                app_name=AGENT_ENGINE_ID,
                user_id=user_id,
                state={'created_at': datetime.now().isoformat()}
            )
    else:
        # Create new session with initial state
        initial_state = {
            'created_at': datetime.now().isoformat(),
            'user_preferences': {}
        }
        
        # Check if user has injuries or special conditions
        has_injury = Prompt.ask(
            "Do you have any injuries or conditions to track?",
            choices=["yes", "no"],
            default="no"
        )
        
        if has_injury == "yes":
            injury_info = Prompt.ask("Describe your injury/condition")
            initial_state['injury_info'] = injury_info
        
        session = await session_service.create_session(
            app_name=AGENT_ENGINE_ID,
            user_id=user_id,
            state=initial_state
        )
        console.print(f"[green]Created new session: {session.id}[/green]\n")
    
    # Helper function to send messages to the agent
    def call_agent(query: str):
        """Send a query to the agent and display the response."""
        # Add user_id to message if not present
        if f"user id is {user_id}" not in query.lower():
            query = f"My user id is {user_id}. {query}"
        
        content = Content(role='user', parts=[Part(text=query)])
        
        with console.status("[dim]Thinking...[/dim]", spinner="dots"):
            events = runner.run(
                user_id=user_id,
                session_id=session.id,
                new_message=content
            )
            
            response_text = ""
            tools_used = []
            
            for event in events:
                if event.is_final_response() and event.content and event.content.parts:
                    response_text = event.content.parts[0].text
                    # Any additional post-processing of the final text can go here
                # Inspect events for tool calls (including during streaming)
                if getattr(event, "content", None) and getattr(event.content, "parts", None):
                    for part in event.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            tool_name = part.function_call.name
                            tools_used.append(tool_name)
                            if tool_name == "store_important_fact":
                                console.print("[dim]💾 Important fact saved to session state[/dim]")
        
        console.print(f"\n[blue]Agent:[/blue] {response_text}")
        if tools_used:
            console.print(f"[dim]Tools used: {', '.join(set(tools_used))}[/dim]")
        console.print()
    
    # Chat loop
    console.print("Commands: 'exit' to quit, 'state' to view session state, 'update_state' to modify state\n")
    
    while True:
        try:
            message = Prompt.ask("[green]You[/green]")
            
            if message.lower() == 'exit':
                break
            elif message.lower() == 'state':
                # Get current session state
                current_session = await session_service.get_session(
                    app_name=AGENT_ENGINE_ID,
                    user_id=user_id,
                    session_id=session.id
                )
                console.print(f"[cyan]Current state:[/cyan] {current_session.state}\n")
                continue
            elif message.lower() == 'update_state':
                # Update state manually
                key = Prompt.ask("State key")
                value = Prompt.ask("State value")
                
                # Create event to update state
                state_changes = {key: value}
                actions = EventActions(state_delta=state_changes)
                system_event = Event(
                    invocation_id=f"manual_update_{int(time.time())}",
                    author="system",
                    actions=actions,
                    timestamp=time.time()
                )
                
                await session_service.append_event(session, system_event)
                console.print(f"[green]State updated: {key} = {value}[/green]\n")
                continue
            
            # Send message to agent
            call_agent(message)
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'exit' to quit[/yellow]\n")
            continue
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {str(e)}\n")
            continue
    
    # Ask if user wants to delete the session
    delete = Prompt.ask(
        "\nDelete this session?",
        choices=["yes", "no"],
        default="no"
    )
    
    if delete == "yes":
        await session_service.delete_session(
            app_name=AGENT_ENGINE_ID,
            user_id=user_id,
            session_id=session.id
        )
        console.print("[dim]Session deleted[/dim]")
    else:
        # Persist final session into memory so future sessions can recall
        try:
            await memory_service.add_session_to_memory(session)
        except Exception:
            pass
        console.print(f"[dim]Session saved. ID: {session.id}[/dim]")
    
    console.print("\n[bold]Goodbye! 💪[/bold]")

def main():
    """Run the async chat session."""
    asyncio.run(run_chat_session())

if __name__ == "__main__":
    main() 