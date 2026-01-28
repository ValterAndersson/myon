"""
Exercise Field Guide - Comprehensive field specifications for catalog enrichment.

This module provides:
1. Canonical value lists (valid equipment, muscles, categories, etc.)
2. Field specifications with types, validation rules, and examples
3. Golden example exercises showing ideal data structure
4. Naming taxonomy rules

All LLM prompts should reference these specifications to ensure consistent,
high-quality exercise data.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# =============================================================================
# PART 1: CANONICAL VALUE LISTS
# =============================================================================

# -----------------------------------------------------------------------------
# Equipment Types (singular form, lowercase)
# -----------------------------------------------------------------------------

EQUIPMENT_TYPES: List[str] = [
    # Free Weights
    "barbell",
    "dumbbell",
    "kettlebell",
    "ez-bar",
    "trap-bar",
    
    # Machines
    "machine",
    "cable",
    "smith-machine",
    
    # Bodyweight & Accessories
    "bodyweight",
    "pull-up-bar",
    "dip-station",
    "suspension-trainer",
    
    # Resistance
    "resistance-band",
    "medicine-ball",
    "stability-ball",
    
    # Cardio
    "treadmill",
    "rowing-machine",
    "bike",
    "elliptical",
]

# Equipment that is common and should be prioritized for family expansion
COMMON_EQUIPMENT: Set[str] = {
    "barbell",
    "dumbbell",
    "kettlebell",
    "cable",
    "machine",
    "bodyweight",
}

# Equipment that is specialty and should NOT be auto-suggested
SPECIALTY_EQUIPMENT: Set[str] = {
    "ez-bar",
    "trap-bar",
    "smith-machine",
    "suspension-trainer",
    "resistance-band",
}

# -----------------------------------------------------------------------------
# Categories
# -----------------------------------------------------------------------------

CATEGORIES: List[str] = [
    "compound",      # Multi-joint movements (squat, deadlift, bench)
    "isolation",     # Single-joint movements (curl, extension)
    "cardio",        # Cardiovascular exercises
    "stretching",    # Flexibility/mobility work
    "plyometric",    # Explosive/jumping movements
    "isometric",     # Static hold exercises
    "core",          # Dedicated core/ab work
]

# -----------------------------------------------------------------------------
# Difficulty Levels
# -----------------------------------------------------------------------------

DIFFICULTY_LEVELS: List[str] = [
    "beginner",      # Low coordination, low injury risk, machine/bodyweight
    "intermediate",  # Moderate coordination, free weights
    "advanced",      # High coordination, high load, complex movements
]

# -----------------------------------------------------------------------------
# Movement Types (for movement.type field)
# -----------------------------------------------------------------------------

MOVEMENT_TYPES: List[str] = [
    "push",          # Pressing away from body (bench press, overhead press)
    "pull",          # Pulling toward body (rows, pulldowns)
    "hinge",         # Hip hinge pattern (deadlift, RDL, good morning)
    "squat",         # Knee-dominant lower body (squat, leg press, lunges)
    "carry",         # Loaded carries (farmer's walk)
    "rotation",      # Rotational movements (Russian twist, woodchop)
    "flexion",       # Curling/crunching (bicep curl, leg curl)
    "extension",     # Extending (tricep extension, leg extension)
    "abduction",     # Moving away from midline (lateral raise)
    "adduction",     # Moving toward midline (cable crossover)
    "other",         # Miscellaneous
]

# -----------------------------------------------------------------------------
# Movement Splits (for movement.split field)
# -----------------------------------------------------------------------------

MOVEMENT_SPLITS: List[str] = [
    "upper",         # Upper body focused
    "lower",         # Lower body focused
    "full_body",     # Full body movement
    "core",          # Core/trunk focused
]

# -----------------------------------------------------------------------------
# Planes of Motion (for metadata.plane_of_motion field)
# -----------------------------------------------------------------------------

PLANES_OF_MOTION: List[str] = [
    "sagittal",      # Forward/backward (most exercises)
    "frontal",       # Side to side (lateral raises, side lunges)
    "transverse",    # Rotational (Russian twist, woodchop)
    "multi-plane",   # Complex movements spanning multiple planes
]

# -----------------------------------------------------------------------------
# Muscle Groups (for muscles.category field)
# Based on PRIMARY training intent, not all muscles activated
# -----------------------------------------------------------------------------

MUSCLE_GROUPS: List[str] = [
    "chest",
    "back",
    "shoulders",
    "arms",
    "legs",
    "core",
    "full_body",
]

# Mapping of exercises to muscle groups based on PRIMARY intent
MUSCLE_GROUP_EXAMPLES: Dict[str, List[str]] = {
    "chest": ["bench press", "push-up", "chest fly", "dip"],
    "back": ["row", "pull-up", "lat pulldown", "pullover"],
    "shoulders": ["overhead press", "lateral raise", "face pull"],
    "arms": ["bicep curl", "tricep extension", "hammer curl"],
    "legs": ["squat", "deadlift", "leg press", "lunge", "leg extension", "leg curl"],
    "core": ["plank", "crunch", "russian twist", "leg raise"],
    "full_body": ["clean", "snatch", "burpee", "thruster"],
}

# -----------------------------------------------------------------------------
# Individual Muscles (for muscles.primary and muscles.secondary)
# All lowercase, anatomically accurate names
# -----------------------------------------------------------------------------

PRIMARY_MUSCLES: List[str] = [
    # Chest
    "pectoralis major",
    "pectoralis minor",
    
    # Back
    "latissimus dorsi",
    "trapezius",
    "rhomboids",
    "erector spinae",
    "teres major",
    "teres minor",
    
    # Shoulders
    "anterior deltoid",
    "lateral deltoid",
    "posterior deltoid",
    "rotator cuff",
    
    # Arms
    "biceps",
    "triceps",
    "brachialis",
    "forearms",
    
    # Core
    "rectus abdominis",
    "obliques",
    "transverse abdominis",
    
    # Legs - Anterior
    "quadriceps",
    "hip flexors",
    
    # Legs - Posterior
    "hamstrings",
    "glutes",
    "gluteus maximus",
    "gluteus medius",
    
    # Legs - Other
    "calves",
    "adductors",
    "abductors",
]

# Simplified muscle names (acceptable alternatives)
MUSCLE_ALIASES: Dict[str, str] = {
    "lats": "latissimus dorsi",
    "traps": "trapezius",
    "delts": "deltoid",
    "front delt": "anterior deltoid",
    "side delt": "lateral deltoid",
    "rear delt": "posterior deltoid",
    "abs": "rectus abdominis",
    "quads": "quadriceps",
    "hams": "hamstrings",
    "glute": "glutes",
    "pecs": "pectoralis major",
}


# =============================================================================
# PART 2: FIELD SPECIFICATIONS
# =============================================================================

@dataclass
class FieldSpec:
    """Specification for an exercise field."""
    name: str
    field_path: str
    field_type: str
    required: bool
    enrichable: bool
    valid_values: Optional[List[str]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    description: str = ""
    good_example: Any = None
    bad_example: Any = None
    enrichment_prompt: str = ""


# -----------------------------------------------------------------------------
# All Field Specifications
# -----------------------------------------------------------------------------

FIELD_SPECS: Dict[str, FieldSpec] = {
    # -------------------------------------------------------------------------
    # Identity Fields (NOT enrichable - derived or source of truth)
    # -------------------------------------------------------------------------
    
    "name": FieldSpec(
        name="name",
        field_path="name",
        field_type="string",
        required=True,
        enrichable=False,
        description="""
        The display name of the exercise following the naming taxonomy:
        - Format: "Base Name (Equipment)" or "Modifier Base-Name (Equipment)"
        - Examples: "Deadlift (Barbell)", "Wide-grip Lat Pulldown (Cable)"
        - The equipment in parentheses should match the primary equipment field
        """,
        good_example="Romanian Deadlift (Dumbbell)",
        bad_example="dumbbell romanian deadlift",
    ),
    
    "name_slug": FieldSpec(
        name="name_slug",
        field_path="name_slug",
        field_type="string",
        required=True,
        enrichable=False,
        description="URL-safe slug derived from name. Auto-generated.",
        good_example="romanian_deadlift_dumbbell",
        bad_example=None,
    ),
    
    "family_slug": FieldSpec(
        name="family_slug",
        field_path="family_slug",
        field_type="string",
        required=True,
        enrichable=False,
        description="Groups exercises by movement pattern. Auto-derived from name.",
        good_example="deadlift",
        bad_example=None,
    ),
    
    # -------------------------------------------------------------------------
    # Core Fields (Enrichable)
    # -------------------------------------------------------------------------
    
    "equipment": FieldSpec(
        name="equipment",
        field_path="equipment",
        field_type="array[string]",
        required=True,
        enrichable=True,
        valid_values=EQUIPMENT_TYPES,
        description="""
        List of equipment needed. Usually a single item.
        Use singular form, lowercase, hyphenated for multi-word.
        """,
        good_example=["barbell"],
        bad_example=["Barbell", "Olympic Barbell", "BB"],
        enrichment_prompt="""What equipment is needed for this exercise?
