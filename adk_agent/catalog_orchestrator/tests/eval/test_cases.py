"""
Enrichment Eval Test Cases — defines expected behavior for each fixture.

Each test case wraps a fixture exercise document with:
- Expected behavior: what the enrichment should do (generate, fix, preserve)
- Quality requirements: scenario-specific quality bars
- Gold standards: example ideal output for the judge to reference

Categories:
- generate: Exercise has missing fields — enrichment should fill them
- fix: Exercise has bad content — enrichment should improve it
- preserve: Exercise is already good — enrichment should leave it alone
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tests.eval.fixtures import ALL_FIXTURES


@dataclass
class EnrichmentTestCase:
    """A single test case for enrichment quality evaluation."""
    id: str
    category: str  # "generate" | "fix" | "preserve"
    fixture_key: str  # Key into ALL_FIXTURES
    exercise: Dict[str, Any]  # The exercise document (from fixture builder)

    # Expected behavior
    expected_behavior: str  # Description for the judge
    fields_to_check: List[str]  # Which fields should be scored

    # Gold standards
    gold_examples: Dict[str, Any]  # Example ideal values per field
    quality_requirements: List[str]  # Scenario-specific quality bars

    # Tags for filtering
    tags: List[str] = field(default_factory=list)


# =============================================================================
# GENERATE CASES — missing fields, enrichment should create content
# =============================================================================

GENERATE_CASES = [
    EnrichmentTestCase(
        id="gen_001",
        category="generate",
        fixture_key="bare_compound",
        exercise=ALL_FIXTURES["bare_compound"](),
        expected_behavior=(
            "Generate all missing content fields for a barbell front squat. "
            "Should produce description, execution_notes, common_mistakes, "
            "suitability_notes, programming_use_cases, stimulus_tags, and "
            "muscles.contribution."
        ),
        fields_to_check=[
            "description", "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases", "stimulus_tags",
        ],
        gold_examples={
            "execution_notes": [
                "Rack the bar on your front deltoids with elbows high",
                "Keep your torso upright throughout the movement",
                "Drive through your heels and push your knees out",
            ],
            "common_mistakes": [
                "Letting the elbows drop during the lift",
                "Rounding the upper back under load",
                "Shifting weight onto the toes",
            ],
        },
        quality_requirements=[
            "execution_notes use second person imperative voice",
            "common_mistakes use third person descriptive (gerund phrases)",
            "description is 1-2 sentences, 100-250 characters",
            "All fields follow the content style guide",
        ],
        tags=["compound", "barbell", "lower"],
    ),

    EnrichmentTestCase(
        id="gen_002",
        category="generate",
        fixture_key="bare_isolation",
        exercise=ALL_FIXTURES["bare_isolation"](),
        expected_behavior=(
            "Generate content for a cable face pull. Should include "
            "beginner-appropriate language and acknowledge the exercise "
            "targets rear delts and upper back."
        ),
        fields_to_check=[
            "description", "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases", "stimulus_tags",
        ],
        gold_examples={
            "execution_notes": [
                "Set the cable at upper chest height with a rope attachment",
                "Pull toward your face, separating the rope ends at your ears",
                "Squeeze your shoulder blades together at the end of the pull",
            ],
            "common_mistakes": [
                "Using too much weight and losing scapular retraction",
                "Pulling to the chest instead of face level",
            ],
        },
        quality_requirements=[
            "Content acknowledges this is a posterior deltoid/upper back exercise",
            "Suitability notes mention beginner-friendly nature",
            "execution_notes items are 8-20 words each",
        ],
        tags=["isolation", "cable", "upper"],
    ),

    EnrichmentTestCase(
        id="gen_003",
        category="generate",
        fixture_key="bare_bodyweight",
        exercise=ALL_FIXTURES["bare_bodyweight"](),
        expected_behavior=(
            "Generate content for bodyweight dips. Should mention "
            "chest and tricep focus, and note the intermediate difficulty."
        ),
        fields_to_check=[
            "description", "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases", "stimulus_tags",
        ],
        gold_examples={
            "execution_notes": [
                "Grip the bars and support your body with arms extended",
                "Lower yourself until your upper arms are parallel to the floor",
                "Press back up to full lockout without swinging",
            ],
        },
        quality_requirements=[
            "Mentions both chest and tricep involvement",
            "Notes that shoulder mobility is a prerequisite",
            "Does not reference equipment beyond parallel bars / dip station",
        ],
        tags=["compound", "bodyweight", "upper"],
    ),

    EnrichmentTestCase(
        id="gen_004",
        category="generate",
        fixture_key="bare_hinge",
        exercise=ALL_FIXTURES["bare_hinge"](),
        expected_behavior=(
            "Generate content for barbell good mornings. Should emphasize "
            "the hip hinge pattern and hamstring/lower back loading."
        ),
        fields_to_check=[
            "description", "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases",
        ],
        gold_examples={
            "execution_notes": [
                "Place the bar across your upper back as for a squat",
                "Hinge forward at the hips with a slight knee bend",
                "Drive your hips forward to return to standing",
            ],
        },
        quality_requirements=[
            "Emphasizes hip hinge mechanics",
            "Mentions lower back strength as both a benefit and risk",
            "execution_notes are concise cues, not paragraph descriptions",
        ],
        tags=["compound", "barbell", "hinge"],
    ),

    EnrichmentTestCase(
        id="gen_005",
        category="generate",
        fixture_key="bare_machine",
        exercise=ALL_FIXTURES["bare_machine"](),
        expected_behavior=(
            "Generate content for machine leg press. Should acknowledge "
            "machine stability and beginner suitability."
        ),
        fields_to_check=[
            "description", "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases",
        ],
        gold_examples={
            "suitability_notes": [
                "Machine guidance makes this accessible for all experience levels",
                "Allows heavy loading without spinal compression",
            ],
        },
        quality_requirements=[
            "Suitability notes acknowledge beginner-friendly nature of machines",
            "Does not overstate difficulty for a machine exercise",
            "programming_use_cases are complete sentences ending with periods",
        ],
        tags=["compound", "machine", "lower"],
    ),
]


# =============================================================================
# FIX CASES — bad content that needs improvement
# =============================================================================

FIX_CASES = [
    EnrichmentTestCase(
        id="fix_001",
        category="fix",
        fixture_key="inconsistent_voice",
        exercise=ALL_FIXTURES["inconsistent_voice"](),
        expected_behavior=(
            "Fix voice inconsistencies: execution_notes should all use "
            "second person imperative, common_mistakes should use third "
            "person descriptive. Improve vague suitability notes and "
            "programming use cases."
        ),
        fields_to_check=[
            "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases", "description",
        ],
        gold_examples={
            "execution_notes": [
                "Hinge at the hips and grip the bar just outside your knees",
                "Pull the bar to your lower chest while squeezing your shoulder blades",
                "Keep your elbows close to your body throughout the pull",
                "Lower the bar under control to full arm extension",
            ],
            "common_mistakes": [
                "Rounding the lower back during the pull",
                "Using momentum to swing the weight up",
                "Not squeezing the shoulder blades at the top",
            ],
        },
        quality_requirements=[
            "All execution_notes use 'you/your' imperative voice",
            "No execution_notes start with numbered prefixes",
            "No execution_notes use first person ('I recommend')",
            "No execution_notes use third person ('The lifter should')",
            "common_mistakes use gerund phrases, no 'you' or 'should'",
            "suitability_notes are specific, not single-word",
            "programming_use_cases are complete sentences with periods",
        ],
        tags=["fix", "voice", "compound"],
    ),

    EnrichmentTestCase(
        id="fix_002",
        category="fix",
        fixture_key="numbered_markdown",
        exercise=ALL_FIXTURES["numbered_markdown"](),
        expected_behavior=(
            "Strip markdown formatting and numbered prefixes. "
            "Rewrite as clean prose following the style guide. "
            "May also enrich missing fields."
        ),
        fields_to_check=[
            "execution_notes", "common_mistakes", "description",
        ],
        gold_examples={
            "execution_notes": [
                "Unrack the bar at shoulder height and step back",
                "Press the bar overhead until your arms are fully locked out",
                "Lower the bar back to your shoulders under control",
                "Exhale as you press up through the sticking point",
            ],
        },
        quality_requirements=[
            "No **bold** markdown in any field",
            "No numbered prefixes (1., Step 1:, etc.)",
            "No bullet markers (-, *)",
            "Items are plain text cues in imperative voice",
            "Description is more than one short sentence",
        ],
        tags=["fix", "formatting", "compound"],
    ),

    EnrichmentTestCase(
        id="fix_003",
        category="fix",
        fixture_key="overly_verbose",
        exercise=ALL_FIXTURES["overly_verbose"](),
        expected_behavior=(
            "Condense verbose, paragraph-style content into concise cues. "
            "execution_notes should be 8-20 words each, not multi-sentence "
            "paragraphs. Description should be 100-250 characters."
        ),
        fields_to_check=[
            "execution_notes", "common_mistakes", "description",
        ],
        gold_examples={
            "execution_notes": [
                "Stand hip-width apart with dumbbells in front of your thighs",
                "Hinge at the hips with a slight knee bend, lowering along your legs",
                "Lower until you feel a deep hamstring stretch around mid-shin",
                "Drive your hips forward and squeeze your glutes to stand",
            ],
        },
        quality_requirements=[
            "execution_notes items are each 8-20 words (not paragraphs)",
            "common_mistakes items are each 6-15 words",
            "description is 100-250 characters (not a full paragraph)",
            "Content is concise but retains key safety/form cues",
        ],
        tags=["fix", "verbose", "hinge"],
    ),

    EnrichmentTestCase(
        id="fix_004",
        category="fix",
        fixture_key="terse_fragments",
        exercise=ALL_FIXTURES["terse_fragments"](),
        expected_behavior=(
            "Expand terse, fragment-style notes into complete, useful cues. "
            "'Raise arms' should become a specific instruction. "
            "'Bad form' should become a specific mistake description."
        ),
        fields_to_check=[
            "execution_notes", "common_mistakes", "description",
            "suitability_notes", "programming_use_cases",
        ],
        gold_examples={
            "execution_notes": [
                "Stand with dumbbells at your sides, palms facing inward",
                "Raise your arms out to the sides until parallel with the floor",
                "Lead with your elbows, keeping a slight bend throughout",
                "Lower the weights slowly over 2-3 seconds",
            ],
            "common_mistakes": [
                "Using too much weight and compensating with momentum",
                "Shrugging the shoulders up toward the ears",
                "Raising the arms above shoulder height",
            ],
        },
        quality_requirements=[
            "execution_notes items are 8-20 words each (no 2-word fragments)",
            "common_mistakes items are 6-15 words each (no vague labels)",
            "description is specific to lateral raises, not generic",
            "All generated content is specific to THIS exercise",
        ],
        tags=["fix", "terse", "isolation"],
    ),

    EnrichmentTestCase(
        id="fix_005",
        category="fix",
        fixture_key="mixed_quality",
        exercise=ALL_FIXTURES["mixed_quality"](),
        expected_behavior=(
            "Keep good execution_notes and description as-is. "
            "Fix vague common_mistakes ('Bad grip', 'Bouncing'). "
            "Generate missing suitability_notes, programming_use_cases, "
            "and stimulus_tags."
        ),
        fields_to_check=[
            "common_mistakes", "suitability_notes",
            "programming_use_cases", "stimulus_tags",
        ],
        gold_examples={
            "common_mistakes": [
                "Gripping too wide or too narrow for the incline angle",
                "Bouncing the bar off the chest to move more weight",
                "Setting the bench angle too steep, shifting load to shoulders",
            ],
        },
        quality_requirements=[
            "Existing good execution_notes are NOT changed",
            "Existing good description is NOT changed",
            "common_mistakes are rewritten to be specific and descriptive",
            "Missing fields are generated following the style guide",
        ],
        tags=["fix", "selective", "compound"],
    ),
]


# =============================================================================
# PRESERVE CASES — good content that should be left alone
# =============================================================================

PRESERVE_CASES = [
    EnrichmentTestCase(
        id="pres_001",
        category="preserve",
        fixture_key="already_good_compound",
        exercise=ALL_FIXTURES["already_good_compound"](),
        expected_behavior=(
            "Exercise is well-formatted and complete. Enrichment should "
            "make minimal or no changes. Judge should verify that the "
            "original content quality is maintained."
        ),
        fields_to_check=[
            "execution_notes", "common_mistakes", "description",
            "suitability_notes", "programming_use_cases",
        ],
        gold_examples={},  # Use the exercise's own content as gold
        quality_requirements=[
            "execution_notes remain in imperative voice",
            "common_mistakes remain in gerund/descriptive form",
            "No unnecessary rewording of already-good content",
            "If changes made, quality must be equal or better",
        ],
        tags=["preserve", "compound", "barbell"],
    ),

    EnrichmentTestCase(
        id="pres_002",
        category="preserve",
        fixture_key="already_good_isolation",
        exercise=ALL_FIXTURES["already_good_isolation"](),
        expected_behavior=(
            "Well-formatted isolation exercise. Enrichment should "
            "make minimal or no changes."
        ),
        fields_to_check=[
            "execution_notes", "common_mistakes", "description",
            "suitability_notes", "programming_use_cases",
        ],
        gold_examples={},
        quality_requirements=[
            "Content quality is maintained or improved",
            "No unnecessary rewording of already-good content",
            "Style guide compliance preserved",
        ],
        tags=["preserve", "isolation", "dumbbell"],
    ),
]


# =============================================================================
# ALL CASES
# =============================================================================

ALL_CASES: List[EnrichmentTestCase] = GENERATE_CASES + FIX_CASES + PRESERVE_CASES


def get_cases(
    category: str = None,
    case_id: str = None,
    tags: List[str] = None,
) -> List[EnrichmentTestCase]:
    """Filter test cases."""
    cases = ALL_CASES
    if case_id:
        cases = [c for c in cases if c.id == case_id]
    if category:
        cases = [c for c in cases if c.category == category]
    if tags:
        cases = [c for c in cases if any(t in c.tags for t in tags)]
    return cases
