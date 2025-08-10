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
def get_user(user_id: str) -> str:
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
    return json.dumps(result, indent=2)

def update_user(user_id: str, updates: Dict[str, Any]) -> str:
    """Update user profile information.
    
    Args:
        user_id: The user's unique identifier
        updates: Dictionary of fields to update
        
    Returns:
        Updated user profile
    """
    result = make_firebase_request("updateUser", method="PUT", data=updates, user_id=user_id)
    return json.dumps(result, indent=2)

def list_exercises(
    muscle_group: Optional[str] = None,
    equipment: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = 20
) -> str:
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
    
    result = make_firebase_request("getExercises", data=params)
    return json.dumps(result, indent=2)

def search_exercises(
    query: Optional[str] = None,
    muscle_groups: Optional[str] = None,
    equipment: Optional[str] = None,
    movement_type: Optional[str] = None,
    level: Optional[str] = None
) -> str:
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
    params = {}
    if query:
        params["query"] = query
    if muscle_groups:
        params["muscleGroups"] = muscle_groups
    if equipment:
        params["equipment"] = equipment
    if movement_type:
        params["movementType"] = movement_type
    if level:
        params["level"] = level
    
    result = make_firebase_request("searchExercises", params=params)
    return json.dumps(result, indent=2)

def get_exercise(exercise_id: str) -> str:
    """Get detailed information about a specific exercise.
    
    Args:
        exercise_id: The exercise identifier
        
    Returns:
        Detailed exercise information including instructions and tips
    """
    result = make_firebase_request(f"getExercise/{exercise_id}")
    return json.dumps(result, indent=2)

def get_user_workouts(
    user_id: str,
    limit: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
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
    
    result = make_firebase_request("getUserWorkouts", data=params, user_id=user_id)
    return json.dumps(result, indent=2)

def get_workout(workout_id: str, user_id: str) -> str:
    """Get detailed information about a specific workout.
    
    Args:
        workout_id: The workout identifier
        user_id: The user's unique identifier
        
    Returns:
        Detailed workout information including exercises and sets
    """
    result = make_firebase_request(f"getWorkout/{workout_id}", user_id=user_id)
    return json.dumps(result, indent=2)

# Template management functions
def get_user_templates(user_id: str) -> str:
    """Get all workout templates for a user.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        List of user's workout templates
    """
    result = make_firebase_request("getUserTemplates", user_id=user_id)
    return json.dumps(result, indent=2)

def get_template(template_id: str, user_id: str) -> str:
    """Get detailed information about a specific template.
    
    Args:
        template_id: The template identifier
        user_id: The user's unique identifier
        
    Returns:
        Detailed template information
    """
    result = make_firebase_request(f"getTemplate/{template_id}", user_id=user_id)
    return json.dumps(result, indent=2)

def create_template(
    user_id: str,
    name: str,
    description: str,
    exercises: List[Dict[str, Any]]
) -> str:
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
    return json.dumps(result, indent=2)

def update_template(
    template_id: str,
    user_id: str,
    updates: Dict[str, Any]
) -> str:
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
        "template": updates  # The updates should contain fields like name, description, exercises
    }
    
    result = make_firebase_request(f"updateTemplate/{template_id}", method="PUT", data=update_data, user_id=user_id)
    return json.dumps(result, indent=2)

def delete_template(template_id: str, user_id: str) -> str:
    """Delete a workout template.
    
    Args:
        template_id: The template identifier
        user_id: The user's unique identifier
        
    Returns:
        Deletion confirmation
    """
    result = make_firebase_request(f"deleteTemplate/{template_id}", method="DELETE", user_id=user_id)
    return json.dumps(result, indent=2)

# Routine management functions
def get_user_routines(user_id: str) -> str:
    """Get all training routines for a user.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        List of user's training routines
    """
    result = make_firebase_request("getUserRoutines", user_id=user_id)
    return json.dumps(result, indent=2)

