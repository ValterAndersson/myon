"""
Integration tests for enrichment validation pipeline.

Tests that LLM enrichment output passes enum validation after normalization.
Uses MockLLMClient with known outputs to verify canonical values.
"""

from app.enrichment.engine import (
    normalize_enrichment_output,
    validate_normalized_output,
    _normalize_category,
    _normalize_movement_type,
    _normalize_movement_split,
)
from app.enrichment.exercise_field_guide import (
    CATEGORIES,
    MOVEMENT_TYPES,
    MOVEMENT_SPLITS,
)


# =============================================================================
# normalize_enrichment_output tests
# =============================================================================


class TestNormalizeEnrichmentOutput:
    """Tests for the normalization step (before validation)."""

    def test_normalizes_muscle_names_underscores_to_spaces(self):
        changes = {"muscles.primary": ["gluteus_maximus", "quadriceps"]}
        result = normalize_enrichment_output(changes)
        assert result["muscles.primary"] == ["gluteus maximus", "quadriceps"]

    def test_normalizes_muscle_names_lowercase(self):
        changes = {"muscles.primary": ["Quadriceps", "GLUTES"]}
        result = normalize_enrichment_output(changes)
        assert result["muscles.primary"] == ["quadriceps", "glutes"]

    def test_deduplicates_muscle_names(self):
        changes = {"muscles.primary": ["quadriceps", "Quadriceps"]}
        result = normalize_enrichment_output(changes)
        assert result["muscles.primary"] == ["quadriceps"]

    def test_normalizes_contribution_map_keys(self):
        changes = {
            "muscles.contribution": {
                "Gluteus_Maximus": 0.5,
                "quadriceps": 0.5,
            }
        }
        result = normalize_enrichment_output(changes)
        assert "gluteus maximus" in result["muscles.contribution"]
        assert "quadriceps" in result["muscles.contribution"]

    def test_clamps_contribution_values(self):
        changes = {
            "muscles.contribution": {
                "quadriceps": 1.5,
                "hamstrings": -0.2,
            }
        }
        result = normalize_enrichment_output(changes)
        assert result["muscles.contribution"]["quadriceps"] == 1.0
        assert result["muscles.contribution"]["hamstrings"] == 0.0

    def test_normalizes_stimulus_tags_title_case(self):
        changes = {"stimulus_tags": ["hypertrophy", "STRENGTH", "core engagement"]}
        result = normalize_enrichment_output(changes)
        assert result["stimulus_tags"] == ["Hypertrophy", "Strength", "Core Engagement"]

    def test_deduplicates_stimulus_tags(self):
        changes = {"stimulus_tags": ["Hypertrophy", "hypertrophy", "HYPERTROPHY"]}
        result = normalize_enrichment_output(changes)
        assert result["stimulus_tags"] == ["Hypertrophy"]

    def test_normalizes_category_valid(self):
        changes = {"category": "compound"}
        result = normalize_enrichment_output(changes)
        assert result["category"] == "compound"

    def test_normalizes_category_stretching_to_mobility(self):
        changes = {"category": "stretching"}
        result = normalize_enrichment_output(changes)
        assert result["category"] == "mobility"

    def test_normalizes_category_plyometric_to_compound(self):
        changes = {"category": "plyometric"}
        result = normalize_enrichment_output(changes)
        assert result["category"] == "compound"

    def test_normalizes_category_isometric_to_mobility(self):
        changes = {"category": "isometric"}
        result = normalize_enrichment_output(changes)
        assert result["category"] == "mobility"

    def test_normalizes_category_unknown_to_compound(self):
        changes = {"category": "unknown_junk"}
        result = normalize_enrichment_output(changes)
        assert result["category"] == "compound"

    def test_passes_through_other_fields(self):
        changes = {
            "description": "A good exercise description.",
            "execution_notes": ["Step 1", "Step 2"],
        }
        result = normalize_enrichment_output(changes)
        assert result["description"] == "A good exercise description."
        assert result["execution_notes"] == ["Step 1", "Step 2"]

    def test_drops_none_values(self):
        changes = {"category": "compound", "description": None}
        result = normalize_enrichment_output(changes)
        assert "description" not in result
        assert result["category"] == "compound"