Choose from: barbell, dumbbell, kettlebell, cable, machine, bodyweight
Respond with a JSON array, e.g., ["barbell"]""",
    ),
    
    "category": FieldSpec(
        name="category",
        field_path="category",
        field_type="string",
        required=True,
        enrichable=True,
        valid_values=CATEGORIES,
        description="""
        Exercise category based on movement pattern:
        - compound: Multi-joint (squat, deadlift, bench press)
        - isolation: Single-joint (curl, extension, raise)
        - cardio: Cardiovascular
        - stretching: Flexibility/mobility
        - plyometric: Explosive/jumping
        - isometric: Static holds
        - core: Dedicated core work
        """,
        good_example="compound",
        bad_example="strength",
        enrichment_prompt="""Is this exercise compound (multi-joint) or isolation (single-joint)?
Respond with exactly one of: compound, isolation, cardio, stretching, plyometric, isometric, core""",
    ),
    
    "instructions": FieldSpec(
        name="instructions",
        field_path="instructions",
        field_type="string",
        required=True,
        enrichable=True,
        min_length=100,
        max_length=1000,
        description="""
        Step-by-step instructions for performing the exercise.
        Use numbered steps (1. 2. 3. etc.)
        Include: starting position, movement execution, key form cues.
        Avoid: overly technical jargon, unnecessary detail.
        """,
        good_example="""1. Set up a barbell in a rack at mid-thigh height.
