"""StrengthOS Agent - Fitness AI Assistant powered by Google ADK

This agent provides comprehensive fitness coaching capabilities including:
- User profile and fitness assessment with state persistence
- Exercise database and search with caching
- Workout template creation and management
- Training routine scheduling
- Workout history analysis
- Advanced memory and state management for Agent Engine
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from google.adk.agents import Agent
from google.adk.tools import FunctionTool, ToolContext
# Temporarily disable load_memory until proper memory service is configured
# from google.adk.tools import load_memory
# from google.adk.tools import load_memory  # Built-in memory tool - disabled due to config issues
import requests
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase Functions Configuration
FIREBASE_BASE_URL = "https://us-central1-myon-53d85.cloudfunctions.net"
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")

# Helper function for Firebase API calls
def make_firebase_request(
    endpoint: str, 
    method: str = "GET", 
    data: Optional[Dict] = None,
    user_id: Optional[str] = None,
    params: Optional[Dict] = None
) -> Dict[str, Any]:
    """Make authenticated requests to Firebase Functions."""
    url = f"{FIREBASE_BASE_URL}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": FIREBASE_API_KEY  # Changed back to X-API-Key header
    }
    
    # Build params - add user_id if provided
    if params is None:
        params = {}
    if user_id:
        params["userId"] = user_id
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=15)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, params=params, timeout=15)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data, params=params, timeout=15)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, params=params, timeout=15)
        else:
            raise ValueError(f"Unsupported method: {method}")
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Firebase request failed: {e}")
        return {"error": str(e), "success": False}

# Helper functions for response formatting
def format_exercise_for_display(exercise_data: Dict[str, Any], sets_config: List[Dict[str, Any]] = None) -> str:
    """Format exercise information for clean display in responses."""
    name = exercise_data.get("name", "Unknown Exercise")
    muscles = exercise_data.get("primaryMuscles", [])
    equipment = exercise_data.get("equipment", "No equipment")
    
    output = f"**{name}**\n"
    output += f"- Target: {', '.join(muscles) if muscles else 'Multiple'}\n"
    output += f"- Equipment: {equipment}\n"
    
    if sets_config:
        for i, set_data in enumerate(sets_config, 1):
            set_type = set_data.get("type", "Working Set")
            reps = set_data.get("reps", 10)
            rir = set_data.get("rir", 2)
            output += f"- Set {i}: {reps} reps @ RIR {rir} ({set_type})\n"
    
    return output

def format_template_summary(template_data: Dict[str, Any]) -> str:
    """Format template for concise display."""
    name = template_data.get("name", "Unnamed Template")
    desc = template_data.get("description", "")
    exercise_count = len(template_data.get("exercises", []))
    
    output = f"**{name}**\n"
    if desc:
        output += f"*{desc}*\n"
    output += f"- {exercise_count} exercises\n"
    
    # Calculate total volume
    total_sets = sum(len(ex.get("sets", [])) for ex in template_data.get("exercises", []))
    output += f"- {total_sets} total sets\n"
    
    return output

# State management helper functions
def get_cached_user_id(state: Dict[str, Any]) -> Optional[str]:
    """Get cached user_id from state."""
    return state.get("user:id") or state.get("user_id")

def cache_user_data(state: Dict[str, Any], user_data: Dict[str, Any]) -> None:
    """Cache important user data in state with proper prefixes."""
    if user_data.get("id"):
        state["user:id"] = user_data["id"]
    if user_data.get("name"):
        state["user:name"] = user_data["name"]
    
    context = user_data.get("contextData", {})
    if context.get("fitnessGoals"):
        state["user:goals"] = context["fitnessGoals"]
    if context.get("fitnessLevel"):
        state["user:level"] = context["fitnessLevel"]
    if context.get("availableEquipment"):
        state["user:equipment"] = context["availableEquipment"]

# Tool implementations with state management
def get_user(user_id: str) -> Dict[str, Any]:
    """Fetch comprehensive user profile including fitness context and recent activity.
    
    What this tool does:
        Retrieves the complete user profile document with personal information, fitness preferences,
        goals, and enriched context about their recent workout activity, active routines, and
        physical attributes.
    
    When to use it:
        - When starting a conversation to understand the user's fitness context
        - When asked about user's goals, experience level, or equipment preferences
        - When needing demographic information (height, weight) for calculations
        - When creating personalized workout recommendations
        - Before analyzing workouts to understand user's fitness level
    
    Args:
        user_id: The Firebase UID of the user whose profile to retrieve
        
    Returns:
        JSON string with the following structure:
        {
            "success": bool,
            "data": {
                "name": str,
                "email": str,
                "provider": str,
                "uid": str,
                "created_at": ISO date string
            },
            "context": {
                "recentWorkoutsCount": int,
                "lastWorkoutDate": ISO date string or null,
                "daysSinceLastWorkout": int or null,
                "hasActiveRoutine": bool,
                "activeRoutineName": str or null,
                "hasTemplates": bool,
                "fitnessLevel": str ("beginner", "intermediate", "advanced"),
                "preferredEquipment": str,
                "fitnessGoals": str ("muscle_gain", "strength", "fat_loss", etc.),
                "experienceLevel": str,
                "availableEquipment": str ("full gym", "home gym", "minimal", etc.),
                "workoutFrequency": int (target workouts per week),
                "height": float (in cm),
                "weight": float (in kg),
                "fitnessProfile": nested object with detailed attributes
            },
            "metadata": {
                "function": "get-user",
                "userId": str,
                "requestedAt": ISO date string,
                "authType": str,
                "source": str
            }
        }
    """
    result = make_firebase_request("getUser", user_id=user_id)
    return result

def update_user(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update user profile information.
    
    Args:
        user_id: The user's unique identifier
        updates: Dictionary of fields to update
        
    Returns:
        Updated user profile
    """
    payload = {"userId": user_id, "userData": updates}
    result = make_firebase_request("updateUser", method="POST", data=payload)
    return result