# =============================================================================
# validate_normalized_output tests
# =============================================================================


class TestValidateNormalizedOutput:
    """Tests for the validation step (after normalization)."""

    def test_accepts_valid_category(self):
        for cat in CATEGORIES:
            result = validate_normalized_output({"category": cat})
            assert result["category"] == cat

    def test_drops_invalid_category(self):
        result = validate_normalized_output({"category": "not_a_category"})
        assert "category" not in result

    def test_accepts_valid_movement_type(self):
        for mt in MOVEMENT_TYPES:
            result = validate_normalized_output({"movement.type": mt})
            assert result["movement.type"] == mt

    def test_drops_invalid_movement_type(self):
        result = validate_normalized_output({"movement.type": "press"})
        assert "movement.type" not in result

    def test_accepts_valid_movement_split(self):
        for ms in MOVEMENT_SPLITS:
            result = validate_normalized_output({"movement.split": ms})
            assert result["movement.split"] == ms

    def test_drops_invalid_movement_split(self):
        result = validate_normalized_output({"movement.split": "legs"})
        assert "movement.split" not in result

    def test_accepts_valid_equipment(self):
        result = validate_normalized_output(
            {"equipment": ["barbell", "dumbbell"]}
        )
        assert result["equipment"] == ["barbell", "dumbbell"]

    def test_drops_invalid_equipment_values(self):
        result = validate_normalized_output(
            {"equipment": ["barbell", "magic-wand"]}
        )
        assert result["equipment"] == ["barbell"]

    def test_drops_equipment_key_if_all_invalid(self):
        result = validate_normalized_output(
            {"equipment": ["magic-wand", "unicorn"]}
        )
        assert "equipment" not in result

    def test_keeps_muscle_names_with_warning(self):
        """Muscle names warn but don't drop — LLM may produce valid names not in our list."""
        result = validate_normalized_output(
            {"muscles.primary": ["quadriceps", "some unusual muscle"]}
        )
        assert result["muscles.primary"] == ["quadriceps", "some unusual muscle"]

    def test_renormalizes_bad_contribution_sum(self):
        result = validate_normalized_output(
            {"muscles.contribution": {"quadriceps": 0.8, "glutes": 0.6}}
        )
        contrib = result["muscles.contribution"]
        total = sum(contrib.values())
        assert abs(total - 1.0) < 0.01

    def test_accepts_good_contribution_sum(self):
        result = validate_normalized_output(
            {"muscles.contribution": {"quadriceps": 0.6, "glutes": 0.4}}
        )
        assert result["muscles.contribution"] == {"quadriceps": 0.6, "glutes": 0.4}

    def test_drops_too_short_description(self):
        result = validate_normalized_output({"description": "Short."})
        assert "description" not in result

    def test_drops_description_under_50_chars(self):
        """Descriptions 20-49 chars must also be dropped (aligned with quality_scanner)."""
        desc_30 = "A basic compound exercise ok."  # 30 chars
        result = validate_normalized_output({"description": desc_30})
        assert "description" not in result

    def test_accepts_good_description(self):
        desc = "A compound lower body exercise targeting quadriceps and glutes."
        assert len(desc) >= 50  # Guard: ensure test fixture is actually valid
        result = validate_normalized_output({"description": desc})
        assert result["description"] == desc

    def test_passes_through_other_fields(self):
        result = validate_normalized_output({
            "execution_notes": ["Keep back straight"],
            "common_mistakes": ["Rounding lower back"],
            "suitability_notes": ["Good for beginners"],
        })
        assert result["execution_notes"] == ["Keep back straight"]
        assert result["common_mistakes"] == ["Rounding lower back"]
        assert result["suitability_notes"] == ["Good for beginners"]

    def test_full_valid_enrichment_passes(self):
        """A complete, valid enrichment result should pass through entirely."""
        changes = {
            "category": "compound",
            "movement.type": "squat",
            "movement.split": "lower",
            "equipment": ["barbell"],
            "muscles.primary": ["quadriceps", "glutes"],
            "muscles.secondary": ["hamstrings", "erector spinae"],
            "muscles.contribution": {
                "quadriceps": 0.45,
                "glutes": 0.30,
                "hamstrings": 0.15,
                "erector spinae": 0.10,
            },
            "description": (
                "A fundamental lower body compound exercise that builds "
                "strength in the quadriceps and glutes."
            ),
            "stimulus_tags": ["Compound Movement", "Strength", "Hypertrophy"],
            "execution_notes": [
                "Keep your knees tracking over your toes",
                "Maintain a neutral spine",
            ],
        }
        result = validate_normalized_output(changes)
        assert len(result) == len(changes)
        assert result["category"] == "compound"
        assert result["movement.type"] == "squat"

    def test_partial_valid_enrichment_keeps_good_drops_bad(self):
        """Mixed valid/invalid fields: keep valid, drop invalid."""
        changes = {
            "category": "compound",       # valid
            "movement.type": "press",     # invalid (not canonical)
            "movement.split": "lower",    # valid
            "description": "OK",          # too short
        }
        result = validate_normalized_output(changes)
        assert result["category"] == "compound"
        assert "movement.type" not in result
        assert result["movement.split"] == "lower"
        assert "description" not in result