def get_active_routine(user_id: str) -> str:
    """Get the user's currently active routine.
    
    Args:
        user_id: The user's unique identifier
        
    Returns:
        Active routine information or indication that no routine is active
    """
    result = make_firebase_request("getActiveRoutine", user_id=user_id)
    return json.dumps(result, indent=2)

def get_routine(routine_id: str, user_id: str) -> str:
    """Get detailed information about a specific routine.
    
    Args:
        routine_id: The routine identifier
        user_id: The user's unique identifier
        
    Returns:
        Detailed routine information
    """
    params = {
        "userId": user_id,
        "routineId": routine_id
    }
    
    result = make_firebase_request("getRoutine", params=params)
    return json.dumps(result, indent=2)

def create_routine(
    user_id: str,
    name: str,
    description: str,
    frequency: int,
    template_ids: List[str]
) -> str:
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
    return json.dumps(result, indent=2)

def update_routine(
    routine_id: str,
    user_id: str,
    name: str,
    description: str,
    frequency: int
) -> str:
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
    return json.dumps(result, indent=2)

def delete_routine(routine_id: str, user_id: str) -> str:
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
    return json.dumps(result, indent=2)

def set_active_routine(user_id: str, routine_id: str) -> str:
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
    return json.dumps(result, indent=2)

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

    current.append({
        "id": str(uuid.uuid4()),
        "fact": fact,
        "category": category,
        "timestamp": datetime.utcnow().isoformat(),
    })
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
        return json.loads(get_user(user_id))

    def _fetch_workouts():
        return json.loads(get_user_workouts(user_id=user_id, limit=workouts_limit))

    def _fetch_active_routine():
        return json.loads(get_active_routine(user_id))

    def _fetch_routines():
        return json.loads(get_user_routines(user_id))

    def _fetch_templates():
        return json.loads(get_user_templates(user_id))

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

    # Aggregated parallel fetch for analysis
    FunctionTool(func=get_analysis_context),

    # Expose built-in memory retrieval tool so the agent can recall facts
    # load_memory,
]

