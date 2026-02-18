"""
Enrichment Eval Fixtures — synthetic exercise documents for eval testing.

Each fixture is a deterministic exercise document that exercises different
enrichment scenarios: missing fields, bad formatting, wrong voice, etc.

Fixtures are intentionally imperfect — they represent exercises that the
enrichment pipeline needs to improve. The eval measures HOW WELL the pipeline
improves them, and whether the output follows the content style guide.
"""

from __future__ import annotations
from typing import Any, Dict, List


# =============================================================================
# FIXTURE BUILDERS
# =============================================================================

def build_exercise(
    name: str,
    name_slug: str,
    family_slug: str,
    equipment: List[str],
    category: str,
    movement_type: str,
    movement_split: str,
    primary_muscles: List[str],
    secondary_muscles: List[str] = None,
    level: str = "intermediate",
    description: str = "",
    execution_notes: List[str] = None,
    common_mistakes: List[str] = None,
    suitability_notes: List[str] = None,
    programming_use_cases: List[str] = None,
    stimulus_tags: List[str] = None,
    contribution: Dict[str, float] = None,
) -> Dict[str, Any]:
    """Build a synthetic exercise document."""
    doc = {
        "name": name,
        "name_slug": name_slug,
        "family_slug": family_slug,
        "equipment": equipment,
        "category": category,
        "movement": {
            "type": movement_type,
            "split": movement_split,
        },
        "muscles": {
            "primary": primary_muscles,
            "secondary": secondary_muscles or [],
            "category": [],
        },
        "metadata": {
            "level": level,
        },
    }
    if description:
        doc["description"] = description
    if execution_notes is not None:
        doc["execution_notes"] = execution_notes
    if common_mistakes is not None:
        doc["common_mistakes"] = common_mistakes
    if suitability_notes is not None:
        doc["suitability_notes"] = suitability_notes
    if programming_use_cases is not None:
        doc["programming_use_cases"] = programming_use_cases
    if stimulus_tags is not None:
        doc["stimulus_tags"] = stimulus_tags
    if contribution is not None:
        doc["muscles"]["contribution"] = contribution
    return doc


# =============================================================================
# EXERCISES WITH MISSING CONTENT (enrichment should generate)
# =============================================================================

def bare_compound_barbell() -> Dict[str, Any]:
    """Barbell squat with minimal data — tests full content generation."""
    return build_exercise(
        name="Front Squat (Barbell)",
        name_slug="front_squat_barbell",
        family_slug="squat",
        equipment=["barbell"],
        category="compound",
        movement_type="squat",
        movement_split="lower",
        primary_muscles=["quadriceps", "glutes"],
        level="intermediate",
    )


def bare_isolation_cable() -> Dict[str, Any]:
    """Cable exercise with minimal data — tests isolation enrichment."""
    return build_exercise(
        name="Face Pull (Cable)",
        name_slug="face_pull_cable",
        family_slug="face_pull",
        equipment=["cable"],
        category="isolation",
        movement_type="pull",
        movement_split="upper",
        primary_muscles=["posterior deltoid", "trapezius"],
        level="beginner",
    )


def bare_bodyweight() -> Dict[str, Any]:
    """Bodyweight exercise with no content — tests bodyweight handling."""
    return build_exercise(
        name="Dip (Bodyweight)",
        name_slug="dip_bodyweight",
        family_slug="dip",
        equipment=["bodyweight", "dip-station"],
        category="compound",
        movement_type="push",
        movement_split="upper",
        primary_muscles=["pectoralis major", "triceps"],
        secondary_muscles=["anterior deltoid"],
        level="intermediate",
    )


def bare_hinge() -> Dict[str, Any]:
    """Hinge pattern with no content."""
    return build_exercise(
        name="Good Morning (Barbell)",
        name_slug="good_morning_barbell",
        family_slug="good_morning",
        equipment=["barbell"],
        category="compound",
        movement_type="hinge",
        movement_split="lower",
        primary_muscles=["hamstrings", "erector spinae"],
        level="intermediate",
    )


def bare_machine() -> Dict[str, Any]:
    """Machine exercise with no content — tests beginner-friendly framing."""
    return build_exercise(
        name="Leg Press (Machine)",
        name_slug="leg_press_machine",
        family_slug="leg_press",
        equipment=["machine"],
        category="compound",
        movement_type="squat",
        movement_split="lower",
        primary_muscles=["quadriceps", "glutes"],
        level="beginner",
    )


# =============================================================================
# EXERCISES WITH BAD/INCONSISTENT CONTENT (enrichment should fix)
# =============================================================================