# =============================================================================
# _normalize_category tests
# =============================================================================


class TestNormalizeCategory:
    """Tests for the category normalization function."""

    def test_valid_categories_pass_through(self):
        for cat in ["compound", "isolation", "cardio", "mobility", "core"]:
            assert _normalize_category(cat) == cat

    def test_stretching_maps_to_mobility(self):
        assert _normalize_category("stretching") == "mobility"

    def test_plyometric_maps_to_compound(self):
        assert _normalize_category("plyometric") == "compound"

    def test_isometric_maps_to_mobility(self):
        assert _normalize_category("isometric") == "mobility"

    def test_flexibility_maps_to_mobility(self):
        assert _normalize_category("flexibility") == "mobility"

    def test_explosive_maps_to_compound(self):
        assert _normalize_category("explosive") == "compound"

    def test_static_maps_to_mobility(self):
        assert _normalize_category("static") == "mobility"

    def test_exercise_maps_to_compound(self):
        assert _normalize_category("exercise") == "compound"

    def test_non_string_returns_compound(self):
        assert _normalize_category(None) == "compound"
        assert _normalize_category(123) == "compound"

    def test_unknown_returns_compound(self):
        assert _normalize_category("random_garbage") == "compound"

    def test_case_insensitive(self):
        assert _normalize_category("COMPOUND") == "compound"
        assert _normalize_category("Isolation") == "isolation"
        assert _normalize_category("STRETCHING") == "mobility"


# =============================================================================
# End-to-end normalization + validation pipeline
# =============================================================================


class TestNormalizationValidationPipeline:
    """Test the full pipeline: normalize then validate."""

    def test_pipeline_fixes_underscored_muscles_and_validates(self):
        raw_changes = {
            "muscles.primary": ["Gluteus_Maximus", "quadriceps"],
            "category": "compound",
            "movement.type": "squat",
        }
        normalized = normalize_enrichment_output(raw_changes)
        validated = validate_normalized_output(normalized)

        assert validated["muscles.primary"] == ["gluteus maximus", "quadriceps"]
        assert validated["category"] == "compound"
        assert validated["movement.type"] == "squat"

    def test_pipeline_normalizes_category_then_validates(self):
        raw_changes = {"category": "stretching"}
        normalized = normalize_enrichment_output(raw_changes)
        validated = validate_normalized_output(normalized)

        # stretching → mobility (normalization) → valid (validation)
        assert validated["category"] == "mobility"

    def test_pipeline_normalizes_movement_type_press_to_push(self):
        """'press' should be normalized to 'push' and then pass validation."""
        raw_changes = {
            "category": "compound",
            "movement.type": "press",
        }
        normalized = normalize_enrichment_output(raw_changes)
        validated = validate_normalized_output(normalized)

        assert validated["category"] == "compound"
        assert validated["movement.type"] == "push"

    def test_pipeline_normalizes_movement_split_full_body(self):
        """'full body' (with space) should normalize to 'full_body'."""
        raw_changes = {"movement.split": "full body"}
        normalized = normalize_enrichment_output(raw_changes)
        validated = validate_normalized_output(normalized)

        assert validated["movement.split"] == "full_body"

    def test_pipeline_drops_unmappable_movement_type(self):
        raw_changes = {
            "category": "compound",
            "movement.type": "totally_unknown",
        }
        normalized = normalize_enrichment_output(raw_changes)
        validated = validate_normalized_output(normalized)

        assert validated["category"] == "compound"
        assert "movement.type" not in validated