2. Grip the bar slightly wider than shoulder width.
3. Unrack and step back, feet shoulder-width apart.
4. Brace your core and keep your back straight.
5. Lower by pushing hips back and bending knees.
6. Descend until thighs are parallel to the ground.
7. Drive through your heels to stand back up.""",
        bad_example="Do the squat movement with good form.",
        enrichment_prompt="""Write clear instructions for this exercise.
Use numbered steps (1. 2. 3. etc.)
Include: starting position, movement, key safety cues.
Keep it practical - a gym-goer should be able to follow this.
4-7 steps is ideal. Respond with ONLY the numbered instructions.""",
    ),
    
    # -------------------------------------------------------------------------
    # Metadata Fields
    # -------------------------------------------------------------------------
    
    "metadata.level": FieldSpec(
        name="level",
        field_path="metadata.level",
        field_type="string",
        required=True,
        enrichable=True,
        valid_values=DIFFICULTY_LEVELS,
        description="""
        Difficulty level based on:
        - Coordination required
        - Injury risk
        - Prerequisite strength/mobility
        
        beginner: Machine-assisted, simple bodyweight, low coordination
        intermediate: Free weights, moderate coordination
        advanced: Complex movements, high load, high skill
        """,
        good_example="intermediate",
        bad_example="medium",
        enrichment_prompt="""What difficulty level is this exercise?
Consider: coordination required, injury risk, prerequisite strength.
Respond with exactly one of: beginner, intermediate, advanced""",
    ),
    
    "metadata.plane_of_motion": FieldSpec(
        name="plane_of_motion",
        field_path="metadata.plane_of_motion",
        field_type="string",
        required=False,
        enrichable=True,
        valid_values=PLANES_OF_MOTION,
        description="""
        Primary plane of motion:
        - sagittal: Forward/backward (most exercises)
        - frontal: Side to side (lateral raises)
        - transverse: Rotational (Russian twist)
        - multi-plane: Complex movements
        """,
        good_example="sagittal",
        bad_example="vertical",
        enrichment_prompt="""What is the primary plane of motion?
Respond with exactly one of: sagittal, frontal, transverse, multi-plane""",
    ),
    
    "metadata.unilateral": FieldSpec(
        name="unilateral",
        field_path="metadata.unilateral",
        field_type="boolean",
        required=False,
        enrichable=True,
        description="""
        Is this exercise performed one side at a time?
        true: Single-arm curl, lunge, single-leg deadlift
        false: Barbell squat, bench press, pull-up
        """,
        good_example=True,
        bad_example="yes",
        enrichment_prompt="""Is this exercise unilateral (one side at a time)?
Respond with exactly: true or false""",
    ),
    
    # -------------------------------------------------------------------------
    # Movement Fields
    # -------------------------------------------------------------------------
    
    "movement.type": FieldSpec(
        name="movement_type",
        field_path="movement.type",
        field_type="string",
        required=True,
        enrichable=True,
        valid_values=MOVEMENT_TYPES,
        description="""
        Primary movement pattern:
        - push: Pressing away (bench, overhead press)
        - pull: Pulling toward (rows, pulldowns)
        - hinge: Hip hinge (deadlift, RDL)
        - squat: Knee-dominant (squat, leg press, lunge)
        - flexion: Curling (bicep curl, leg curl)
        - extension: Extending (tricep extension, leg extension)
        - abduction: Away from midline (lateral raise)
        - adduction: Toward midline (cable crossover)
        """,
        good_example="hinge",
        bad_example="hip hinge",
        enrichment_prompt="""What is the primary movement pattern?
