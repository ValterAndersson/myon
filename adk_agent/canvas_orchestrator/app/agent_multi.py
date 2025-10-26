"""Multi-Agent Canvas Orchestrator - Production entry point."""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool

from .multi_agent_orchestrator import multi_agent_orchestrator, StreamEvent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_with_streaming(message: str) -> None:
    """
    Process message through multi-agent system with streaming.
    
    This is the main entry point that Vertex AI calls.
    """
    # Extract context from message
    import re
    context_match = re.search(r'\(context:([^)]*)\)', message, re.IGNORECASE)
    
    canvas_id = None
    user_id = None
    correlation_id = None
    
    if context_match:
        context_str = context_match.group(1)
        for pair in context_str.split():
            if '=' in pair:
                key, value = pair.split('=', 1)
                if key == 'canvas_id':
                    canvas_id = value
                elif key == 'user_id':
                    user_id = value
                elif key == 'corr':
                    correlation_id = value
        
        # Remove context from message
        message = message.replace(context_match.group(0), '').strip()
    
    # Validate required context
    if not canvas_id or not user_id:
        error_event = StreamEvent(
            type="error",
            agent="orchestrator",
            content={"error": "Missing canvas_id or user_id in context"}
        )
        print(json.dumps(error_event.to_dict()))
        return
    
    # Process through multi-agent orchestrator
    try:
        async for event in multi_agent_orchestrator.process_request(
            message=message,
            canvas_id=canvas_id,
            user_id=user_id,
            correlation_id=correlation_id
        ):
            # Stream events to Vertex AI
            print(json.dumps(event))
            
            # Flush to ensure immediate streaming
            import sys
            sys.stdout.flush()
            
    except Exception as e:
        logger.error(f"Processing error: {e}")
        error_event = StreamEvent(
            type="error",
            agent="orchestrator",
            content={"error": str(e)}
        )
        print(json.dumps(error_event.to_dict()))


def process_message(message: str) -> dict:
    """Synchronous tool wrapper that runs the async pipeline.

    This ensures ADK FunctionTool executes the full pipeline (including card
    publishing) even without native streaming integration.
    """
    try:
        import asyncio as _asyncio
        _asyncio.run(process_with_streaming(message))
        return {"ok": True}
    except Exception as e:
        logger.error(f"process_message error: {e}")
        return {"ok": False, "error": str(e)}

# Create the root agent for Vertex AI
multi_agent_root = Agent(
    name="MultiAgentOrchestrator",
    model="gemini-2.5-flash",  # Gemini 2.5 Flash - fastest model for routing
    instruction="""
    You coordinate a multi-agent system for workout planning and fitness analysis.
    
    Your ONLY job is to:
    1. Receive the user message with context
    2. Call the process_message tool with the full message
    3. Stream the results back
    
    Do NOT attempt to answer questions directly.
    Do NOT modify the message.
    Do NOT add your own interpretation.
    
    Simply pass the ENTIRE message (including context prefix) to process_message.
    """,
    tools=[
        FunctionTool(func=process_message)
    ]
)

# For backwards compatibility, also export as root_agent
root_agent = multi_agent_root

if __name__ == "__main__":
    # Test locally
    test_message = "(context: canvas_id=test123 user_id=user456 corr=corr789) I want to plan a workout for my upper body"
    
    async def test():
        async for event in multi_agent_orchestrator.process_request(
            message="I want to plan a workout for my upper body",
            canvas_id="test123",
            user_id="user456",
            correlation_id="corr789"
        ):
            print(json.dumps(event, indent=2))
    
    asyncio.run(test())