# =============================================================================
# _normalize_movement_type tests
# =============================================================================


class TestNormalizeMovementType:
    """Tests for the movement type normalization function."""

    def test_valid_types_pass_through(self):
        for mt in MOVEMENT_TYPES:
            assert _normalize_movement_type(mt) == mt

    def test_press_maps_to_push(self):
        assert _normalize_movement_type("press") == "push"

    def test_pressing_maps_to_push(self):
        assert _normalize_movement_type("pressing") == "push"

    def test_row_maps_to_pull(self):
        assert _normalize_movement_type("row") == "pull"

    def test_curl_maps_to_flexion(self):
        assert _normalize_movement_type("curl") == "flexion"

    def test_deadlift_maps_to_hinge(self):
        assert _normalize_movement_type("deadlift") == "hinge"

    def test_lunge_maps_to_squat(self):
        assert _normalize_movement_type("lunge") == "squat"

    def test_fly_maps_to_adduction(self):
        assert _normalize_movement_type("fly") == "adduction"

    def test_raise_maps_to_abduction(self):
        assert _normalize_movement_type("raise") == "abduction"

    def test_twist_maps_to_rotation(self):
        assert _normalize_movement_type("twist") == "rotation"

    def test_dip_maps_to_push(self):
        assert _normalize_movement_type("dip") == "push"

    def test_unmappable_returns_none(self):
        assert _normalize_movement_type("totally_unknown") is None

    def test_non_string_returns_none(self):
        assert _normalize_movement_type(None) is None
        assert _normalize_movement_type(123) is None

    def test_case_insensitive(self):
        assert _normalize_movement_type("PUSH") == "push"
        assert _normalize_movement_type("Press") == "push"


# =============================================================================
# _normalize_movement_split tests
# =============================================================================


class TestNormalizeMovementSplit:
    """Tests for the movement split normalization function."""

    def test_valid_splits_pass_through(self):
        for ms in MOVEMENT_SPLITS:
            assert _normalize_movement_split(ms) == ms

    def test_full_body_with_space(self):
        assert _normalize_movement_split("full body") == "full_body"

    def test_upper_body_maps_to_upper(self):
        assert _normalize_movement_split("upper body") == "upper"

    def test_lower_body_maps_to_lower(self):
        assert _normalize_movement_split("lower body") == "lower"

    def test_legs_maps_to_lower(self):
        assert _normalize_movement_split("legs") == "lower"

    def test_abs_maps_to_core(self):
        assert _normalize_movement_split("abs") == "core"

    def test_chest_maps_to_upper(self):
        assert _normalize_movement_split("chest") == "upper"

    def test_unmappable_returns_none(self):
        assert _normalize_movement_split("totally_unknown") is None

    def test_non_string_returns_none(self):
        assert _normalize_movement_split(None) is None
        assert _normalize_movement_split(123) is None

    def test_list_takes_first_mappable(self):
        assert _normalize_movement_split(["unknown", "upper"]) == "upper"

    def test_list_with_no_mappable_returns_none(self):
        assert _normalize_movement_split(["unknown1", "unknown2"]) is None

    def test_case_insensitive(self):
        assert _normalize_movement_split("UPPER") == "upper"
        assert _normalize_movement_split("Full Body") == "full_body"