Respond with exactly one of: push, pull, hinge, squat, flexion, extension, abduction, adduction, carry, rotation, other""",
    ),
    
    "movement.split": FieldSpec(
        name="movement_split",
        field_path="movement.split",
        field_type="string",
        required=False,
        enrichable=True,
        valid_values=MOVEMENT_SPLITS,
        description="""
        Body region focus:
        - upper: Upper body focused
        - lower: Lower body focused
        - full_body: Full body movement
        - core: Core/trunk focused
        """,
        good_example="lower",
        bad_example="legs",
        enrichment_prompt="""What body region does this exercise focus on?
Respond with exactly one of: upper, lower, full_body, core""",
    ),
    
    # -------------------------------------------------------------------------
    # Muscle Fields
    # -------------------------------------------------------------------------
    
    "muscles.primary": FieldSpec(
        name="primary_muscles",
        field_path="muscles.primary",
        field_type="array[string]",
        required=True,
        enrichable=True,
        min_length=1,
        max_length=3,
        description="""
        The 1-3 muscles doing MOST of the work.
        Don't list every muscle activated - focus on the main movers.
        Use anatomically accurate names, lowercase.
        """,
        good_example=["quadriceps", "glutes"],
        bad_example=["Quads", "Glutes", "Hamstrings", "Core", "Back"],
        enrichment_prompt="""What are the PRIMARY muscles (1-3) worked by this exercise?
These are the main movers, not every muscle activated.
Use lowercase muscle names.
Respond with a JSON array, e.g., ["quadriceps", "glutes"]""",
    ),
    
    "muscles.secondary": FieldSpec(
        name="secondary_muscles",
        field_path="muscles.secondary",
        field_type="array[string]",
        required=False,
        enrichable=True,
        max_length=5,
        description="""
        Supporting muscles that are significantly activated.
        Not every stabilizer - just notable secondary involvement.
        """,
        good_example=["hamstrings", "erector spinae"],
        bad_example=["core", "stabilizers", "everything"],
        enrichment_prompt="""What are the SECONDARY muscles worked by this exercise?
These support the movement but aren't the primary focus.
Respond with a JSON array, e.g., ["hamstrings", "erector spinae"]""",
    ),
    
    "muscles.category": FieldSpec(
        name="muscle_category",
        field_path="muscles.category",
        field_type="array[string]",
        required=True,
        enrichable=True,
        valid_values=MUSCLE_GROUPS,
        description="""
        Muscle group(s) based on PRIMARY training intent.
        For compounds like Deadlift, use the primary target (legs) even though
        back is heavily worked. Usually a single value.

        Mapping examples:
        - Deadlift, Squat, Leg Press → ["legs"]
        - Bench Press, Push-up → ["chest"]
        - Row, Pulldown → ["back"]
        - Overhead Press → ["shoulders"]
        - Bicep Curl, Tricep Extension → ["arms"]
        - Plank, Crunch → ["core"]
        """,
        good_example=["legs"],
        bad_example=["back", "legs", "core"],
        enrichment_prompt="""What muscle GROUP does this exercise primarily target?
Choose based on the PRIMARY training intent.
Deadlift = legs (even though back works hard).
Respond with a JSON array, usually single value: ["legs"] or ["chest"]""",
    ),

    "muscles.contribution": FieldSpec(
        name="muscle_contribution",
        field_path="muscles.contribution",
        field_type="map[string, number]",
        required=False,
        enrichable=True,
        description="""
        Percentage contribution of each muscle to the movement.
        Keys are muscle names (lowercase), values are decimals 0.0-1.0.
        All values should sum to approximately 1.0.
        Include all primary and secondary muscles.

        Example for lateral raise:
        {
            "medial deltoid": 0.75,
            "anterior deltoid": 0.15,
            "trapezius": 0.10
        }
        """,
        good_example={"quadriceps": 0.50, "glutes": 0.35, "hamstrings": 0.15},
        bad_example={"quads": 50, "glutes": 35},  # Wrong: use full names, decimals not %
        enrichment_prompt="""What is the percentage contribution of each muscle?
