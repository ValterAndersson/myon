#!/usr/bin/env python3
"""
Shell Agent wiring tests.

Validates agent configuration, tool registration, routing, planner templates,
and skill imports without requiring Vertex AI credentials or a deployment.

Usage:
    cd adk_agent/canvas_orchestrator
    python3 -m pytest tests/test_shell_agent.py -v
"""

from __future__ import annotations

import sys
import os

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# 1. AGENT CONFIGURATION
# ============================================================================

class TestAgentConfig:
    """Verify agent definition and model selection."""

    def test_model_is_flash(self):
        from app.shell.agent import ShellAgent
        assert "flash" in ShellAgent.model, (
            f"Expected gemini-2.5-flash, got {ShellAgent.model}"
        )

    def test_instruction_is_set(self):
        from app.shell.agent import ShellAgent
        assert ShellAgent.instruction is not None
        assert len(ShellAgent.instruction) > 500

    def test_instruction_contains_tool_routing(self):
        from app.shell.instruction import SHELL_INSTRUCTION
        assert "tool_get_training_analysis" in SHELL_INSTRUCTION
        assert "tool_get_exercise_progress" in SHELL_INSTRUCTION
        assert "tool_query_training_sets" in SHELL_INSTRUCTION
        assert "tool_get_planning_context" in SHELL_INSTRUCTION

    def test_instruction_contains_interpretation_guidance(self):
        from app.shell.instruction import SHELL_INSTRUCTION
        # Core interpretation rules preserved
        assert "Progression" in SHELL_INSTRUCTION or "progression" in SHELL_INSTRUCTION
        assert "Stalled" in SHELL_INSTRUCTION or "stalled" in SHELL_INSTRUCTION
        # Response structure preserved
        assert "Verdict" in SHELL_INSTRUCTION
        assert "Evidence" in SHELL_INSTRUCTION

    def test_instruction_no_deleted_tools(self):
        from app.shell.instruction import SHELL_INSTRUCTION
        assert "tool_get_coaching_context" not in SHELL_INSTRUCTION
        assert "tool_get_recent_insights" not in SHELL_INSTRUCTION
        assert "tool_get_daily_brief" not in SHELL_INSTRUCTION
        assert "tool_get_latest_weekly_review" not in SHELL_INSTRUCTION

    def test_factory_matches_singleton(self):
        from app.shell.agent import ShellAgent, create_shell_agent
        fresh = create_shell_agent()
        assert fresh.model == ShellAgent.model
        assert fresh.instruction == ShellAgent.instruction

    def test_root_agent_is_shell_agent(self):
        from app.shell.agent import root_agent, ShellAgent
        assert root_agent is ShellAgent


# ============================================================================
# 2. TOOL REGISTRY
# ============================================================================

class TestToolRegistry:
    """Verify all expected tools are registered and no dead tools remain."""

    EXPECTED_TOOLS = {
        # Read tools
        "tool_get_training_context",
        "tool_get_user_profile",
        "tool_search_exercises",
        "tool_get_exercise_details",
        "tool_get_planning_context",
        # Analytics v2
        "tool_get_muscle_group_progress",
        "tool_get_muscle_progress",
        "tool_get_exercise_progress",
        "tool_query_training_sets",
        # Pre-computed analysis (consolidated)
        "tool_get_training_analysis",
        # Write tools
        "tool_propose_workout",
        "tool_propose_routine",
        "tool_update_routine",
        "tool_update_template",
    }

    DELETED_TOOLS = {
        "tool_get_coaching_context",
        "tool_get_recent_insights",
        "tool_get_daily_brief",
        "tool_get_latest_weekly_review",
        "tool_get_analytics_features",
        "tool_get_recent_workouts",
    }

    def _get_tool_names(self):
        from app.shell.tools import all_tools
        return {t.func.__name__ for t in all_tools}

    def test_expected_tools_registered(self):
        names = self._get_tool_names()
        missing = self.EXPECTED_TOOLS - names
        assert not missing, f"Missing tools: {missing}"

    def test_deleted_tools_not_registered(self):
        names = self._get_tool_names()
        present = self.DELETED_TOOLS & names
        assert not present, f"Dead tools still registered: {present}"

    def test_training_analysis_tool_has_sections_param(self):
        from app.shell.tools import tool_get_training_analysis
        import inspect
        sig = inspect.signature(tool_get_training_analysis)
        assert "sections" in sig.parameters

    def test_training_analysis_tool_docstring_has_schema(self):
        from app.shell.tools import tool_get_training_analysis
        doc = tool_get_training_analysis.__doc__
        assert doc is not None
        # Verify key schema details are in docstring (LLM reads these)
        assert "insights" in doc
        assert "weekly_review" in doc
        assert "progression_candidates" in doc
        assert "stalled_exercises" in doc
        # daily_brief was removed
        assert "daily_brief" not in doc

    def test_tool_count(self):
        names = self._get_tool_names()
        assert len(names) == len(self.EXPECTED_TOOLS), (
            f"Expected {len(self.EXPECTED_TOOLS)} tools, got {len(names)}: {names}"
        )


# ============================================================================
# 3. SKILL IMPORTS
# ============================================================================

