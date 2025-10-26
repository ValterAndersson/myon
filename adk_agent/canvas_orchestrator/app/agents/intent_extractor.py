"""Intent Extractor Agent - Lightweight, fast intent classification."""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

from google.adk import Agent
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)

class IntentType(Enum):
    """Primary intent types."""
    CREATE_WORKOUT = "create_workout"
    CREATE_ROUTINE = "create_routine"
    ANALYZE_PROGRESS = "analyze_progress"
    MODIFY_EXERCISE = "modify_exercise"
    GET_ADVICE = "get_advice"
    START_WORKOUT = "start_workout"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"

class WorkoutScope(Enum):
    """Workout scope types."""
    SINGLE_SESSION = "single_session"
    WEEKLY_ROUTINE = "weekly_routine"
    PROGRAM = "program"
    QUICK_WORKOUT = "quick_workout"
    
@dataclass
class ExtractedIntent:
    """Structured intent output."""
    primary_intent: str
    scope: Optional[str] = None
    constraints: Dict[str, Any] = None
    entities: Dict[str, Any] = None
    ambiguities: List[str] = None
    confidence: float = 0.0
    requires_clarification: bool = False
    suggested_questions: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {}
        for key, value in asdict(self).items():
            if value is not None:
                result[key] = value
        return result

def extract_context_hints(message: str) -> tuple[str, Dict[str, str]]:
    """Extract context hints from message prefix."""
    import re
    
    # Look for (context: ...) pattern
    match = re.search(r'\(context:([^)]*)\)', message, re.IGNORECASE)
    if not match:
        return message, {}
    
    context_str = match.group(1)
    clean_message = message.replace(match.group(0), '').strip()
    
    # Parse context key-value pairs
    context = {}
    for pair in context_str.split():
        if '=' in pair:
            key, value = pair.split('=', 1)
            context[key.strip()] = value.strip()
    
    return clean_message, context

def tool_classify_intent(
    message: str,
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Classify user intent from message.
    
    This is a deterministic tool that uses pattern matching and keyword analysis
    for fast intent extraction. Complex cases fall back to LLM reasoning.
    """
    clean_message, context_hints = extract_context_hints(message)
    message_lower = clean_message.lower()
    
    # Quick pattern matching for common intents
    intent = ExtractedIntent(primary_intent=IntentType.UNKNOWN.value)
    
    # Workout creation patterns
    if any(word in message_lower for word in ['plan', 'create', 'design', 'build', 'make']):
        if any(word in message_lower for word in ['workout', 'session', 'training']):
            intent.primary_intent = IntentType.CREATE_WORKOUT.value
            intent.scope = WorkoutScope.SINGLE_SESSION.value
            
            # Extract muscle groups
            muscle_keywords = {
                'upper body': ['chest', 'shoulders', 'arms', 'back'],
                'lower body': ['legs', 'glutes', 'quads', 'hamstrings'],
                'core': ['abs', 'core'],
                'full body': ['all'],
            }
            
            constraints = {}
            for group, muscles in muscle_keywords.items():
                if group in message_lower:
                    constraints['muscle_groups'] = muscles
                    break
            
            # Check for specific muscles
            all_muscles = ['chest', 'back', 'shoulders', 'arms', 'biceps', 'triceps', 
                          'legs', 'quads', 'hamstrings', 'glutes', 'abs', 'core']
            mentioned_muscles = [m for m in all_muscles if m in message_lower]
            if mentioned_muscles:
                constraints['muscle_groups'] = mentioned_muscles
            
            intent.constraints = constraints
            intent.confidence = 0.9 if constraints else 0.7
            
        elif any(word in message_lower for word in ['routine', 'program', 'split']):
            intent.primary_intent = IntentType.CREATE_ROUTINE.value
            intent.scope = WorkoutScope.WEEKLY_ROUTINE.value
            intent.confidence = 0.85
    
    # Progress analysis patterns
    elif any(word in message_lower for word in ['progress', 'growing', 'improving', 'gains']):
        intent.primary_intent = IntentType.ANALYZE_PROGRESS.value
        intent.confidence = 0.8
        
        # Extract what to analyze
        entities = {}
        if 'strength' in message_lower:
            entities['metric'] = 'strength'
        elif 'muscle' in message_lower or 'size' in message_lower:
            entities['metric'] = 'hypertrophy'
        intent.entities = entities
    
    # Start workout patterns
    elif any(word in message_lower for word in ['start', 'begin', 'let\'s do', 'ready']):
        if 'workout' in message_lower:
            intent.primary_intent = IntentType.START_WORKOUT.value
            intent.scope = WorkoutScope.QUICK_WORKOUT.value
            intent.confidence = 0.9
    
    # Ambiguous or clarification needed
    if intent.confidence < 0.7:
        intent.requires_clarification = True
        intent.suggested_questions = [
            "What would you like to do - create a workout, start training, or analyze progress?",
            "Are you looking for a single workout or a full program?",
        ]
    
    # Add context hints to entities
    if context_hints:
        if not intent.entities:
            intent.entities = {}
        intent.entities.update(context_hints)
    
    result = intent.to_dict()
    logger.info(f"Intent extracted: {result}")
    return result

# Create the Intent Extractor agent
intent_extractor_agent = Agent(
    name="IntentExtractor",
    model="gemini-2.5-flash",  # Gemini 2.5 Flash for quick classification
    instruction="""
    You are an intent classifier for a fitness app. Extract user intent quickly and accurately.
    
    For each message:
    1. Identify the primary intent (create_workout, analyze_progress, etc.)
    2. Extract key entities (muscle groups, time constraints, equipment)
    3. Note any ambiguities that need clarification
    4. Assess confidence level
    
    Call tool_classify_intent first for pattern matching, then enhance with reasoning if needed.
    
    Output structured JSON with:
    - primary_intent
    - scope (single_session, routine, etc.)
    - constraints (muscle_groups, duration, equipment)
    - entities (specific details mentioned)
    - ambiguities (what's unclear)
    - confidence (0-1)
    - requires_clarification (boolean)
    - suggested_questions (if clarification needed)
    
    Be fast and decisive. This should take <200ms.
    """,
    tools=[
        FunctionTool(func=tool_classify_intent),
    ],
)