Use decimal values (0.0-1.0) that sum to approximately 1.0.
Include primary and secondary muscles.
Respond with a JSON object: {"muscle name": 0.XX, ...}""",
    ),

    # -------------------------------------------------------------------------
    # Enrichment Array Fields
    # -------------------------------------------------------------------------

    "stimulus_tags": FieldSpec(
        name="stimulus_tags",
        field_path="stimulus_tags",
        field_type="array[string]",
        required=False,
        enrichable=True,
        max_length=8,
        description="""
        Tags describing the training stimulus and characteristics.
        Use title case, focus on training benefits.

        Common tags:
        - Hypertrophy, Strength, Power, Endurance
        - Muscle Isolation, Compound Movement
        - Beginner Friendly, Advanced
        - Time Under Tension, Controlled Movement
        - Joint Stability, Core Engagement
        """,
        good_example=["Hypertrophy", "Muscle Isolation", "Beginner Friendly"],
        bad_example=["good exercise", "arms", "gym"],
        enrichment_prompt="""What training stimulus tags apply to this exercise?
Use title case. Focus on benefits like Hypertrophy, Strength, Muscle Isolation, etc.
Respond with a JSON array of 4-6 tags.""",
    ),

    "programming_use_cases": FieldSpec(
        name="programming_use_cases",
        field_path="programming_use_cases",
        field_type="array[string]",
        required=False,
        enrichable=True,
        max_length=5,
        description="""
        Specific scenarios where this exercise is valuable in program design.
        Each item is a complete sentence describing a use case.

        Examples:
        - "Excellent for beginners to safely learn the movement pattern"
        - "Ideal as an accessory exercise in hypertrophy-focused programs"
        - "Effective as a finisher at the end of a workout"
        """,
        good_example=[
            "Excellent for beginners to safely learn proper squat form.",
            "Ideal as a primary compound movement in leg-focused programs.",
        ],
        bad_example=["good for legs", "use it"],
        enrichment_prompt="""What are the programming use cases for this exercise?
Describe 3-5 specific scenarios where this exercise adds value.
Each should be a complete sentence.
Respond with a JSON array of strings.""",
    ),

    "suitability_notes": FieldSpec(
        name="suitability_notes",
        field_path="suitability_notes",
        field_type="array[string]",
        required=False,
        enrichable=True,
        max_length=5,
        description="""
        Notes about who this exercise is suitable for and any considerations.
        Include positive suitability and any cautions.

        Examples:
        - "Highly effective for isolating the target muscle"
        - "The machine's stability makes it safe for beginners"
        - "Requires good shoulder mobility"
        """,
        good_example=[
            "Highly effective for isolating the medial deltoid.",
            "Safe and easy for beginners to learn proper form.",
        ],
        bad_example=["good", "safe"],
        enrichment_prompt="""Who is this exercise suitable for? Any considerations?