def inconsistent_voice() -> Dict[str, Any]:
    """Exercise where notes mix first, second, and third person voice."""
    return build_exercise(
        name="Bent-over Row (Barbell)",
        name_slug="bent_over_row_barbell",
        family_slug="row",
        equipment=["barbell"],
        category="compound",
        movement_type="pull",
        movement_split="upper",
        primary_muscles=["latissimus dorsi", "rhomboids"],
        secondary_muscles=["biceps", "erector spinae"],
        level="intermediate",
        description="The bent-over row is a back exercise.",
        execution_notes=[
            "1. Hinge at the hips and grab the bar",
            "The lifter should pull the bar to the lower chest",
            "I recommend keeping elbows close to body",
            "Lower the bar under control",
        ],
        common_mistakes=[
            "You shouldn't round your back",
            "Using too much weight",
            "Not squeezing at the top of the movement",
        ],
        suitability_notes=[
            "Good",
            "Requires back strength",
        ],
        programming_use_cases=[
            "back day",
        ],
    )


def numbered_markdown_formatting() -> Dict[str, Any]:
    """Exercise with markdown and numbered prefixes that should be cleaned."""
    return build_exercise(
        name="Overhead Press (Barbell)",
        name_slug="overhead_press_barbell",
        family_slug="overhead_press",
        equipment=["barbell"],
        category="compound",
        movement_type="push",
        movement_split="upper",
        primary_muscles=["anterior deltoid", "triceps"],
        secondary_muscles=["trapezius", "pectoralis major"],
        level="intermediate",
        description="A shoulder pressing exercise.",
        execution_notes=[
            "**Step 1:** Unrack the bar from the rack at shoulder height",
            "**Step 2:** Press the bar overhead until arms are locked out",
            "**Step 3:** Lower the bar back to shoulders under control",
            "- Breathe out as you press up",
        ],
        common_mistakes=[
            "1. Leaning back too far",
            "2. Not locking out at the top",
            "3. Flaring ribs",
        ],
    )


def overly_verbose() -> Dict[str, Any]:
    """Exercise with long, paragraph-style notes instead of concise cues."""
    return build_exercise(
        name="Romanian Deadlift (Dumbbell)",
        name_slug="romanian_deadlift_dumbbell",
        family_slug="deadlift",
        equipment=["dumbbell"],
        category="compound",
        movement_type="hinge",
        movement_split="lower",
        primary_muscles=["hamstrings", "glutes"],
        secondary_muscles=["erector spinae"],
        level="intermediate",
        description="This is the Romanian Deadlift performed with dumbbells. It is an excellent exercise for the posterior chain muscles including the hamstrings, glutes, and lower back. The dumbbell variation allows for a greater range of motion and can be easier on the lower back compared to the barbell version.",
        execution_notes=[
            "Begin by standing with your feet hip-width apart and holding a dumbbell in each hand with an overhand grip in front of your thighs. This is your starting position for the exercise.",
            "While maintaining a slight bend in your knees and keeping your back completely flat and straight, slowly hinge forward at the hips and lower the dumbbells down along the front of your legs. You should feel a deep stretch in your hamstrings as you descend.",
            "Continue lowering until you feel a significant stretch in the hamstrings, which for most people is around mid-shin level, then reverse the movement by driving your hips forward and squeezing your glutes to return to the starting position.",
        ],
        common_mistakes=[
            "A very common mistake that many beginners make is rounding their lower back during the descent phase of the movement, which places excessive stress on the lumbar spine",
            "Bending the knees too much, which essentially turns the Romanian Deadlift into a conventional deadlift and takes the emphasis away from the hamstrings",
        ],
    )


def terse_fragments() -> Dict[str, Any]:
    """Exercise with very short, fragment-style notes lacking detail."""
    return build_exercise(
        name="Lateral Raise (Dumbbell)",
        name_slug="lateral_raise_dumbbell",
        family_slug="lateral_raise",
        equipment=["dumbbell"],
        category="isolation",
        movement_type="abduction",
        movement_split="upper",
        primary_muscles=["lateral deltoid"],
        level="beginner",
        description="Lateral raises.",
        execution_notes=[
            "Raise arms",
            "Lower slowly",
        ],
        common_mistakes=[
            "Too heavy",
            "Bad form",
        ],
    )


def mixed_quality() -> Dict[str, Any]:
    """Some fields good, others bad — tests selective enrichment."""
    return build_exercise(
        name="Incline Bench Press (Barbell)",
        name_slug="incline_bench_press_barbell",
        family_slug="bench_press",
        equipment=["barbell"],
        category="compound",
        movement_type="push",
        movement_split="upper",
        primary_muscles=["pectoralis major", "anterior deltoid"],
        secondary_muscles=["triceps"],
        level="intermediate",
        # Good description
        description="An upper chest pressing variation performed on an inclined bench, emphasizing the clavicular head of the pectoralis major and anterior deltoids.",
        # Good execution notes
        execution_notes=[
            "Set the bench to 30-45 degrees for optimal upper chest activation",
            "Keep your shoulder blades retracted and pinched together",
            "Lower the bar to your upper chest, just below the collarbone",
            "Press up and slightly back to lockout",
        ],
        # Bad common mistakes (too vague)
        common_mistakes=[
            "Bad grip",
            "Bouncing",
        ],
        # Missing: suitability_notes, programming_use_cases, stimulus_tags
    )