def list_exercises(
    muscle_group: Optional[str] = None,
    equipment: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """List exercises with optional filters.
    
    Args:
        muscle_group: Filter by muscle group (e.g., "chest", "back", "legs")
        equipment: Filter by equipment (e.g., "barbell", "dumbbell", "bodyweight")
        difficulty: Filter by difficulty (e.g., "beginner", "intermediate", "advanced")
        limit: Maximum number of exercises to return
        
    Returns:
        List of exercises matching the criteria
    """
    params = {
        "muscleGroup": muscle_group,
        "equipment": equipment,
        "difficulty": difficulty,
        "limit": limit
    }
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    
    result = make_firebase_request("getExercises", params=params)
    return result

def search_exercises(
    query: Optional[str] = None,
    muscle_groups: Optional[str] = None,
    equipment: Optional[str] = None,
    movement_type: Optional[str] = None,
    level: Optional[str] = None
) -> Dict[str, Any]:
    """Search and filter exercises based on various criteria.
    
    What this tool does:
        Searches the exercise database using multiple filters including text search,
        muscle groups, equipment availability, movement type, and difficulty level.
        Returns a filtered list of exercises matching the criteria.
    
    When to use it:
        - When user asks for exercises for specific muscle groups
        - When finding exercises that match available equipment
        - When user wants beginner-friendly or advanced exercises
        - When building templates and need exercise options
        - When user asks "Show me chest exercises" or similar queries
    
    Args:
        query: Optional. Text search in exercise names (e.g., "press", "squat")
        muscle_groups: Optional. Comma-separated muscle groups (e.g., "chest,shoulders")
        equipment: Optional. Comma-separated equipment (e.g., "barbell,dumbbell")
        movement_type: Optional. Filter by "compound" or "isolation"
        level: Optional. Filter by difficulty - "beginner", "intermediate", or "advanced"
        
    Returns:
        JSON string with filtered exercises and applied filters:
        {
            "success": bool,
            "data": [exercise objects matching criteria],
            "count": int,
            "filters_applied": {
                "query": str or null,
                "muscleGroups": [str] or null,
                "equipment": [str] or null,
                "movementType": str or null,
                "level": str or null
            }
        }
        
    Examples:
        - Chest exercises: muscle_groups="chest"
        - Home workout options: equipment="dumbbell,resistance_band,bodyweight"
        - Beginner compounds: movement_type="compound", level="beginner"
        - Search by name: query="bench press"
    """
    params: Dict[str, Any] = {}
    if query:
        params["query"] = query
    # Server supports single muscleGroup; if CSV provided, take the first value
    if muscle_groups:
        first_group = str(muscle_groups).split(",")[0].strip()
        if first_group:
            params["muscleGroup"] = first_group
    # Server supports single equipment value; if CSV provided, take the first value
    if equipment:
        first_equipment = str(equipment).split(",")[0].strip()
        if first_equipment:
            params["equipment"] = first_equipment
    # movement_type/level not currently supported server-side; omit to avoid confusion

    result = make_firebase_request("searchExercises", params=params)
    return result

def get_exercise(exercise_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific exercise.
    
    Args:
        exercise_id: The exercise identifier
        
    Returns:
        Detailed exercise information including instructions and tips
    """
    result = make_firebase_request("getExercise", params={"exerciseId": exercise_id})
    return result

def get_user_workouts(
    user_id: str,
    limit: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Get user's workout history.
    
    Args:
        user_id: The user's unique identifier
        limit: Maximum number of workouts to return
        start_date: Filter workouts after this date (ISO format)
        end_date: Filter workouts before this date (ISO format)
        
    Returns:
        List of user's workouts with details
    """
    params = {
        "limit": limit,
        "startDate": start_date,
        "endDate": end_date
    }
    params = {k: v for k, v in params.items() if v is not None}
    
    result = make_firebase_request("getUserWorkouts", params=params, user_id=user_id)
    return result

def get_workout(workout_id: str, user_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific workout.
    
    Args:
        workout_id: The workout identifier
        user_id: The user's unique identifier
        
    Returns:
        Detailed workout information including exercises and sets
    """
    result = make_firebase_request("getWorkout", params={"workoutId": workout_id}, user_id=user_id)
    return result

# Template management functions
def get_user_templates(user_id: str) -> Dict[str, Any]:
    """Get all workout templates for a user.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        List of user's workout templates
    """
    result = make_firebase_request("getUserTemplates", user_id=user_id)
    return result

def get_template(template_id: str, user_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific template.
    
    Args:
        template_id: The template identifier
        user_id: The user's unique identifier
        
    Returns:
        Detailed template information
    """
    result = make_firebase_request(
        "getTemplate",
        params={"templateId": template_id, "userId": user_id},
    )
    return result

def create_template(
    user_id: str,
    name: str,
    description: str,
    exercises: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create a new workout template with exercises and set configurations.
    
    What this tool does:
        Creates a new reusable workout template with specified exercises, sets, reps, and
        rest periods. Firestore triggers automatically calculate muscle volume analytics
        for AI-created templates, including projected volume distribution across muscle groups.
    
    When to use it:
        - When user asks to create a new workout (e.g., "Create a push day workout")
        - When designing personalized training programs
        - When user wants to save a specific workout structure for reuse
        - After analyzing user's needs and designing an appropriate template
    
    Args:
        user_id: The Firebase UID of the user who will own the template
        name: Template name (e.g., "Push Day A", "Leg Hypertrophy")
        description: Brief description of the template's purpose
        exercises: List of exercise dictionaries with structure:
            [{
                "exercise_id": "exercise123",
                "position": 0,
                "sets": [{
                    "reps": 8,
                    "rir": 2,
                    "type": "Working Set",
                    "weight": 100.0  # should follow the user's weight unit (kg or lbs)
                }]
            }]
    
    Returns:
        JSON string with created template:
        {
            "success": bool,
            "data": {
                "id": str (newly created template ID),
                "user_id": str,
                "name": str,
                "description": str,
                "exercises": [...],
                "created_at": ISO date string,
                "updated_at": ISO date string
            }
        }
        
    Note: 
        - Analytics are automatically calculated by Firestore triggers
        - Weight values should match user's unit preference (kg/lbs)
    """
    # Ensure each exercise has required fields and generate IDs
    for i, exercise in enumerate(exercises):
        if "position" not in exercise:
            exercise["position"] = i
        if "id" not in exercise:
            exercise["id"] = f"template_exercise_{uuid.uuid4()}"
        for j, set_data in enumerate(exercise.get("sets", [])):
            if "id" not in set_data:
                set_data["id"] = f"set_{uuid.uuid4()}"
            if "type" not in set_data:
                set_data["type"] = "Working Set"
    
    template_data = {
        "userId": user_id,
        "template": {
            "user_id": user_id,  # Add user_id inside template object
            "name": name,
            "description": description,
            "exercises": exercises
        }
    }
    
    result = make_firebase_request("createTemplate", method="POST", data=template_data)
    return result

def update_template(
    template_id: str,
    user_id: str,
    updates: Dict[str, Any]
) -> Dict[str, Any]:
    """Update an existing workout template.
    
    Args:
        template_id: The template identifier
        user_id: The user's unique identifier
        updates: Dictionary of fields to update (name, description, exercises)
        
    Returns:
        Updated template information
    """
    # Structure the update data properly
    update_data = {
        "userId": user_id,
        "templateId": template_id,
        "template": updates,
    }

    # Server is onRequest; send body without relying on path params
    result = make_firebase_request("updateTemplate", method="POST", data=update_data)
    return result

def delete_template(template_id: str, user_id: str) -> Dict[str, Any]:
    """Delete a workout template.
    
    Args:
        template_id: The template identifier
        user_id: The user's unique identifier
        
    Returns:
        Deletion confirmation
    """
    payload = {"userId": user_id, "templateId": template_id}
    result = make_firebase_request("deleteTemplate", method="POST", data=payload)
    return result

# Routine management functions
def get_user_routines(user_id: str) -> Dict[str, Any]:
    """Get all training routines for a user.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        List of user's training routines
    """
    result = make_firebase_request("getUserRoutines", user_id=user_id)
    return result

def get_active_routine(user_id: str) -> Dict[str, Any]:
    """Get the user's currently active routine.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        Active routine information or indication that no routine is active
    """
    result = make_firebase_request("getActiveRoutine", user_id=user_id)
    return result

def get_routine(routine_id: str, user_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific routine.
    
    Args:
        routine_id: The routine identifier
        user_id: The user's unique identifier
        
    Returns:
        Detailed routine information
    """
    params = {"userId": user_id, "routineId": routine_id}
    result = make_firebase_request("getRoutine", params=params)
    return result

def create_routine(
    user_id: str,
    name: str,
    description: str,
    frequency: int,
    template_ids: List[str]
) -> Dict[str, Any]:
    """Create a new workout routine (weekly/monthly training schedule).
    
    Args:
        user_id: The user's unique identifier
        name: Routine name (e.g., "Push/Pull/Legs")
        description: Brief description of the routine's goals
        frequency: Number of workouts per week (1-7)
        template_ids: List of template IDs to include in the routine
        
    Returns:
        Created routine information
    """
    routine_data = {
        "userId": user_id,
        "routine": {
            "user_id": user_id,  # Add user_id inside routine object
            "name": name,
            "description": description,
            "frequency": frequency,
            "template_ids": template_ids
        }
    }
    
    result = make_firebase_request("createRoutine", method="POST", data=routine_data)
    return result

def update_routine(
    routine_id: str,
    user_id: str,
    name: str,
    description: str,
    frequency: int
) -> Dict[str, Any]:
    """Update an existing workout routine's metadata.
    
    Args:
        routine_id: The routine identifier
        user_id: The user's unique identifier
        name: New name for the routine
        description: New description
        frequency: New weekly frequency
        
    Returns:
        Updated routine information
    """
    update_data = {
        "userId": user_id,
        "routineId": routine_id,
        "routine": {
            "name": name,
            "description": description,
            "frequency": frequency
        }
    }
    
    result = make_firebase_request("updateRoutine", method="POST", data=update_data)
    return result

def delete_routine(routine_id: str, user_id: str) -> Dict[str, Any]:
    """Delete a workout routine.
    
    Args:
        routine_id: The routine identifier
        user_id: The user's unique identifier
        
    Returns:
        Deletion confirmation
    """
    delete_data = {
        "userId": user_id,
        "routineId": routine_id
    }
    
    result = make_firebase_request("deleteRoutine", method="POST", data=delete_data)
    return result

def set_active_routine(user_id: str, routine_id: str) -> Dict[str, Any]:
    """Set a routine as the user's active training program.
    
    Args:
        user_id: The user's unique identifier
        routine_id: The routine to set as active
        
    Returns:
        Confirmation of the activated routine
    """
    data = {
        "userId": user_id,
        "routineId": routine_id
    }
    
    result = make_firebase_request("setActiveRoutine", method="POST", data=data)
    return result

# Store important facts tool


def store_important_fact(fact: str, category: str, tool_context: ToolContext, **kwargs) -> dict:
    """Save a user-specific important fact (e.g. injuries, limitations, disabilities).

    Use this tool whenever the user shares personal information that could
    impact training recommendations – especially injuries, pain, mobility
    limitations, chronic conditions, or disabilities.

    Args:
        fact: The exact text or concise summary you want to remember.
        category: One of "injury", "limitation", "disability", "pain", or "other".
        tool_context: (Injected) provides access to the current session state.

    Behavior:
        Adds the fact to a "user:important_facts" list in state. The "user:" prefix
        indicates this data should persist across sessions for the same user when
        using Vertex AI Agent Engine Sessions. Each entry includes the fact, 
        category, a timestamp, and a stable id. Existing facts are preserved.

    Returns:
        {"status": "success", "stored_count": int}
    """
    key = "user:important_facts"
    current = tool_context.state.get(key, [])

    now = datetime.utcnow().isoformat()
    entry: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "fact": fact,
        "category": category,
        "timestamp": now,
        "last_seen_at": now,
        "mentions": 1,
        "status": "active",  # active|expired|archived
    }
    # Optional TTL support
    if kwargs.get("ttl_days"):
        try:
            ttl_days = int(kwargs["ttl_days"])  # type: ignore[index]
            entry["expires_at"] = (
                datetime.utcnow()
                .replace(microsecond=0)
                .isoformat()
            )
            # Store review_at as a hint for future checks
            entry["review_at"] = now
        except Exception:
            pass

    current.append(entry)
    tool_context.state[key] = current
    return {"status": "success", "stored_count": len(current)}


# Add function to retrieve facts from current session

def get_important_facts(tool_context: ToolContext) -> dict:
    """Retrieve important facts about the user from the current session.
    
    This tool retrieves any injuries, limitations, or other important facts
    that were stored during the current conversation. For any legacy entries
    missing an id, a stable id is added and written back once.
    
    Args:
        tool_context: (Injected) provides access to the current session state.
    
    Returns:
        {"facts": list of stored facts, "count": number of facts}
    """
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))

    changed = False
    for entry in facts:
        if "id" not in entry or not entry.get("id"):
            entry["id"] = str(uuid.uuid4())
            changed = True
        # hydrate counters/last_seen fields
        if not entry.get("last_seen_at"):
            entry["last_seen_at"] = datetime.utcnow().isoformat()
        if not isinstance(entry.get("mentions"), int):
            entry["mentions"] = 1
    if changed:
        tool_context.state[key] = facts

    return {"facts": facts, "count": len(facts)}


def update_important_fact(
    fact_id: str,
    tool_context: ToolContext,
    fact: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Update an existing important fact by id.

    Args:
        fact_id: The id of the fact to update
        fact: Optional new fact text
        category: Optional new category
        tool_context: (Injected) session state access

    Returns:
        {"status": "success"|"not_found", "updated": int}
    """
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))

    updated = 0
    for entry in facts:
        if entry.get("id") == fact_id:
            if fact is not None:
                entry["fact"] = fact
            if category is not None:
                entry["category"] = category
            # Update timestamp to reflect modification
            entry["timestamp"] = datetime.utcnow().isoformat()
            updated += 1
            break

    if updated:
        tool_context.state[key] = facts
        return {"status": "success", "updated": updated}
    return {"status": "not_found", "updated": 0}


def delete_important_fact(fact_id: str, tool_context: ToolContext) -> dict:
    """Delete an important fact by id.

    Args:
        fact_id: The id of the fact to remove
        tool_context: (Injected) session state access

    Returns:
        {"status": "success"|"not_found", "deleted": int}
    """
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))

    new_facts = [f for f in facts if f.get("id") != fact_id]
    deleted = len(facts) - len(new_facts)

    if deleted:
        tool_context.state[key] = new_facts
        return {"status": "success", "deleted": deleted}
    return {"status": "not_found", "deleted": 0}


def clear_important_facts(confirm: bool, tool_context: ToolContext) -> dict:
    """Clear all important facts when confirm=True.

    Args:
        confirm: Must be True to perform the deletion
        tool_context: (Injected) session state access

    Returns:
        {"status": "success"|"cancelled", "deleted": int}
    """
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))

    if not confirm:
        return {"status": "cancelled", "deleted": 0}

    deleted = len(facts)
    tool_context.state[key] = []
    return {"status": "success", "deleted": deleted}


# Convenience: search and delete facts by matching text
def find_facts_by_text(query: str, tool_context: ToolContext) -> dict:
    """Find facts containing query (case-insensitive)."""
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))
    q = (query or "").strip().lower()
    matches = [f for f in facts if q and q in str(f.get("fact", "")).lower()]
    return {"matches": matches, "count": len(matches)}


def delete_facts_by_text(query: str, confirm: bool, tool_context: ToolContext) -> dict:
    """Delete all facts whose text contains query.

    If confirm is False, returns matched ids without deleting.
    """
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))
    q = (query or "").strip().lower()
    matched_ids = [f.get("id") for f in facts if q and q in str(f.get("fact", "")).lower()]
    if not confirm:
        return {"status": "preview", "matched_ids": matched_ids, "count": len(matched_ids)}
    new_facts = [f for f in facts if f.get("id") not in matched_ids]
    tool_context.state[key] = new_facts
    return {"status": "success", "deleted": len(matched_ids), "deleted_ids": matched_ids}


def upsert_preference(preference_text: str, tool_context: ToolContext, confidence: float = 0.8) -> dict:
    """Store or update a user preference as an important fact (category=preference)."""
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))
    now = datetime.utcnow().isoformat()
    updated = False
    for f in facts:
        if f.get("category") == "preference" and str(f.get("fact", "")).strip().lower() == preference_text.strip().lower():
            f["last_seen_at"] = now
            f["mentions"] = int(f.get("mentions", 0)) + 1
            f["confidence"] = max(float(f.get("confidence", 0.0)), confidence)
            updated = True
            break
    if not updated:
        facts.append({
            "id": str(uuid.uuid4()),
            "fact": preference_text,
            "category": "preference",
            "timestamp": now,
            "last_seen_at": now,
            "mentions": 1,
            "status": "active",
            "confidence": confidence,
        })
    tool_context.state[key] = facts
    return {"status": "success", "updated": updated, "count": len(facts)}


def upsert_temporary_condition(condition_text: str, tool_context: ToolContext, ttl_days: int = 14) -> dict:
    """Store a temporary condition (e.g., cold) with a TTL to auto-review/expire."""
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))
    now = datetime.utcnow()
    expires_at = now + __import__("datetime").timedelta(days=int(ttl_days))
    exists = False
    for f in facts:
        if f.get("category") == "condition" and str(f.get("fact", "")).strip().lower() == condition_text.strip().lower():
            f["last_seen_at"] = now.isoformat()
            f["mentions"] = int(f.get("mentions", 0)) + 1
            f["expires_at"] = expires_at.isoformat()
            f["status"] = "active"
            exists = True
            break
    if not exists:
        facts.append({
            "id": str(uuid.uuid4()),
            "fact": condition_text,
            "category": "condition",
            "timestamp": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "mentions": 1,
            "status": "active",
            "expires_at": expires_at.isoformat(),
        })
    tool_context.state[key] = facts
    return {"status": "success", "exists": exists}


def review_and_decay_memories(tool_context: ToolContext, auto_delete_expired: bool = True) -> dict:
    """Review stored facts: expire temporaries past TTL and return a summary of changes."""
    key = "user:important_facts"
    facts: List[Dict[str, Any]] = list(tool_context.state.get(key, []))
    now = datetime.utcnow()
    expired_ids: List[str] = []
    for f in facts:
        exp = f.get("expires_at")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                if now >= exp_dt and f.get("status") != "expired":
                    f["status"] = "expired"
                    expired_ids.append(str(f.get("id")))
            except Exception:
                continue
    if auto_delete_expired and expired_ids:
        facts = [f for f in facts if str(f.get("id")) not in expired_ids]
    tool_context.state[key] = facts
    return {"status": "success", "expired": expired_ids, "remaining": len(facts)}

# Add simple tool to get user ID from state
def get_my_user_id(tool_context: ToolContext) -> dict:
    """Get the current user's ID from session state.
    
    This should be called at the start of conversations to retrieve
    the user ID that was stored when the session was created.
    
    Args:
        tool_context: (Injected) provides access to the current session state.
    
    Returns:
        {"user_id": str or None, "found": bool}
    """
    user_id = get_cached_user_id(tool_context.state)
    return {"user_id": user_id, "found": user_id is not None}

def get_analysis_context(
    user_id: str,
    tool_context: ToolContext,
    workouts_limit: int = 20,
    include_templates: bool = False,
) -> dict:
    """Fetch key data in parallel for performance analysis.

    Retrieves user profile, recent workouts, routine context, and important facts
    concurrently to minimize latency. Optionally includes templates.

    Args:
        user_id: Firebase UID
        tool_context: (Injected) session state access
        workouts_limit: Max number of recent workouts to fetch
        include_templates: Whether to also include templates

    Returns:
        Combined dictionary with keys: user, workouts, activeRoutine, routines,
        importantFacts, (optional) templates
    """
    results = {
        "user": None,
        "workouts": None,
        "activeRoutine": None,
        "routines": None,
        "importantFacts": get_important_facts(tool_context),
    }

    def _fetch_user():
        return get_user(user_id)

    def _fetch_workouts():
        return get_user_workouts(user_id=user_id, limit=workouts_limit)

    def _fetch_active_routine():
        return get_active_routine(user_id)

    def _fetch_routines():
        return get_user_routines(user_id)

    def _fetch_templates():
        return get_user_templates(user_id)

    tasks = {
        "user": _fetch_user,
        "workouts": _fetch_workouts,
        "activeRoutine": _fetch_active_routine,
        "routines": _fetch_routines,
    }
    if include_templates:
        tasks["templates"] = _fetch_templates

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_key = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = {"error": str(e)}

    return results

def validate_template_payload(template: Dict[str, Any]) -> dict:
    """Validate and normalize a workout template payload.

    Rules:
    - name: non-empty string
    - exercises: non-empty list
      - each exercise requires exercise_id (str) and sets (non-empty list)
      - sets entries require reps (int), weight (float|int), type (default "Working Set")
      - optional: rir (int), rest (int seconds)
      - convert numeric strings to numbers when safe
      - reject ranges like "8-12"; pick a single value is caller's job
    - positions are integers if present

    Returns: { valid: bool, errors: list[str], normalized: dict }
    """
    errors: List[str] = []
    normalized = dict(template or {})

    name = normalized.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")

    exercises = normalized.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        errors.append("exercises must be a non-empty list")
        return {"valid": False, "errors": errors, "normalized": normalized}

    norm_exercises: List[Dict[str, Any]] = []
    for idx, ex in enumerate(exercises):
        if not isinstance(ex, dict):
            errors.append(f"exercise[{idx}] must be an object")
            continue
        exercise_id = ex.get("exercise_id") or ex.get("id")
        if not isinstance(exercise_id, str) or not exercise_id:
            errors.append(f"exercise[{idx}].exercise_id missing")
        sets = ex.get("sets")
        if not isinstance(sets, list) or not sets:
            errors.append(f"exercise[{idx}].sets must be a non-empty list")
            continue
        pos = ex.get("position")
        if pos is not None:
            try:
                pos = int(pos)
            except Exception:
                errors.append(f"exercise[{idx}].position must be an integer")
        norm_sets: List[Dict[str, Any]] = []
        for sidx, s in enumerate(sets):
            if not isinstance(s, dict):
                errors.append(f"exercise[{idx}].sets[{sidx}] must be an object")
                continue
            rep_val = s.get("reps")
            if isinstance(rep_val, str) and rep_val.strip().isdigit():
                rep_val = int(rep_val.strip())
            if not isinstance(rep_val, int):
                errors.append(f"exercise[{idx}].sets[{sidx}].reps must be int")
            wt_val = s.get("weight")
            if isinstance(wt_val, str):
                try:
                    wt_val = float(wt_val.strip())
                except Exception:
                    errors.append(f"exercise[{idx}].sets[{sidx}].weight must be number")
            if not isinstance(wt_val, (int, float)):
                errors.append(f"exercise[{idx}].sets[{sidx}].weight must be number")
            rir_val = s.get("rir")
            if rir_val is not None:
                try:
                    rir_val = int(rir_val)
                except Exception:
                    errors.append(f"exercise[{idx}].sets[{sidx}].rir must be int if present")
            set_type = s.get("type") or "Working Set"
            rest_val = s.get("rest")
            if rest_val is not None:
                try:
                    rest_val = int(rest_val)
                except Exception:
                    errors.append(f"exercise[{idx}].sets[{sidx}].rest must be int seconds")
            norm_sets.append({
                "reps": rep_val,
                "weight": wt_val,
                "rir": rir_val,
                "type": set_type,
                "rest": rest_val,
            })
        norm_exercises.append({
            "exercise_id": exercise_id,
            "position": pos if pos is not None else idx + 1,
            "sets": norm_sets,
        })
    normalized["exercises"] = norm_exercises

    return {"valid": len(errors) == 0, "errors": errors, "normalized": normalized}


def insert_template(user_id: str, template: Dict[str, Any]) -> str:
    """Validate then create a template for the user.

    Returns JSON with success and created template info or validation errors.
    """
    check = validate_template_payload(template)
    if not check["valid"]:
        return json.dumps({"success": False, "errors": check["errors"]}, indent=2)
    normalized = check["normalized"]
    payload = {
        "user_id": user_id,
        "name": normalized.get("name"),
        "description": normalized.get("description"),
        "exercises": normalized.get("exercises", []),
    }
    return create_template(user_id=user_id, name=payload["name"], description=payload.get("description"), exercises=payload["exercises"])  # type: ignore


def update_template_with_validation(template_id: str, user_id: str, updates: Dict[str, Any]) -> str:
    """Validate updates (if exercises provided) then update the template.

    Returns JSON with success or validation errors.
    """
    if updates.get("exercises") is not None:
        check = validate_template_payload({"name": updates.get("name", "tmp"), "exercises": updates.get("exercises")})
        if not check["valid"]:
            return json.dumps({"success": False, "errors": check["errors"]}, indent=2)
        updates = {**updates, "exercises": check["normalized"]["exercises"]}
    return update_template(template_id=template_id, user_id=user_id, updates=updates)

# Create FunctionTool instances with state parameter
tools = [
    # User management
    FunctionTool(func=get_user),
    FunctionTool(func=update_user),

    # Exercise database
    FunctionTool(func=list_exercises),
    FunctionTool(func=search_exercises),
    FunctionTool(func=get_exercise),

    # Workout history
    FunctionTool(func=get_user_workouts),
    FunctionTool(func=get_workout),

    # Template management
    FunctionTool(func=get_user_templates),
    FunctionTool(func=get_template),
    FunctionTool(func=create_template),
    FunctionTool(func=update_template),
    FunctionTool(func=delete_template),
    # Validation helpers
    FunctionTool(func=validate_template_payload),
    FunctionTool(func=insert_template),
    FunctionTool(func=update_template_with_validation),

    # Routine management
    FunctionTool(func=get_user_routines),
    FunctionTool(func=get_active_routine),
    FunctionTool(func=get_routine),
    FunctionTool(func=create_routine),
    FunctionTool(func=update_routine),
    FunctionTool(func=delete_routine),
    FunctionTool(func=set_active_routine),

    # Memory / facts persistence
    FunctionTool(func=store_important_fact),
    FunctionTool(func=get_important_facts),
    FunctionTool(func=update_important_fact),
    FunctionTool(func=delete_important_fact),
    FunctionTool(func=clear_important_facts),
    FunctionTool(func=get_my_user_id),

    # Memory helpers
    FunctionTool(func=find_facts_by_text),
    FunctionTool(func=delete_facts_by_text),
    FunctionTool(func=upsert_preference),
    FunctionTool(func=upsert_temporary_condition),
    FunctionTool(func=review_and_decay_memories),

    # Aggregated parallel fetch for analysis
    FunctionTool(func=get_analysis_context),

    # Expose built-in memory retrieval tool so the agent can recall facts
    # load_memory,
]

# Agent configuration with concise, high-signal instructions
AGENT_INSTRUCTION = """You are StrengthOS, a concise fitness assistant.

Output policy (strict):
- Be brief and analytical; avoid filler and engagement phrases.
- Start directly with the answer. No greetings or long preambles.
- Prefer compact bullets with bold labels: "- **label**: fact".
- Keep to ≤6 bullets or ≤6 short sentences per answer.
- Avoid section headings unless explicitly requested.
- Use consistent markdown only: '-', '*', numbers. Do not emit the '•' symbol.
- Ensure each bullet starts on its own new line.

Tooling protocol:
- Announce actions before tool calls with a single short line (e.g., "Fetching workouts...").
- If multiple data lookups are needed, use get_analysis_context to fetch in parallel.

Evidence policy:
- Use science-based guidance (volume landmarks, progressive overload). Cite at a high level when relevant.

Templates/Routines (format rules):
- Use exact numbers for reps/weight/sets/RIR; no ranges.
- Each exercise must include exercise_id, position, and sets with reps, weight, optional rir.
- Validate with validate_template_payload before insert/update; then call insert_template or update_template_with_validation.

Memory:
- Prefer upsert_preference for stable likes/dislikes; upsert_temporary_condition for short-lived states (e.g., cold) with TTL.
- If the user says a memory is wrong or no longer applies, immediately delete it (delete_facts_by_text or delete_important_fact) and confirm.
- Store injuries/constraints/preferences with store_important_fact when unsure; then normalize with upsert_* tools.
- Read with get_important_facts; delete via delete_important_fact or delete_facts_by_text.
- Periodically call review_and_decay_memories to expire stale temporaries. Ask for confirmation before deleting ambiguous items.

Style:
- Short, factual, user-centered. Avoid repetition and self-reference. Use numbers/units explicitly.
"""

# Create the StrengthOS agent with state management
strengthos_agent = Agent(
    name="StrengthOS",
    model="gemini-2.5-flash",  # Using 2.5 Flash for fast, efficient responses
    instruction=AGENT_INSTRUCTION,
    tools=tools,
) 