class TestSkillImports:
    """Verify skill functions are importable and have correct signatures."""

    def test_get_training_analysis_importable(self):
        from app.skills.coach_skills import get_training_analysis
        assert callable(get_training_analysis)

    def test_get_training_analysis_signature(self):
        import inspect
        from app.skills.coach_skills import get_training_analysis
        sig = inspect.signature(get_training_analysis)
        params = set(sig.parameters.keys())
        assert "user_id" in params
        assert "sections" in params
        assert "limit" in params
        assert "client" in params
        # date parameter was removed (only used for daily_brief)
        assert "date" not in params

    def test_deleted_skills_not_importable(self):
        import importlib
        mod = importlib.import_module("app.skills.coach_skills")
        assert not hasattr(mod, "get_analytics_features")
        assert not hasattr(mod, "get_recent_workouts")
        assert not hasattr(mod, "get_coaching_context")
        assert not hasattr(mod, "get_recent_insights")
        assert not hasattr(mod, "get_daily_brief")
        assert not hasattr(mod, "get_latest_weekly_review")

    def test_skills_init_exports(self):
        from app.skills import __all__ as skills_all
        assert "get_training_analysis" in skills_all
        assert "get_coaching_context" not in skills_all

    def test_coach_skills_all_exports(self):
        from app.skills.coach_skills import __all__ as coach_all
        assert "get_training_analysis" in coach_all
        assert "get_coaching_context" not in coach_all
        assert "get_analytics_features" not in coach_all
        assert "get_recent_workouts" not in coach_all


# ============================================================================
# 4. ROUTING (no LLM needed)
# ============================================================================

class TestRouting:
    """Verify the router classifies messages into correct lanes."""

    def test_fast_lane_done(self):
        from app.shell.router import route_message, Lane
        result = route_message("done")
        assert result.lane == Lane.FAST

    def test_fast_lane_next_set(self):
        from app.shell.router import route_message, Lane
        result = route_message("next set")
        assert result.lane == Lane.FAST

    def test_slow_lane_progress_question(self):
        from app.shell.router import route_message, Lane
        result = route_message("How is my chest developing?")
        assert result.lane == Lane.SLOW

    def test_slow_lane_routine_creation(self):
        from app.shell.router import route_message, Lane
        result = route_message("Create a push pull legs routine")
        assert result.lane == Lane.SLOW

    def test_functional_lane_json_intent(self):
        from app.shell.router import route_request, Lane
        # Functional lane uses route_request (not route_message) with dict payloads
        result = route_request({"intent": "SWAP_EXERCISE", "exercise_id": "abc"})
        assert result.lane == Lane.FUNCTIONAL


# ============================================================================
# 5. PLANNER (no LLM needed)
# ============================================================================

class TestPlanner:
    """Verify planner generates correct plans for known intents."""

    def test_analyze_progress_plan(self):
        from app.shell.planner import generate_plan, PLANNING_TEMPLATES
        from app.shell.router import RoutingResult, Lane

        routing = RoutingResult(lane=Lane.SLOW, intent="ANALYZE_PROGRESS")
        plan = generate_plan(routing, "How am I doing?")

        assert plan.intent == "ANALYZE_PROGRESS"
        assert not plan.skip_planning
        assert any("training_analysis" in t for t in plan.suggested_tools)

    def test_analyze_progress_no_coaching_context_ref(self):
        from app.shell.planner import PLANNING_TEMPLATES
        template = PLANNING_TEMPLATES["ANALYZE_PROGRESS"]
        tools_str = " ".join(template["suggested_tools"])
        rationale = template["rationale"]
        assert "coaching_context" not in tools_str
        assert "coaching_context" not in rationale

    def test_should_generate_plan_fast_lane(self):
        from app.shell.planner import should_generate_plan
        from app.shell.router import RoutingResult, Lane
        routing = RoutingResult(lane=Lane.FAST, intent="LOG_SET")
        assert not should_generate_plan(routing)

    def test_should_generate_plan_slow_lane_known_intent(self):
        from app.shell.planner import should_generate_plan
        from app.shell.router import RoutingResult, Lane
        routing = RoutingResult(lane=Lane.SLOW, intent="ANALYZE_PROGRESS")
        assert should_generate_plan(routing)


# ============================================================================
# 6. CLIENT METHOD
# ============================================================================

class TestClientMethod:
    """Verify the client method exists and has correct params."""

    def test_get_analysis_summary_exists(self):
        from app.libs.tools_canvas.client import CanvasFunctionsClient
        assert hasattr(CanvasFunctionsClient, "get_analysis_summary")

    def test_get_analysis_summary_signature(self):
        import inspect
        from app.libs.tools_canvas.client import CanvasFunctionsClient
        sig = inspect.signature(CanvasFunctionsClient.get_analysis_summary)
        params = set(sig.parameters.keys())
        assert "user_id" in params
        assert "sections" in params
        assert "limit" in params
        # date parameter was removed (only used for daily_brief)
        assert "date" not in params

    def test_deleted_client_methods(self):
        from app.libs.tools_canvas.client import CanvasFunctionsClient
        assert not hasattr(CanvasFunctionsClient, "get_analytics_features")
        assert not hasattr(CanvasFunctionsClient, "get_coaching_pack")
        assert not hasattr(CanvasFunctionsClient, "get_exercise_series")