Include positive notes and any cautions or prerequisites.
Respond with a JSON array of 2-4 complete sentences.""",
    ),
}


def get_field_spec(field_path: str) -> Optional[FieldSpec]:
    """Get the specification for a field by path."""
    return FIELD_SPECS.get(field_path)


def get_enrichable_fields() -> List[FieldSpec]:
    """Get all fields that can be enriched by LLM."""
    return [spec for spec in FIELD_SPECS.values() if spec.enrichable]


def get_required_fields() -> List[FieldSpec]:
    """Get all required fields."""
    return [spec for spec in FIELD_SPECS.values() if spec.required]


# =============================================================================
# PART 3: GOLDEN EXAMPLES
# =============================================================================

# These are "gold standard" examples showing ideal exercise data.
# Use these as reference when enriching exercises.

GOLDEN_EXAMPLES: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Example 1: Compound Lower Body (Barbell)
    # -------------------------------------------------------------------------
    "back_squat_barbell": {
        "name": "Back Squat (Barbell)",
        "name_slug": "back_squat_barbell",
        "family_slug": "squat",
        "equipment": ["barbell"],
        "category": "compound",
        "metadata": {
            "level": "intermediate",
            "plane_of_motion": "sagittal",
            "unilateral": False,
        },
        "movement": {
            "type": "squat",
            "split": "lower",
        },
        "muscles": {
            "primary": ["quadriceps", "glutes"],
            "secondary": ["hamstrings", "erector spinae", "rectus abdominis"],
            "category": ["legs"],
            "contribution": {
                "quadriceps": 0.45,
                "glutes": 0.30,
                "hamstrings": 0.15,
                "erector spinae": 0.07,
                "rectus abdominis": 0.03,
            },
        },
        "execution_notes": [
            "Keep your knees tracking over your toes throughout the movement",
            "Maintain a neutral spine - don't round your lower back",
            "Breathe in at the top, hold during descent, exhale as you drive up",
        ],
        "common_mistakes": [
            "Knees caving inward during the lift",
            "Rounding the lower back at the bottom",
            "Rising onto toes instead of driving through heels",
            "Looking up or down instead of forward",
        ],
        "suitability_notes": [
            "Requires good hip and ankle mobility",
            "Start with lighter weight to master form",
        ],
        "programming_use_cases": [
            "Primary compound movement for leg-focused strength programs.",
            "Essential exercise for building lower body power and muscle mass.",
            "Foundation movement for athletic performance training.",
        ],
        "stimulus_tags": [
            "Compound Movement",
            "Strength",
            "Hypertrophy",
            "Core Engagement",
            "Athletic Performance",
        ],
    },
    
    # -------------------------------------------------------------------------
    # Example 2: Compound Upper Body (Dumbbell)
    # -------------------------------------------------------------------------
    "bench_press_dumbbell": {
        "name": "Bench Press (Dumbbell)",
        "name_slug": "bench_press_dumbbell",
        "family_slug": "bench_press",
        "equipment": ["dumbbell"],
        "category": "compound",
        "metadata": {
            "level": "intermediate",
            "plane_of_motion": "sagittal",
            "unilateral": False,
        },
        "movement": {
            "type": "push",
            "split": "upper",
        },
        "muscles": {
            "primary": ["pectoralis major", "triceps"],
            "secondary": ["anterior deltoid"],
            "category": ["chest"],
            "contribution": {
                "pectoralis major": 0.55,
                "triceps": 0.30,
                "anterior deltoid": 0.15,
            },
        },
        "execution_notes": [
            "Don't bounce the weights off your chest",
            "Keep your wrists straight, not bent back",
            "Control the weight - don't let gravity do the work on the way down",
        ],
        "common_mistakes": [
            "Flaring elbows out to 90 degrees (stresses shoulders)",
            "Arching back excessively to lift more weight",
            "Not using full range of motion",
        ],
        "suitability_notes": [
            "Good alternative to barbell for those with shoulder issues",
            "Requires more stabilization than barbell version",
        ],
        "programming_use_cases": [
            "Primary pressing movement for chest hypertrophy programs.",
            "Alternative to barbell for lifters with shoulder limitations.",
            "Accessory exercise to improve pressing strength balance.",
        ],
        "stimulus_tags": [
            "Compound Movement",
            "Hypertrophy",
            "Strength",
            "Stabilization",
        ],
    },

    # -------------------------------------------------------------------------
    # Example 3: Isolation (Cable)
    # -------------------------------------------------------------------------
    "tricep_pushdown_cable": {
        "name": "Tricep Pushdown (Cable)",
        "name_slug": "tricep_pushdown_cable",
        "family_slug": "tricep_pushdown",
        "equipment": ["cable"],
        "category": "isolation",
        "metadata": {
            "level": "beginner",
            "plane_of_motion": "sagittal",
            "unilateral": False,
        },
        "movement": {
            "type": "extension",
            "split": "upper",
        },
        "muscles": {
            "primary": ["triceps"],
            "secondary": [],
            "category": ["arms"],
            "contribution": {
                "triceps": 1.0,
            },
        },
        "execution_notes": [
            "Keep your upper arms stationary - only your forearms should move",
            "Don't lean forward to use body weight",
            "Focus on squeezing the triceps at full extension",
        ],
        "common_mistakes": [
            "Letting elbows drift forward or back",
            "Using momentum by swinging the body",
            "Gripping too tight (causes forearm fatigue)",
        ],
        "suitability_notes": [
            "Great exercise for beginners learning tricep isolation",
            "Low injury risk when performed correctly",
        ],
        "programming_use_cases": [
            "Accessory exercise to build tricep strength for pressing movements.",
            "Finisher at the end of an arm or push workout.",
            "Beginner exercise to learn proper tricep activation.",
        ],
        "stimulus_tags": [
            "Muscle Isolation",
            "Beginner Friendly",
            "Controlled Movement",
            "Time Under Tension",
        ],
    },
    
    # -------------------------------------------------------------------------
    # Example 4: Bodyweight
    # -------------------------------------------------------------------------
    "pull_up_bodyweight": {
        "name": "Pull-up (Bodyweight)",
        "name_slug": "pull_up_bodyweight",
        "family_slug": "pull_up",
        "equipment": ["bodyweight", "pull-up-bar"],
        "category": "compound",
        "metadata": {
            "level": "intermediate",
            "plane_of_motion": "sagittal",
            "unilateral": False,
        },
        "movement": {
            "type": "pull",
            "split": "upper",
        },
        "muscles": {
            "primary": ["latissimus dorsi", "biceps"],
            "secondary": ["rhomboids", "posterior deltoid", "forearms"],
            "category": ["back"],
            "contribution": {
                "latissimus dorsi": 0.45,
                "biceps": 0.25,
                "rhomboids": 0.12,
                "posterior deltoid": 0.10,
                "forearms": 0.08,
            },
        },
        "execution_notes": [
            "Initiate the pull by depressing your shoulder blades",
            "Think about pulling your elbows to your back pockets",
            "Keep your core engaged to prevent swinging",
        ],
        "common_mistakes": [
            "Kipping or using momentum (unless doing CrossFit-style)",
            "Not going to full arm extension at the bottom",
            "Shrugging shoulders up instead of keeping them depressed",
        ],
        "suitability_notes": [
            "Requires baseline upper body strength",
            "Use assisted machine or bands if unable to complete reps",
        ],
        "programming_use_cases": [
            "Primary vertical pulling movement for back development.",
            "Bodyweight strength benchmark and progression exercise.",
            "Foundation for advanced calisthenics training.",
        ],
        "stimulus_tags": [
            "Compound Movement",
            "Bodyweight",
            "Strength",
            "Back Development",
            "Core Engagement",
        ],
    },
    
    # -------------------------------------------------------------------------
    # Example 5: Hinge Pattern (Barbell)
    # -------------------------------------------------------------------------
    "romanian_deadlift_barbell": {
        "name": "Romanian Deadlift (Barbell)",
        "name_slug": "romanian_deadlift_barbell",
        "family_slug": "deadlift",
        "equipment": ["barbell"],
        "category": "compound",
        "metadata": {
            "level": "intermediate",
            "plane_of_motion": "sagittal",
            "unilateral": False,
        },
        "movement": {
            "type": "hinge",
            "split": "lower",
        },
        "muscles": {
            "primary": ["hamstrings", "glutes"],
            "secondary": ["erector spinae", "latissimus dorsi"],
            "category": ["legs"],
            "contribution": {
                "hamstrings": 0.45,
                "glutes": 0.30,
                "erector spinae": 0.15,
                "latissimus dorsi": 0.10,
            },
        },
        "execution_notes": [
            "This is a hip hinge, not a squat - knees stay slightly bent",
            "The bar should stay close to your body throughout",
            "Feel the stretch in your hamstrings as you lower",
        ],
        "common_mistakes": [
            "Rounding the lower back (most common and dangerous)",
            "Bending the knees too much (turning it into a squat)",
            "Looking up instead of keeping neutral neck",
        ],
        "suitability_notes": [
            "Excellent for hamstring development and hip hinge learning",
            "Requires good hamstring flexibility",
        ],
        "programming_use_cases": [
            "Primary hip hinge movement for posterior chain development.",
            "Accessory exercise to complement conventional deadlifts.",
            "Hamstring strengthening for injury prevention in athletes.",
        ],
        "stimulus_tags": [
            "Compound Movement",
            "Hinge Pattern",
            "Hypertrophy",
            "Hamstring Focus",
            "Posterior Chain",
        ],
    },
}


def get_golden_example(exercise_key: str) -> Optional[Dict[str, Any]]:
    """Get a golden example exercise by key."""
    return GOLDEN_EXAMPLES.get(exercise_key)


def get_all_golden_examples() -> Dict[str, Dict[str, Any]]:
    """Get all golden example exercises."""
    return GOLDEN_EXAMPLES


# =============================================================================
# PART 4: NAMING TAXONOMY
# =============================================================================

NAMING_TAXONOMY = """
# Exercise Naming Taxonomy

