"""Streaming Canvas Agent - Cursor-like experience with transparent agent actions."""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from google.adk import Agent
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)

class StreamType(Enum):
    """Types of stream events for UI."""
    THINKING = "thinking"
    THOUGHT = "thought"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    MESSAGE = "message"
    CARD = "card"
    ERROR = "error"

@dataclass
class StreamEvent:
    """Event to stream to UI."""
    type: StreamType
    content: Any
    duration_ms: Optional[float] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "content": self.content,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp
        }

class StreamingOrchestrator:
    """Orchestrator that streams every action transparently."""
    
    def __init__(self):
        self.start_times = {}
        self.context = {}
        self.cards_buffer = []
        
    def emit(self, event: StreamEvent) -> Dict[str, Any]:
        """Emit a stream event and return it."""
        event_dict = event.to_dict()
        
        # Log for debugging
        logger.info(f"Stream: {event_dict}")
        
        # In production, this would write to SSE stream
        # For now, return for agent to output
        return event_dict
    
    def start_thinking(self) -> Dict[str, Any]:
        """Start thinking timer."""
        self.start_times["thinking"] = time.time()
        return self.emit(StreamEvent(
            type=StreamType.THINKING,
            content={"status": "thinking", "message": "Thinking..."}
        ))
    
    def end_thinking(self, thought: str) -> Dict[str, Any]:
        """End thinking with the thought."""
        duration = None
        if "thinking" in self.start_times:
            duration = (time.time() - self.start_times["thinking"]) * 1000
            del self.start_times["thinking"]
        
        return self.emit(StreamEvent(
            type=StreamType.THOUGHT,
            content={"message": thought},
            duration_ms=duration
        ))
    
    def start_tool(self, tool_name: str, description: str) -> Dict[str, Any]:
        """Start a tool execution."""
        self.start_times[tool_name] = time.time()
        
        # Make tool names human-readable
        readable_names = {
            "tool_get_user_preferences": "Looking up your profile",
            "tool_search_exercises": "Searching for exercises",
            "tool_calculate_volume": "Calculating sets and reps",
            "tool_publish_clarify_questions": "Preparing question",
            "tool_canvas_publish": "Publishing cards"
        }
        
        readable_name = readable_names.get(tool_name, tool_name.replace("_", " ").title())
        
        return self.emit(StreamEvent(
            type=StreamType.TOOL_START,
            content={
                "tool": tool_name,
                "description": description or readable_name,
                "status": "running"
            }
        ))
    
    def end_tool(self, tool_name: str, success: bool = True) -> Dict[str, Any]:
        """End a tool execution."""
        duration = None
        if tool_name in self.start_times:
            duration = (time.time() - self.start_times[tool_name]) * 1000
            del self.start_times[tool_name]
        
        return self.emit(StreamEvent(
            type=StreamType.TOOL_END,
            content={
                "tool": tool_name,
                "status": "complete" if success else "failed"
            },
            duration_ms=duration
        ))
    
    def message(self, text: str) -> Dict[str, Any]:
        """Stream a message to the user."""
        return self.emit(StreamEvent(
            type=StreamType.MESSAGE,
            content={"text": text}
        ))
    
    def card(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """Stream a card."""
        self.cards_buffer.append(card_data)
        return self.emit(StreamEvent(
            type=StreamType.CARD,
            content=card_data
        ))

# Global orchestrator instance
stream = StreamingOrchestrator()

# Tool wrappers that emit streaming events

def tool_understand_request(message: str) -> Dict[str, Any]:
    """Understand the user's request with streaming."""
    stream.start_thinking()
    time.sleep(0.5)  # Simulate thinking
    
    # Determine intent
    message_lower = message.lower()
    
    if "program" in message_lower or "workout" in message_lower:
        thought = "Okay, let's plan a program. I'll first take a look at your background and activity."
        intent = "create_workout"
    else:
        thought = "I'll help you with that."
        intent = "unknown"
    
    stream.end_thinking(thought)
    stream.message(thought)
    
    return {"intent": intent, "confidence": 0.8}

def tool_check_profile(
    user_id: str,
    canvas_id: str
) -> Dict[str, Any]:
    """Check user profile with streaming."""
    stream.start_tool("tool_get_user_preferences", "Looking up your profile")
    
    # Simulate profile lookup
    time.sleep(0.3)
    
    # Mock response - missing goals
    profile = {
        "has_goals": False,
        "has_experience": True,
        "experience": "intermediate",
        "equipment": ["barbell", "dumbbells"]
    }
    
    stream.end_tool("tool_get_user_preferences", success=True)
    
    if not profile["has_goals"]:
        stream.message("I currently don't know what your primary fitness goal is. This information helps me tailor the program for you.")
    
    return profile

def tool_ask_clarification(
    question: str,
    options: List[str],
    canvas_id: str,
    user_id: str
) -> Dict[str, Any]:
    """Ask a clarification question with streaming."""
    stream.start_tool("tool_publish_clarify_questions", "Preparing question")
    
    # Create card
    card = {
        "type": "clarify_questions",
        "content": {
            "title": "Quick question",
            "questions": [{
                "id": "q_0",
                "text": question,
                "type": "choice",
                "options": options
            }]
        }
    }
    
    stream.card(card)
    stream.end_tool("tool_publish_clarify_questions", success=True)
    
    return {"published": True, "card_id": "clarify_123"}

def tool_find_exercises(
    goal: str,
    muscle_groups: List[str]
) -> Dict[str, Any]:
    """Find exercises with streaming."""
    stream.message(f"Got it. If your fitness goal is {goal}, then we need to focus on exercises that drive muscle growth.")
    
    stream.start_tool("tool_search_exercises", f"Looking for exercises that drive {goal.lower()}")
    
    # Simulate search
    time.sleep(0.5)
    
    exercises = [
        {"name": "Bench Press", "muscles": ["chest"]},
        {"name": "Overhead Press", "muscles": ["shoulders"]},
        {"name": "Barbell Row", "muscles": ["back"]},
        {"name": "Bicep Curl", "muscles": ["biceps"]}
    ]
    
    stream.end_tool("tool_search_exercises", success=True)
    
    return {"exercises": exercises}

def tool_create_workout_card(
    exercises: List[Dict[str, Any]],
    canvas_id: str,
    user_id: str
) -> Dict[str, Any]:
    """Create and publish workout card with streaming."""
    stream.start_tool("tool_canvas_publish", "Creating your workout")
    
    # Format workout
    card = {
        "type": "session_plan",
        "content": {
            "title": "Hypertrophy Focus",
            "blocks": [
                {
                    "exercise_id": ex["name"].lower().replace(" ", "_"),
                    "name": ex["name"],
                    "sets": [{"target": {"reps": "8-12"}} for _ in range(3)]
                }
                for ex in exercises
            ]
        }
    }
    
    stream.card(card)
    stream.end_tool("tool_canvas_publish", success=True)
    
    stream.message("Here's your hypertrophy-focused workout. Each exercise targets 8-12 reps for optimal muscle growth.")
    
    return {"published": True, "card_count": 1}

# Create the streaming agent
streaming_agent = Agent(
    name="StreamingCanvas",
    model="gemini-2.0-flash-exp",  # Fastest Gemini model (2.5 flash when available)
    instruction="""
    You provide a transparent, Cursor-like experience for workout planning.
    
    ALWAYS follow this exact flow:
    
    1. Call tool_understand_request to process the message
    2. Call tool_check_profile to look up user data
    3. If data missing, call tool_ask_clarification with ONE question
    4. Wait for user response (will appear in context)
    5. Call tool_find_exercises based on goal
    6. Call tool_create_workout_card to publish the workout
    
    IMPORTANT:
    - Every action must be streamed to the user
    - Show your thinking process
    - Explain what you're doing and why
    - Keep messages conversational and helpful
    
    The user should see:
    - "Thinking..." with duration
    - Your thoughts about what to do
    - Tool executions with timers
    - Clear explanations at each step
    """,
    tools=[
        FunctionTool(func=tool_understand_request),
        FunctionTool(func=tool_check_profile),
        FunctionTool(func=tool_ask_clarification),
        FunctionTool(func=tool_find_exercises),
        FunctionTool(func=tool_create_workout_card),
    ]
)
