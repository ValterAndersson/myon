"""Clarification Agent - Specialized agent for handling ambiguous queries."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from google.adk import Agent
from google.adk.tools import FunctionTool

class QuestionType(Enum):
    """Types of clarification questions."""
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    YES_NO = "yes_no"
    TEXT = "text"
    NUMBER = "number"

@dataclass
class ClarificationQuestion:
    """Structured clarification question."""
    id: str
    question: str
    question_type: QuestionType
    options: Optional[List[str]] = None
    context: Optional[str] = None
    required: bool = True
    default: Optional[Any] = None

def tool_generate_clarification(
    ambiguity_type: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate appropriate clarification question based on ambiguity type.
    
    This tool provides deterministic question generation for common ambiguities.
    """
    questions_map = {
        "workout_scope": {
            "question": "Are you looking for a single workout or a full program?",
            "type": "single_choice",
            "options": ["Single workout", "Weekly routine", "Full program"]
        },
        "muscle_groups": {
            "question": "Which muscle groups do you want to focus on?",
            "type": "multi_choice",
            "options": ["Chest", "Back", "Shoulders", "Arms", "Legs", "Core"]
        },
        "experience_level": {
            "question": "What's your training experience level?",
            "type": "single_choice",
            "options": ["Beginner", "Intermediate", "Advanced"]
        },
        "equipment": {
            "question": "What equipment do you have access to?",
            "type": "single_choice",
            "options": ["Full gym", "Dumbbells only", "Barbell & rack", "Bodyweight only"]
        },
        "duration": {
            "question": "How much time do you have for this workout?",
            "type": "single_choice",
            "options": ["30 minutes", "45 minutes", "60 minutes", "90+ minutes"]
        },
        "intensity": {
            "question": "What intensity level are you looking for?",
            "type": "single_choice",
            "options": ["Light", "Moderate", "Intense", "Max effort"]
        },
        "goal": {
            "question": "What's your primary training goal?",
            "type": "single_choice",
            "options": ["Build strength", "Build muscle", "Lose fat", "Improve endurance", "General fitness"]
        }
    }
    
    question_data = questions_map.get(ambiguity_type, {
        "question": "Can you provide more details about what you're looking for?",
        "type": "text",
        "options": None
    })
    
    return {
        "id": f"clarify_{ambiguity_type}",
        "question": question_data["question"],
        "question_type": question_data["type"],
        "options": question_data.get("options"),
        "context": f"Clarifying {ambiguity_type.replace('_', ' ')}",
        "required": True
    }

def tool_prioritize_questions(
    ambiguities: List[str],
    intent: Dict[str, Any]
) -> List[str]:
    """
    Prioritize which questions to ask based on intent and importance.
    
    Returns ordered list of ambiguities to clarify (most important first).
    """
    # Priority order for different intents
    priority_map = {
        "create_workout": ["muscle_groups", "duration", "equipment", "experience_level", "intensity"],
        "create_routine": ["goal", "experience_level", "equipment", "workout_scope"],
        "analyze_progress": ["goal", "muscle_groups", "duration"],
        "default": ["goal", "workout_scope", "experience_level"]
    }
    
    intent_type = intent.get("primary_intent", "default")
    priority_order = priority_map.get(intent_type, priority_map["default"])
    
    # Sort ambiguities by priority
    sorted_ambiguities = []
    for priority_item in priority_order:
        if priority_item in ambiguities:
            sorted_ambiguities.append(priority_item)
    
    # Add any remaining ambiguities not in priority list
    for ambiguity in ambiguities:
        if ambiguity not in sorted_ambiguities:
            sorted_ambiguities.append(ambiguity)
    
    # Return only the most important (limit to 1 for better UX)
    return sorted_ambiguities[:1]

# Clarification Agent with structured output
clarification_agent = Agent(
    name="ClarificationAgent",
    model="gemini-2.5-flash",  # Gemini 2.5 Flash for quick clarifications
    instruction="""
    You generate clarification questions for ambiguous user requests.
    
    Process:
    1. Identify what information is missing or ambiguous
    2. Call tool_prioritize_questions to determine the most important question
    3. Call tool_generate_clarification to create the question
    4. Output a single clarification question with appropriate options
    
    Rules:
    - Ask ONLY ONE question at a time
    - Provide clickable options whenever possible (avoid text input)
    - Make questions clear and specific
    - Include 3-5 options for choice questions
    - Keep questions conversational and friendly
    
    Output exactly ONE question in this format:
    {
      "question": {
        "id": "string",
        "text": "string",
        "type": "single_choice|multi_choice|yes_no|text",
        "options": ["string"] or null
      },
      "follow_up_needed": boolean,
      "confidence": number
    }
    """,
    tools=[
        FunctionTool(func=tool_generate_clarification),
        FunctionTool(func=tool_prioritize_questions),
    ],
    output_schema={
        "type": "object",
        "properties": {
            "question": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": ["single_choice", "multi_choice", "yes_no", "text"]},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "nullable": True
                    }
                },
                "required": ["id", "text", "type"]
            },
            "follow_up_needed": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["question", "follow_up_needed", "confidence"]
    }
)