## Format
Exercise names follow a consistent pattern:

    [Modifier] Base-Name (Equipment)

## Components

### Base Name
The core movement pattern. Examples:
- Deadlift, Squat, Bench Press, Row, Curl, Extension

### Equipment (Required in Parentheses)
The primary equipment used. Always in parentheses at the end:
- (Barbell), (Dumbbell), (Kettlebell), (Cable), (Machine), (Bodyweight)

### Modifier (Optional)
Describes the variation. Placed before the base name:
- Grip: Wide-grip, Narrow-grip, Neutral-grip
- Stance: Sumo, Close-stance, Staggered-stance
- Position: Incline, Decline, Seated, Standing
- Type: Romanian, Bulgarian, Reverse

## Examples

### Standard Equipment Variants
- Deadlift (Barbell)
- Deadlift (Dumbbell)
- Deadlift (Kettlebell)

### With Modifiers
- Romanian Deadlift (Barbell)
- Sumo Deadlift (Barbell)
- Single-leg Deadlift (Dumbbell)

### Grip Variations
- Lat Pulldown (Cable)
- Wide-grip Lat Pulldown (Cable)
- Neutral-grip Lat Pulldown (Cable)
- Reverse-grip Lat Pulldown (Cable)

### Position Variations
- Bench Press (Barbell)
- Incline Bench Press (Barbell)
- Decline Bench Press (Barbell)

