"""Exercise Selector Agent - Specialized agent for exercise selection with structured output."""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from google.adk import Agent
from google.adk.tools import FunctionTool

@dataclass
class Exercise:
    """Structured exercise representation."""
    id: str
    name: str
    primary_muscles: List[str]
    secondary_muscles: List[str]
    equipment: str
    difficulty: str  # beginner, intermediate, advanced
    movement_pattern: str  # push, pull, squat, hinge, carry, rotate
    sets: Optional[int] = 3
    reps: Optional[str] = "8-12"
    rest_seconds: Optional[int] = 90
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

@dataclass
class ExerciseSelection:
    """Structured output for exercise selection."""
    exercises: List[Exercise]
    total_volume: int  # total sets across all exercises
    estimated_duration: int  # minutes
    muscle_coverage: Dict[str, int]  # muscle -> number of exercises hitting it
    reasoning: str
    alternatives: List[Exercise]  # backup exercises if needed

def tool_search_exercises(
    muscle_groups: List[str],
    equipment: List[str],
    movement_patterns: Optional[List[str]] = None,
    exclude_exercises: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Search exercise database for matching exercises.
    
    Returns list of exercises matching criteria, sorted by relevance.
    """
    # In production, this queries a real exercise database
    # For now, return curated exercises
    exercise_db = [
        Exercise("bench_press", "Barbell Bench Press", ["chest"], ["triceps", "shoulders"], "barbell", "intermediate", "push"),
        Exercise("incline_db_press", "Incline Dumbbell Press", ["chest"], ["shoulders"], "dumbbells", "intermediate", "push"),
        Exercise("pushup", "Push-Up", ["chest"], ["triceps", "core"], "bodyweight", "beginner", "push"),
        Exercise("overhead_press", "Overhead Press", ["shoulders"], ["triceps", "core"], "barbell", "intermediate", "push"),
        Exercise("lateral_raise", "Lateral Raise", ["shoulders"], [], "dumbbells", "beginner", "push"),
        Exercise("pullup", "Pull-Up", ["back", "lats"], ["biceps"], "bodyweight", "intermediate", "pull"),
        Exercise("barbell_row", "Barbell Row", ["back"], ["biceps", "rear_delts"], "barbell", "intermediate", "pull"),
        Exercise("lat_pulldown", "Lat Pulldown", ["lats"], ["biceps"], "cable", "beginner", "pull"),
        Exercise("bicep_curl", "Bicep Curl", ["biceps"], [], "dumbbells", "beginner", "pull"),
        Exercise("tricep_extension", "Tricep Extension", ["triceps"], [], "dumbbells", "beginner", "push"),
        Exercise("squat", "Back Squat", ["quads", "glutes"], ["hamstrings", "core"], "barbell", "intermediate", "squat"),
        Exercise("deadlift", "Conventional Deadlift", ["glutes", "hamstrings"], ["back", "core"], "barbell", "advanced", "hinge"),
        Exercise("leg_press", "Leg Press", ["quads", "glutes"], [], "machine", "beginner", "squat"),
        Exercise("romanian_deadlift", "Romanian Deadlift", ["hamstrings", "glutes"], ["back"], "barbell", "intermediate", "hinge"),
        Exercise("plank", "Plank", ["core"], [], "bodyweight", "beginner", "carry"),
    ]
    
    # Filter by muscle groups
    filtered = []
    for exercise in exercise_db:
        exercise_dict = exercise.to_dict()
        
        # Check muscle match
        all_muscles = exercise.primary_muscles + exercise.secondary_muscles
        if any(mg in all_muscles for mg in muscle_groups):
            # Check equipment match
            if not equipment or exercise.equipment in equipment or "any" in equipment:
                # Check exclusions
                if not exclude_exercises or exercise.id not in exclude_exercises:
                    # Check movement patterns if specified
                    if not movement_patterns or exercise.movement_pattern in movement_patterns:
                        filtered.append(exercise_dict)
    
    # Sort by relevance (primary muscles match first)
    filtered.sort(key=lambda e: (
        -sum(1 for m in muscle_groups if m in e["primary_muscles"]),
        -sum(1 for m in muscle_groups if m in e["secondary_muscles"])
    ))
    
    return filtered

def tool_build_exercise_selection(
    exercises: List[Dict[str, Any]],
    target_sets: int = 12,
    target_duration: int = 45,
) -> Dict[str, Any]:
    """
    Build structured exercise selection with volume distribution.
    
    Assigns sets and reps to each exercise and calculates totals.
    """
    if not exercises:
        return {"error": "No exercises provided"}
    
    selected = []
    total_sets = 0
    remaining_sets = target_sets
    
    # Distribute sets across exercises
    for i, ex_dict in enumerate(exercises):
        if total_sets >= target_sets:
            break
            
        # More sets for compound movements
        is_compound = ex_dict.get("movement_pattern") in ["squat", "hinge", "push", "pull"]
        sets = 4 if is_compound and remaining_sets >= 4 else min(3, remaining_sets)
        
        # Adjust reps based on movement
        if ex_dict.get("movement_pattern") == "hinge":
            reps = "5-8"  # Lower reps for deadlifts
        elif ex_dict.get("movement_pattern") == "squat":
            reps = "6-10"
        else:
            reps = "8-12"
        
        exercise = Exercise(
            id=ex_dict["id"],
            name=ex_dict["name"],
            primary_muscles=ex_dict["primary_muscles"],
            secondary_muscles=ex_dict["secondary_muscles"],
            equipment=ex_dict["equipment"],
            difficulty=ex_dict["difficulty"],
            movement_pattern=ex_dict["movement_pattern"],
            sets=sets,
            reps=reps,
            rest_seconds=90 if is_compound else 60
        )
        
        selected.append(exercise)
        total_sets += sets
        remaining_sets -= sets
    
    # Calculate muscle coverage
    muscle_coverage = {}
    for ex in selected:
        for muscle in ex.primary_muscles:
            muscle_coverage[muscle] = muscle_coverage.get(muscle, 0) + 1
        for muscle in ex.secondary_muscles:
            muscle_coverage[muscle] = muscle_coverage.get(muscle, 0) + 0.5
    
    # Estimate duration (3 min per set average)
    estimated_duration = total_sets * 3
    
    return ExerciseSelection(
        exercises=selected,
        total_volume=total_sets,
        estimated_duration=estimated_duration,
        muscle_coverage=muscle_coverage,
        reasoning=f"Selected {len(selected)} exercises with {total_sets} total sets",
        alternatives=[]  # Would include alternatives in production
    ).__dict__

# Exercise Selection Agent with structured output
exercise_selector_agent = Agent(
    name="ExerciseSelector",
    model="gemini-2.5-flash",  # Use 2.5 Flash unless reasoning needed
    instruction="""
    You select exercises for workout programs. Always output valid JSON.
    
    Process:
    1. Call tool_search_exercises with the target muscle groups and available equipment
    2. Select 3-5 exercises that best cover the target muscles
    3. Call tool_build_exercise_selection to structure the selection
    4. Return the structured ExerciseSelection as JSON
    
    Selection criteria:
    - Prioritize compound movements for efficiency
    - Balance push and pull movements
    - Match exercises to user's experience level
    - Ensure all target muscles are adequately covered
    - Consider equipment availability
    
    Output schema:
    {
      "exercises": [
        {
          "id": "string",
          "name": "string", 
          "primary_muscles": ["string"],
          "secondary_muscles": ["string"],
          "equipment": "string",
          "difficulty": "beginner|intermediate|advanced",
          "movement_pattern": "push|pull|squat|hinge|carry|rotate",
          "sets": number,
          "reps": "string",
          "rest_seconds": number,
          "notes": "string|null"
        }
      ],
      "total_volume": number,
      "estimated_duration": number,
      "muscle_coverage": {"muscle": count},
      "reasoning": "string",
      "alternatives": []
    }
    """,
    tools=[
        FunctionTool(func=tool_search_exercises),
        FunctionTool(func=tool_build_exercise_selection),
    ],
    # Remove output_schema to avoid strict Pydantic BaseModel requirement in ADK
)