# =============================================================================
# EXERCISES WITH GOOD CONTENT (enrichment should mostly leave alone)
# =============================================================================

def already_good_compound() -> Dict[str, Any]:
    """Well-formatted exercise — tests that enrichment doesn't break it."""
    return build_exercise(
        name="Deadlift (Barbell)",
        name_slug="deadlift_barbell",
        family_slug="deadlift",
        equipment=["barbell"],
        category="compound",
        movement_type="hinge",
        movement_split="lower",
        primary_muscles=["hamstrings", "glutes", "erector spinae"],
        secondary_muscles=["quadriceps", "trapezius", "forearms"],
        level="intermediate",
        description="A foundational compound lift that develops full posterior chain strength, grip endurance, and overall pulling power from the floor.",
        execution_notes=[
            "Set up with the bar over mid-foot and feet hip-width apart",
            "Hinge at the hips and grip the bar just outside your knees",
            "Brace your core and pull your chest up before initiating the lift",
            "Drive through your heels and extend hips and knees simultaneously",
            "Lock out by squeezing your glutes at the top",
        ],
        common_mistakes=[
            "Rounding the lower back during the pull",
            "Jerking the bar off the floor instead of building tension",
            "Letting the bar drift away from the body",
            "Hyperextending at the top of the lift",
        ],
        suitability_notes=[
            "Requires good hip mobility and hamstring flexibility",
            "Start with lighter loads to establish proper movement pattern",
            "Not recommended for those with acute lower back injuries",
        ],
        programming_use_cases=[
            "Primary posterior chain movement in strength-focused programs.",
            "Foundation lift for powerlifting preparation.",
            "Full-body strength builder for intermediate and advanced lifters.",
        ],
        stimulus_tags=[
            "Compound Movement",
            "Strength",
            "Posterior Chain",
            "Grip Strength",
            "Full Body",
        ],
        contribution={
            "hamstrings": 0.30,
            "glutes": 0.25,
            "erector spinae": 0.20,
            "quadriceps": 0.15,
            "trapezius": 0.05,
            "forearms": 0.05,
        },
    )


def already_good_isolation() -> Dict[str, Any]:
    """Well-formatted isolation exercise — minimal changes expected."""
    return build_exercise(
        name="Bicep Curl (Dumbbell)",
        name_slug="bicep_curl_dumbbell",
        family_slug="bicep_curl",
        equipment=["dumbbell"],
        category="isolation",
        movement_type="flexion",
        movement_split="upper",
        primary_muscles=["biceps"],
        secondary_muscles=["brachialis", "forearms"],
        level="beginner",
        description="A classic arm isolation exercise that builds bicep size and strength through elbow flexion with dumbbells.",
        execution_notes=[
            "Stand with dumbbells at your sides, palms facing forward",
            "Curl the weights up by bending at the elbow only",
            "Squeeze at the top, then lower under control over 2-3 seconds",
        ],
        common_mistakes=[
            "Swinging the torso to generate momentum",
            "Not fully extending the arms at the bottom",
            "Rushing the eccentric phase",
        ],
        suitability_notes=[
            "Excellent starting exercise for arm training in beginners",
            "Low injury risk when performed with controlled tempo",
        ],
        programming_use_cases=[
            "Accessory exercise at the end of pull or arm workouts.",
            "Superset partner with tricep isolation for arm hypertrophy.",
            "Beginner-friendly isolation for building bicep mind-muscle connection.",
        ],
        stimulus_tags=[
            "Muscle Isolation",
            "Beginner Friendly",
            "Hypertrophy",
            "Controlled Movement",
        ],
        contribution={
            "biceps": 0.75,
            "brachialis": 0.15,
            "forearms": 0.10,
        },
    )


# =============================================================================
# ALL FIXTURES
# =============================================================================

ALL_FIXTURES = {
    # Missing content (generation needed)
    "bare_compound": bare_compound_barbell,
    "bare_isolation": bare_isolation_cable,
    "bare_bodyweight": bare_bodyweight,
    "bare_hinge": bare_hinge,
    "bare_machine": bare_machine,

    # Bad/inconsistent content (fix needed)
    "inconsistent_voice": inconsistent_voice,
    "numbered_markdown": numbered_markdown_formatting,
    "overly_verbose": overly_verbose,
    "terse_fragments": terse_fragments,
    "mixed_quality": mixed_quality,

    # Good content (should be preserved)
    "already_good_compound": already_good_compound,
    "already_good_isolation": already_good_isolation,
}