## Common Naming Patterns by Family

### Deadlift Family
- Deadlift (Barbell) - conventional
- Romanian Deadlift (Barbell) - RDL variant
- Sumo Deadlift (Barbell) - wide stance
- Stiff-leg Deadlift (Barbell) - straight legs
- Single-leg Deadlift (Dumbbell) - unilateral

### Squat Family
- Back Squat (Barbell) - bar on upper back
- Front Squat (Barbell) - bar on front shoulders
- Goblet Squat (Dumbbell) - dumbbell at chest
- Split Squat (Dumbbell) - lunge position
- Bulgarian Split Squat (Dumbbell) - rear foot elevated

### Press Family
- Bench Press (Barbell)
- Incline Bench Press (Barbell)
- Overhead Press (Barbell) - standing shoulder press
- Shoulder Press (Dumbbell) - seated
- Push Press (Barbell) - with leg drive

### Row Family
- Bent-over Row (Barbell)
- Pendlay Row (Barbell) - from floor
- Single-arm Row (Dumbbell) - one arm at a time
- Seated Row (Cable)
- T-bar Row (Machine)

## Naming Rules

1. **Equipment is always last in parentheses**
   ✓ Deadlift (Barbell)
   ✗ Barbell Deadlift

2. **Modifiers come before the base name**
   ✓ Romanian Deadlift (Barbell)
   ✗ Deadlift Romanian (Barbell)

3. **Use hyphens for multi-word modifiers**
   ✓ Wide-grip Lat Pulldown (Cable)
   ✗ Wide Grip Lat Pulldown (Cable)

4. **Capitalize each word (Title Case)**
   ✓ Incline Bench Press (Barbell)
   ✗ incline bench press (barbell)

5. **Use standard equipment names**
   ✓ (Barbell), (Dumbbell), (Cable), (Machine)
   ✗ (BB), (DB), (Cables), (Smith Machine)

6. **Be specific but not redundant**
   ✓ Bicep Curl (Dumbbell)
   ✗ Dumbbell Bicep Curl (Dumbbell)
"""


def get_naming_taxonomy() -> str:
    """Get the naming taxonomy documentation."""
    return NAMING_TAXONOMY


def validate_exercise_name(name: str) -> Dict[str, Any]:
    """
    Validate an exercise name against the naming taxonomy.
    
    Returns:
        Dict with 'valid', 'issues', and 'suggested_fix' keys
    """
    issues = []
    suggested_fix = name
    
    # Check for equipment in parentheses
    if "(" not in name or ")" not in name:
        issues.append("Missing equipment in parentheses")
        # Try to suggest a fix
        for equipment in EQUIPMENT_TYPES:
            if equipment.lower() in name.lower():
                suggested_fix = name.replace(equipment, "").strip()
                suggested_fix += f" ({equipment.title()})"
                break
    else:
        # Check equipment is at the end
        if not name.endswith(")"):
            issues.append("Equipment should be at the end")
        
        # Check equipment is valid
        import re
        equipment_match = re.search(r'\(([^)]+)\)$', name)
        if equipment_match:
            equipment = equipment_match.group(1).lower()
            if equipment not in EQUIPMENT_TYPES:
                issues.append(f"Unknown equipment: {equipment}")
    
    # Check capitalization (should be Title Case)
    words = name.split()
    for word in words:
        if word and word[0].islower() and word not in ["(", ")"]:
            issues.append("Should use Title Case capitalization")
            break
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "suggested_fix": suggested_fix if issues else None,
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Canonical Values
    "EQUIPMENT_TYPES",
    "COMMON_EQUIPMENT",
    "SPECIALTY_EQUIPMENT",
    "CATEGORIES",
    "DIFFICULTY_LEVELS",
    "MOVEMENT_TYPES",
    "MOVEMENT_SPLITS",
    "PLANES_OF_MOTION",
    "MUSCLE_GROUPS",
    "MUSCLE_GROUP_EXAMPLES",
    "PRIMARY_MUSCLES",
    "MUSCLE_ALIASES",
    
    # Field Specifications
    "FieldSpec",
    "FIELD_SPECS",
    "get_field_spec",
    "get_enrichable_fields",
    "get_required_fields",
    
    # Golden Examples
    "GOLDEN_EXAMPLES",
    "get_golden_example",
    "get_all_golden_examples",
    
    # Naming Taxonomy
    "NAMING_TAXONOMY",
    "get_naming_taxonomy",
    "validate_exercise_name",
]