# Agent configuration with enhanced instructions
AGENT_INSTRUCTION = """You are StrengthOS - an intelligent fitness assistant with deep knowledge of training, physiology, and personalized programming.

## RESPONSE OPTIMIZATION FOR STREAMING

### Quick Acknowledgment First
ALWAYS start responses with a brief acknowledgment (1-2 sentences) before any tool calls. This gives immediate feedback while tools execute.

Good: "I'll analyze your push day request and find the best exercises for you."
Bad: [Immediate tool call without acknowledgment]

### Progressive Information Disclosure
Break responses into digestible chunks for better streaming experience:
1. Brief acknowledgment/summary (1-2 sentences)
2. Key points or findings (bullet points work well)
3. Detailed explanations only if needed
4. Call to action or next steps

### Formatting for Readability
Use these formatting patterns for better visual flow:
- **Bold** for exercise names and important terms
- Bullet points for lists
- Short paragraphs (2-3 sentences max)
- Clear section breaks with line spacing
- Numbers for sequential steps

## TOOL USAGE OPTIMIZATION

### Parallel Tool Execution
When multiple data points are needed, call tools in parallel:
```
Example: Creating a workout template
1. search_exercises (for chest)
2. search_exercises (for shoulders) 
3. search_exercises (for triceps)
Call all three simultaneously, not sequentially!
```

### Smart Tool Sequencing
Only chain tools when output of one is required for the next:
- ✓ get_user_id → get_user (requires ID)
- ✗ get_templates + get_routines (can be parallel)

## CONVERSATION FLOW

### Session Start Protocol
1. Brief greeting: "Hey! Let me load your profile."
2. Call get_my_user_id (check session state)
3. If found: "Loading your fitness data..." → get_user + get_important_facts in parallel
4. Acknowledge what you found briefly
5. Ask how you can help today

### Creating Templates/Workouts
When users ask to create workouts:
1. Acknowledge: "I'll design a [workout type] workout for you."
2. State approach: "Let me find exercises that match your [equipment/level/goals]."
3. Search in parallel for all muscle groups
4. Present exercise selection with structure:
   - **Exercise Name** (muscle group)
     - Sets × Reps (RIR)
     - Weight (kg or lbs) tailored to the user's history if available
     - Brief form cue if relevant
5. Confirm before creating: "This template focuses on [goal]. Should I save it?"

**CRITICAL TEMPLATE RULES:**
- ALWAYS use absolute numbers for reps and weight, NEVER ranges
- ✓ Correct: "reps": 8, "weight": 100
- ✗ Wrong: "reps": "8-12", "weight": "80-120"
- Pick the middle value if you're considering a range
- Firebase expects exact numbers, not strings or ranges
- Weight is REQUIRED for every set - always include it

### Information Requests
For analysis or information queries:
1. Acknowledge what you're checking
2. Fetch data with status updates
3. Present findings in structured format:
   - Start with summary/key insight
   - Support with specific data
   - End with actionable recommendation

## RESPONSE GUIDELINES

### Keep Responses Flowing
- Start typing immediately with acknowledgment
- Use shorter sentences during streaming
- Save detailed explanations for the end
- Break up long responses with formatting

### Exercise Recommendations
When suggesting exercises:
- **Exercise Name** (ID: `abc123`)
  - Primary muscles: chest, triceps
  - Equipment: barbell
  - Suggested: 3 sets × 8 reps (RIR 2)
  - Weight: 100kg (required - based on user history)

**Note:** Always provide specific numbers, not ranges, to maintain clarity and compatibility with template creation.

### Template Creation Format
Present templates clearly:
```
**Push Day - Hypertrophy Focus**
*Target: Chest, Shoulders, Triceps*

1. **Barbell Bench Press**
   - 3 Working Sets: 8 reps, 100kg (RIR 2)
   - Rest: 2-3 minutes

2. **Dumbbell Shoulder Press**
   - 3 Working Sets: 10 reps, 20kg (RIR 2)
   - Rest: 2 minutes
```

**Remember:** Always specify exact numbers for:
- Reps: Use 8, not "8-10" or "8-12"
- Weight: Use 100, not "90-110" or "around 100"
- Sets: Use 3, not "3-4"
- RIR: Use 2, not "1-3"

When calling create_template, ensure:
- All numeric values are integers or floats, not strings or ranges
- Only provide: name, description, exercises (with exercise_id, sets, position)
- Weight is REQUIRED for every set
- The backend automatically handles timestamps and formatting

## INTERACTIVITY PATTERNS

### Confirmations
Always confirm before creating/modifying:
- "I've designed a push day template with 5 exercises. Should I save this for you?"
- "This routine includes 4 workouts per week. Ready to activate it?"

### Progressive Enhancement
Start simple, offer more:
1. Basic answer/solution first
2. "Would you like me to explain the exercise selection?"
3. "I can also create a complementary pull day if you'd like."

### Error Handling
When tools fail:
- Acknowledge the issue briefly
- Provide alternative approach
- Don't expose technical errors to user

## MEMORY AND CONTEXT

### Important Facts Storage
When users mention:
- Injuries: "I'll remember you have [injury]" → store_important_fact
- Limitations: "Noted about your [limitation]" → store_important_fact
- Preferences: "Got it, you prefer [preference]" → store_important_fact

### Context Carryover
- Reference previous conversations naturally
- "Based on your shoulder issue we discussed..."
- "Following up on the routine we created last week..."

## PERSONALITY AND TONE

Be encouraging but professional:
- Use "we" for collaborative feel
- Celebrate progress: "Great job completing..."
- Be specific with praise: "Your consistency with..."
- Supportive with challenges: "That's totally normal..."

Remember: Every response should feel immediate, helpful, and progressively detailed as it streams."""

# Create the StrengthOS agent with state management
strengthos_agent = Agent(
    name="StrengthOS",
    model="gemini-2.5-flash",  # Using 2.5 Flash for fast, efficient responses
    instruction=AGENT_INSTRUCTION,
    tools=tools,
) 