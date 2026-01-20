"""
Taxonomy - Equipment naming rules, validation, and detection.

Architecture:
- EQUIPMENT = physical apparatus (barbell, cable, machine) → suffix in name
- MODIFIERS = grip, stance, position → part of base name, NOT equipment
- ATTACHMENTS = cable attachments (v-bar, rope) → base name or metadata

Key rules:
- When family has >1 primary equipment types, exercises MUST have equipment in name
- Equipment suffix uses canonical display name: (Barbell), (Dumbbell), etc.
- Detection uses priority ordering (specific → generic)
- Grip/stance/position are NOT equipment and don't go in suffix
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from app.family.models import ExerciseSummary, FamilyRegistry


# =============================================================================
# CANONICAL EQUIPMENT TAXONOMY
# =============================================================================

EQUIPMENT_DISPLAY_MAP: Dict[str, str] = {
    # =========================================================================
    # FREE WEIGHTS - Barbells
    # =========================================================================
    "barbell": "Barbell",
    "ez_bar": "EZ Bar",
    "hex_bar": "Hex Bar",
    "trap_bar": "Trap Bar",
    "safety_squat_bar": "Safety Squat Bar",
    "swiss_bar": "Swiss Bar",
    "axle_bar": "Axle Bar",
    "cambered_bar": "Cambered Bar",
    "buffalo_bar": "Buffalo Bar",
    "log": "Log",
    
    # =========================================================================
    # FREE WEIGHTS - Other
    # =========================================================================
    "dumbbell": "Dumbbell",
    "kettlebell": "Kettlebell",
    "plate": "Plate",
    "medicine_ball": "Medicine Ball",
    "slam_ball": "Slam Ball",
    "sandbag": "Sandbag",
    "clubbell": "Clubbell",
    "mace": "Mace",
    
    # =========================================================================
    # MACHINES - Cable
    # =========================================================================
    "cable": "Cable",
    "cable_crossover": "Cable Crossover",
    "functional_trainer": "Functional Trainer",
    
    # =========================================================================
    # MACHINES - Plate Loaded
    # =========================================================================
    "machine": "Machine",
    "smith_machine": "Smith Machine",
    "hack_squat": "Hack Squat",
    "leg_press": "Leg Press",
    "pendulum_squat": "Pendulum Squat",
    "belt_squat": "Belt Squat",
    "v_squat": "V-Squat",
    
    # =========================================================================
    # MACHINES - Selectorized / Pin-Loaded
    # =========================================================================
    "lat_pulldown": "Lat Pulldown",
    "seated_row": "Seated Row",
    "chest_press": "Chest Press",
    "shoulder_press_machine": "Shoulder Press Machine",
    "pec_deck": "Pec Deck",
    "rear_delt_machine": "Rear Delt Machine",
    "leg_curl": "Leg Curl",
    "leg_extension": "Leg Extension",
    "hip_abductor": "Hip Abductor",
    "hip_adductor": "Hip Adductor",
    "glute_machine": "Glute Machine",
    "calf_machine": "Calf Machine",
    "ab_machine": "Ab Machine",
    "preacher_curl": "Preacher Curl",
    "tricep_machine": "Tricep Machine",
    
    # =========================================================================
    # BODYWEIGHT & ASSISTANCE
    # =========================================================================
    "bodyweight": "Bodyweight",
    "assisted": "Assisted",
    "weighted": "Weighted",
    "pull_up_bar": "Pull-Up Bar",
    "dip_station": "Dip Station",
    "rings": "Rings",
    "parallettes": "Parallettes",
    "roman_chair": "Roman Chair",
    "glute_ham_raise": "GHR",
    "reverse_hyper": "Reverse Hyper",
    
    # =========================================================================
    # BANDS & SUSPENSION
    # =========================================================================
    "band": "Band",
    "resistance_band": "Resistance Band",
    "mini_band": "Mini Band",
    "trx": "TRX",
    "suspension_trainer": "Suspension Trainer",
    
    # =========================================================================
    # SPECIALTY & CONDITIONING
    # =========================================================================
    "landmine": "Landmine",
    "chains": "Chains",
    "sled": "Sled",
    "prowler": "Prowler",
    "battle_rope": "Battle Rope",
    "ab_wheel": "Ab Wheel",
    "foam_roller": "Foam Roller",
    "lacrosse_ball": "Lacrosse Ball",
    "slider": "Slider",
    "stability_ball": "Stability Ball",
    "bosu": "BOSU",
    
    # =========================================================================
    # CARDIO (if needed)
    # =========================================================================
    "rower": "Rower",
    "ski_erg": "Ski Erg",
    "assault_bike": "Assault Bike",
    "treadmill": "Treadmill",
    "stairmaster": "Stairmaster",
}

# Reverse map for parsing names
EQUIPMENT_REVERSE_MAP: Dict[str, str] = {
    v.lower(): k for k, v in EQUIPMENT_DISPLAY_MAP.items()
}


# =============================================================================
# CABLE ATTACHMENTS (separate from primary equipment)
# =============================================================================

ATTACHMENT_DISPLAY_MAP: Dict[str, str] = {
    "v_bar": "V-Bar",
    "straight_bar": "Straight Bar",
    "lat_bar": "Lat Bar",
    "ez_handle": "EZ Handle",
    "rope": "Rope",
    "d_handle": "D-Handle",
    "single_handle": "Single Handle",
    "ankle_strap": "Ankle Strap",
    "stirrup": "Stirrup",
    "mag_grip": "MAG Grip",
    "close_grip": "Close Grip",
    "wide_grip": "Wide Grip",
}


# =============================================================================
# MODIFIERS - These are NOT equipment (go in base name, not suffix)
# =============================================================================

# Grip types - affects hand position
GRIP_MODIFIERS: Set[str] = {
    "wide_grip", "narrow_grip", "close_grip",
    "neutral_grip", "supinated", "pronated", "mixed_grip",
    "false_grip", "thumbless", "hook_grip",
    "overhand", "underhand", "alternating",
}

# Stance types - affects leg/foot position
STANCE_MODIFIERS: Set[str] = {
    "sumo", "conventional", "staggered", "split_stance",
    "single_leg", "unilateral", "bilateral",
    "narrow_stance", "wide_stance",
}

# Body position types
POSITION_MODIFIERS: Set[str] = {
    "incline", "decline", "flat",
    "seated", "standing", "lying", "prone", "supine",
    "kneeling", "half_kneeling",
    "bent_over", "upright",
}

# Range of motion / tempo modifiers
ROM_MODIFIERS: Set[str] = {
    "pause", "tempo", "eccentric", "isometric",
    "partial", "full_rom", "deficit", "block",
    "pin", "bottom_up",
}


# =============================================================================
# NAME → EQUIPMENT DETECTION (priority ordered)
# =============================================================================

# Order matters! More specific terms first to avoid false matches
# e.g., "hex bar" must be checked before "bar" would match "barbell"
NAME_EQUIPMENT_PRIORITY: List[Tuple[str, str]] = [
    # Specialty bars (most specific first)
    ("safety squat bar", "safety_squat_bar"),
    ("ssb", "safety_squat_bar"),
    ("swiss bar", "swiss_bar"),
    ("football bar", "swiss_bar"),
    ("cambered bar", "cambered_bar"),
    ("buffalo bar", "buffalo_bar"),
    ("axle bar", "axle_bar"),
    ("axle", "axle_bar"),
    ("hex bar", "hex_bar"),
    ("trap bar", "trap_bar"),
    ("ez bar", "ez_bar"),
    ("ez-bar", "ez_bar"),
    ("curl bar", "ez_bar"),
    ("log", "log"),
    
    # Machines (check before generic terms)
    ("smith machine", "smith_machine"),
    ("hack squat", "hack_squat"),
    ("leg press", "leg_press"),
    ("pendulum squat", "pendulum_squat"),
    ("belt squat", "belt_squat"),
    ("v-squat", "v_squat"),
    ("lat pulldown", "lat_pulldown"),
    ("seated row", "seated_row"),
    ("cable row", "cable"),
    ("chest press", "chest_press"),
    ("shoulder press machine", "shoulder_press_machine"),
    ("pec deck", "pec_deck"),
    ("pec fly", "pec_deck"),
    ("rear delt", "rear_delt_machine"),
    ("leg curl", "leg_curl"),
    ("leg extension", "leg_extension"),
    ("hip abductor", "hip_abductor"),
    ("hip adductor", "hip_adductor"),
    ("glute machine", "glute_machine"),
    ("calf raise machine", "calf_machine"),
    ("calf machine", "calf_machine"),
    ("preacher curl", "preacher_curl"),
    ("roman chair", "roman_chair"),
    ("ghr", "glute_ham_raise"),
    ("glute ham raise", "glute_ham_raise"),
    ("reverse hyper", "reverse_hyper"),
    
    # Bodyweight variants
    ("pull-up bar", "pull_up_bar"),
    ("pullup bar", "pull_up_bar"),
    ("dip station", "dip_station"),
    ("parallel bars", "dip_station"),
    ("rings", "rings"),
    ("parallettes", "parallettes"),
    
    # Cable and machines (check before generic)
    ("cable crossover", "cable_crossover"),
    ("functional trainer", "functional_trainer"),
    ("cable", "cable"),
    ("machine", "machine"),
    
    # Specialty equipment
    ("landmine", "landmine"),
    ("sled", "sled"),
    ("prowler", "prowler"),
    ("battle rope", "battle_rope"),
    ("ab wheel", "ab_wheel"),
    ("stability ball", "stability_ball"),
    ("swiss ball", "stability_ball"),
    ("bosu", "bosu"),
    ("trx", "trx"),
    ("suspension", "suspension_trainer"),
    
    # Bands
    ("resistance band", "resistance_band"),
    ("mini band", "mini_band"),
    ("band", "band"),
    
    # Free weights (most generic last)
    ("barbell", "barbell"),
    ("dumbbell", "dumbbell"),
    ("kettlebell", "kettlebell"),
    ("medicine ball", "medicine_ball"),
    ("slam ball", "slam_ball"),
    ("plate", "plate"),
    ("sandbag", "sandbag"),
    
    # Bodyweight (last - often implicit)
    ("bodyweight", "bodyweight"),
    ("bw", "bodyweight"),
    ("assisted", "assisted"),
    ("weighted", "weighted"),
]


def detect_equipment_from_name(name: str) -> Optional[str]:
    """
    Detect equipment implied by exercise name using priority ordering.
    
    More specific terms are checked first to avoid false matches.
    e.g., "Hex Bar Deadlift" matches "hex_bar", not "barbell".
    
    Args:
        name: Exercise name (e.g., "Hex Bar Deadlift")
        
    Returns:
        Equipment key if detected, None otherwise
    """
    name_lower = name.lower()
    
    for keyword, equipment in NAME_EQUIPMENT_PRIORITY:
        if keyword in name_lower:
            return equipment
    
    return None


# =============================================================================
# DERIVATION FUNCTIONS
# =============================================================================

def derive_equipment_suffix(equipment: str) -> str:
    """
    Get the canonical display suffix for equipment.
    
    Args:
        equipment: Equipment key (e.g., "barbell", "smith_machine")
        
    Returns:
        Display name for name suffix (e.g., "Barbell", "Smith Machine")
    """
    # Normalize the input
    normalized = equipment.lower().replace(" ", "_").replace("-", "_")
    return EQUIPMENT_DISPLAY_MAP.get(normalized, equipment.title())


def derive_canonical_name(base_name: str, equipment: Optional[str]) -> str:
    """
    Derive canonical exercise name with equipment suffix.
    
    Args:
        base_name: Base exercise name (e.g., "Deadlift")
        equipment: Primary equipment (e.g., "barbell")
        
    Returns:
        Canonical name (e.g., "Deadlift (Barbell)")
    """
    # Strip any existing equipment suffix
    clean_base = re.sub(r'\s*\([^)]+\)\s*$', '', base_name).strip()
    
    if not equipment:
        return clean_base
    
    suffix = derive_equipment_suffix(equipment)
    return f"{clean_base} ({suffix})"


def derive_movement_family(name: str) -> str:
    """
    Derive family slug from exercise name by stripping equipment.
    
    Extracts just the base movement for family grouping.
    
    Rules:
    - Remove equipment suffix in parentheses: "Deadlift (Barbell)" → "deadlift"
    - Remove equipment keywords: "Dumbbell Curl" → "curl"
    - Convert to underscore slug format: "Bench Press" → "bench_press"
    
    Args:
        name: Exercise name (e.g., "Deadlift (Barbell)", "Dumbbell Bench Press")
        
    Returns:
        Family slug using underscores (e.g., "deadlift", "bench_press")
    """
    # Step 1: Remove parenthetical suffix (equipment qualifier)
    base = re.sub(r'\s*\([^)]+\)\s*$', '', name).strip()
    
    # Step 2: Remove leading equipment keywords
    base_lower = base.lower()
    equipment_prefixes = [
        "barbell", "dumbbell", "kettlebell", "cable", "machine", 
        "band", "bodyweight", "weighted", "smith machine",
        "ez bar", "hex bar", "trap bar", "landmine",
    ]
    for prefix in equipment_prefixes:
        if base_lower.startswith(prefix + " "):
            base = base[len(prefix):].strip()
            break
    
    # Step 3: Convert to underscore slug
    slug = unicodedata.normalize('NFKD', base)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    slug = slug.lower()
    slug = re.sub(r'[\s-]+', '_', slug)  # Use underscores
    slug = re.sub(r'[^a-z0-9_]', '', slug)
    slug = re.sub(r'_+', '_', slug)
    slug = slug.strip('_')
    
    return slug


def derive_name_slug(name: str) -> str:
    """
    Derive deterministic slug from exercise name.
    
    Rules:
    - Lowercase
    - Replace spaces and underscores with hyphens
    - Remove parentheses, keep content
    - Remove other special characters
    - Collapse multiple hyphens
    
    Args:
        name: Exercise name (e.g., "Deadlift (Barbell)")
        
    Returns:
        Slug (e.g., "deadlift-barbell")
    """
    # Normalize unicode
    slug = unicodedata.normalize('NFKD', name)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    
    # Remove parentheses but keep content
    slug = re.sub(r'[()]', ' ', slug)
    
    # Lowercase
    slug = slug.lower()
    
    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    
    # Remove non-alphanumeric except hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    
    return slug


def compute_primary_equipment_set(exercises: List[ExerciseSummary]) -> Set[str]:
    """
    Compute set of primary equipment types from exercises.
    
    Only uses equipment[0] for multi-equipment family determination.
    
    Args:
        exercises: List of exercise summaries
        
    Returns:
        Set of primary equipment types
    """
    return {
        ex.primary_equipment
        for ex in exercises
        if ex.primary_equipment
    }


def normalize_equipment_value(equipment: str) -> str:
    """
    Normalize equipment value to canonical key.
    
    Args:
        equipment: Raw equipment value (e.g., "Trap Bar", "trap bar", "trap_bar")
        
    Returns:
        Canonical key (e.g., "trap_bar")
    """
    normalized = equipment.lower().strip().replace(" ", "_").replace("-", "_")
    
    # Check if it's already a valid key
    if normalized in EQUIPMENT_DISPLAY_MAP:
        return normalized
    
    # Check reverse map (display name -> key)
    if normalized in EQUIPMENT_REVERSE_MAP:
        return EQUIPMENT_REVERSE_MAP[normalized]
    
    return normalized


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_equipment_naming(
    exercise: ExerciseSummary,
    registry: FamilyRegistry,
) -> List[Dict[str, Any]]:
    """
    Validate exercise naming against family taxonomy rules.
    
    Args:
        exercise: Exercise to validate
        registry: Family registry with equipment info
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check if family needs equipment suffixes
    if not registry.needs_equipment_suffixes():
        # Single-equipment family - no suffix required
        return errors
    
    # Multi-equipment family - validate naming
    has_suffix = exercise.has_equipment_in_name()
    
    if not has_suffix:
        errors.append({
            "code": "MISSING_EQUIPMENT_QUALIFIER",
            "message": f"Exercise '{exercise.name}' needs equipment qualifier for multi-equipment family",
            "doc_id": exercise.doc_id,
            "suggestion": derive_canonical_name(exercise.name, exercise.primary_equipment),
        })
        return errors
    
    # Has suffix - check if it matches primary equipment
    name_equipment = exercise.extract_name_equipment()
    if name_equipment:
        expected_suffix = derive_equipment_suffix(exercise.primary_equipment or "")
        if name_equipment.lower() != expected_suffix.lower():
            errors.append({
                "code": "EQUIPMENT_MISMATCH",
                "message": f"Name suffix '({name_equipment})' doesn't match primary equipment '{exercise.primary_equipment}'",
                "doc_id": exercise.doc_id,
                "expected": expected_suffix,
                "actual": name_equipment,
            })
    
    return errors


