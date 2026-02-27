"""Tests for warm-up set generation in tool_add_exercise."""
from __future__ import annotations

import pytest
from app.shell.tools import _calculate_warmup_ramp


class TestCalculateWarmupRamp:
    """Test warmup ramp calculation."""

    def test_standard_3_warmups(self):
        sets = _calculate_warmup_ramp(100.0, count=3, progression="standard")
        assert len(sets) == 3
        assert sets[0]["weight"] == 50.0
        assert sets[1]["weight"] == 65.0
        assert sets[2]["weight"] == 80.0
        assert sets[0]["reps"] == 10
        assert sets[1]["reps"] == 8
        assert sets[2]["reps"] == 5
        for s in sets:
            assert s["set_type"] == "warmup"

    def test_conservative_2_warmups(self):
        sets = _calculate_warmup_ramp(100.0, count=2, progression="conservative")
        assert len(sets) == 2
        assert sets[0]["weight"] == 60.0
        assert sets[1]["weight"] == 80.0

    def test_rounding_to_2_5kg(self):
        sets = _calculate_warmup_ramp(130.0, count=3, progression="standard")
        assert sets[0]["weight"] == 65.0
        assert sets[1]["weight"] == 85.0  # 130*0.65=84.5 → 85.0
        assert sets[2]["weight"] == 105.0  # 130*0.80=104.0 → 105.0

    def test_light_weight_skips_warmups(self):
        sets = _calculate_warmup_ramp(20.0, count=3, progression="standard")
        assert sets == []

    def test_zero_count_returns_empty(self):
        sets = _calculate_warmup_ramp(100.0, count=0, progression="standard")
        assert sets == []

    def test_sets_have_unique_ids(self):
        sets = _calculate_warmup_ramp(100.0, count=3, progression="standard")
        ids = [s["id"] for s in sets]
        assert len(set(ids)) == 3

    def test_default_rir_is_5(self):
        sets = _calculate_warmup_ramp(100.0, count=3, progression="standard")
        for s in sets:
            assert s.get("rir") == 5