def validate_name_equipment_consistency(
    exercise: ExerciseSummary,
) -> List[Dict[str, Any]]:
    """
    Validate that equipment implied by name matches stored equipment.
    
    Detects issues like "Hex Bar Deadlift" with equipment=['trap bar'].
    
    Args:
        exercise: Exercise to validate
        
    Returns:
        List of validation errors (empty if consistent)
    """
    errors = []
    
    # Detect equipment from name
    name_implies = detect_equipment_from_name(exercise.name)
    
    if not name_implies:
        # No equipment detected in name - OK
        return errors
    
    # Get stored primary equipment and normalize
    stored_equipment = normalize_equipment_value(exercise.primary_equipment or "")
    
    if name_implies != stored_equipment:
        errors.append({
            "code": "NAME_EQUIPMENT_INCONSISTENCY",
            "message": f"Name implies '{name_implies}' but equipment array has '{stored_equipment}'",
            "doc_id": exercise.doc_id,
            "name_implies": name_implies,
            "stored_equipment": stored_equipment,
            "recommendation": f"Fix equipment array to '{name_implies}' or rename exercise",
        })
    
    return errors


def validate_slug_derivation(exercise: ExerciseSummary) -> List[Dict[str, Any]]:
    """
    Validate that exercise slug matches derived slug from name.
    
    Args:
        exercise: Exercise to validate
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    expected_slug = derive_name_slug(exercise.name)
    if exercise.name_slug != expected_slug:
        errors.append({
            "code": "SLUG_MISMATCH",
            "message": f"Slug '{exercise.name_slug}' doesn't match derived slug",
            "doc_id": exercise.doc_id,
            "expected": expected_slug,
            "actual": exercise.name_slug,
        })
    
    return errors


def detect_duplicate_equipment(exercises: List[ExerciseSummary]) -> List[Dict[str, Any]]:
    """
    Detect duplicate equipment variants within a family.
    
    Args:
        exercises: List of exercises in family
        
    Returns:
        List of duplicate groups
    """
    duplicates = []
    
    # Group by primary equipment
    by_equipment: Dict[str, List[ExerciseSummary]] = {}
    for ex in exercises:
        key = normalize_equipment_value(ex.primary_equipment or "none")
        if key not in by_equipment:
            by_equipment[key] = []
        by_equipment[key].append(ex)
    
    # Find duplicates
    for equipment, group in by_equipment.items():
        if len(group) > 1:
            duplicates.append({
                "equipment": equipment,
                "exercises": [
                    {"doc_id": ex.doc_id, "name": ex.name, "status": ex.status}
                    for ex in group
                ],
                "count": len(group),
            })
    
    return duplicates


__all__ = [
    "EQUIPMENT_DISPLAY_MAP",
    "ATTACHMENT_DISPLAY_MAP",
    "GRIP_MODIFIERS",
    "STANCE_MODIFIERS",
    "POSITION_MODIFIERS",
    "ROM_MODIFIERS",
    "detect_equipment_from_name",
    "derive_equipment_suffix",
    "derive_canonical_name",
    "derive_movement_family",
    "derive_name_slug",
    "compute_primary_equipment_set",
    "normalize_equipment_value",
    "validate_equipment_naming",
    "validate_name_equipment_consistency",
    "validate_slug_derivation",
    "detect_duplicate_equipment",
]
