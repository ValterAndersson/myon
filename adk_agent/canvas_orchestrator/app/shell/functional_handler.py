"""
Functional Handler - Smart Button logic using Gemini Flash.

Lane 3: Functional Lane
- Input: JSON payload with intent and data
- Model: gemini-2.5-flash (temperature=0)
- Output: Structured JSON (no chat text)

This handler processes UI-initiated actions that require AI reasoning
but don't need conversational output. Examples:
- SWAP_EXERCISE: Find alternative exercise matching constraints
- AUTOFILL_SET: Predict values for next set
- MONITOR_STATE: Silent observer for workout progress
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.shell.context import SessionContext
from app.skills.coach_skills import search_exercises, get_exercise_progress

logger = logging.getLogger(__name__)

# Model configuration
FUNCTIONAL_MODEL = os.getenv("CANVAS_FUNCTIONAL_MODEL", "gemini-2.5-flash")
FUNCTIONAL_TEMPERATURE = 0.0

# System instruction for JSON-only output
FUNCTIONAL_INSTRUCTION = """You are a logic engine for a fitness app.
You process structured requests and output ONLY valid JSON.
No chat text. No explanations. No markdown.

Output format: {"action": "...", "data": {...}}

If you cannot complete the request, output: {"action": "ERROR", "data": {"message": "..."}}
"""


@dataclass
class FunctionalResult:
    """Result from functional handler."""
    success: bool
    action: str
    data: Dict[str, Any]
    intent: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "data": self.data,
            "intent": self.intent,
        }


class FunctionalHandler:
    """
    Handler for Functional Lane requests.
    
    Uses gemini-2.5-flash with temperature=0 for deterministic JSON output.
    """
    
    def __init__(self):
        self._client = None
    
    @property
    def client(self):
        """
        Lazy-load Gemini client.
        
        Uses Vertex AI (ADC) for GCP deployments, falls back to genai for local dev.
        """
        if self._client is None:
            # Try Vertex AI first (for Cloud Run / GCP environment)
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel, GenerationConfig
                
                # Initialize with ADC (Application Default Credentials)
                project = os.getenv("GOOGLE_PROJECT") or os.getenv("GCP_PROJECT")
                location = os.getenv("GOOGLE_LOCATION", "us-central1")
                if project:
                    vertexai.init(project=project, location=location)
                else:
                    vertexai.init()  # Uses default project from ADC
                
                self._client = GenerativeModel(
                    FUNCTIONAL_MODEL,
                    system_instruction=FUNCTIONAL_INSTRUCTION,
                    generation_config=GenerationConfig(
                        temperature=FUNCTIONAL_TEMPERATURE,
                        response_mime_type="application/json",
                    ),
                )
                logger.info("FunctionalHandler using Vertex AI (ADC)")
                
            except Exception as vertex_err:
                # Fallback to google-generativeai for local development
                logger.warning("Vertex AI init failed (%s), falling back to genai", vertex_err)
                try:
                    import google.generativeai as genai
                    
                    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                    if api_key:
                        genai.configure(api_key=api_key)
                    else:
                        genai.configure()  # Try without explicit key
                    
                    self._client = genai.GenerativeModel(
                        FUNCTIONAL_MODEL,
                        system_instruction=FUNCTIONAL_INSTRUCTION,
                        generation_config={
                            "temperature": FUNCTIONAL_TEMPERATURE,
                            "response_mime_type": "application/json",
                        },
                    )
                    logger.info("FunctionalHandler using google-generativeai (API key)")
                except Exception as e:
                    logger.error("Failed to initialize Gemini client: %s", e)
                    raise
        return self._client
    
    async def handle(
        self, 
        intent: str, 
        payload: Dict[str, Any], 
        ctx: SessionContext
    ) -> FunctionalResult:
        """
        Route intent to appropriate handler.
        
        Args:
            intent: The functional intent (SWAP_EXERCISE, MONITOR_STATE, etc.)
            payload: The full JSON payload from the client
            ctx: Session context
            
        Returns:
            FunctionalResult with action and data
        """
        handlers = {
            "SWAP_EXERCISE": self._handle_swap_exercise,
            "AUTOFILL_SET": self._handle_autofill_set,
            "SUGGEST_WEIGHT": self._handle_suggest_weight,
            "MONITOR_STATE": self._handle_monitor_state,
        }
        
        handler = handlers.get(intent)
        if not handler:
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": f"Unknown intent: {intent}"},
                intent=intent,
            )
        
        try:
            return await handler(payload, ctx)
        except Exception as e:
            logger.error("Functional handler error for %s: %s", intent, e)
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": str(e)},
                intent=intent,
            )
    
    def _track_usage(self, response, feature: str, ctx: SessionContext) -> None:
        """Track LLM usage from a generate_content response (fire-and-forget)."""
        try:
            from shared.usage_tracker import extract_usage_from_vertex_response, track_usage
            usage = extract_usage_from_vertex_response(response)
            if usage.get("total_tokens"):
                track_usage(
                    user_id=ctx.user_id,
                    category="user_initiated",
                    system="canvas_orchestrator",
                    feature=feature,
                    model=FUNCTIONAL_MODEL,
                    **usage,
                )
        except Exception as e:
            logger.debug("Usage tracking error (non-fatal): %s", e)

    async def _handle_swap_exercise(
        self, 
        payload: Dict[str, Any], 
        ctx: SessionContext
    ) -> FunctionalResult:
        """
        Handle SWAP_EXERCISE intent.
        
        Finds alternative exercise matching the constraint (e.g., "machine").
        Uses search_exercises skill + Flash to pick best match.
        
        Payload:
            target: Exercise name to replace (e.g., "Barbell Bench Press")
            target_id: Exercise ID (optional)
            constraint: Filter constraint (e.g., "machine", "dumbbell")
            muscle_group: Primary muscle (e.g., "chest")
        """
        target = payload.get("target", "")
        constraint = payload.get("constraint", "")
        muscle_group = payload.get("muscle_group", "")
        
        if not target:
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": "Missing target exercise"},
                intent="SWAP_EXERCISE",
            )
        
        # 1. Search for alternatives using pure skill
        search_result = search_exercises(
            muscle_group=muscle_group or None,
            equipment=constraint or None,
            limit=10,
        )
        
        if not search_result.success or not search_result.data.get("items"):
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": "No alternatives found"},
                intent="SWAP_EXERCISE",
            )
        
        alternatives = search_result.data.get("items", [])
        
        # 2. Use Flash to select best match
        prompt = f"""Select the best alternative to replace "{target}".
Constraint: {constraint or 'any equipment'}
Target muscle: {muscle_group or 'same as original'}

Available alternatives:
{json.dumps(alternatives, indent=2)}

Select ONE exercise. Output:
{{"action": "REPLACE_EXERCISE", "data": {{"old_exercise": "{target}", "new_exercise": {{...}}}}}}
"""
        
        try:
            response = self.client.generate_content(prompt)
            result = json.loads(response.text)

            self._track_usage(response, "functional", ctx)

            return FunctionalResult(
                success=True,
                action=result.get("action", "REPLACE_EXERCISE"),
                data=result.get("data", {}),
                intent="SWAP_EXERCISE",
            )
        except Exception as e:
            logger.error("Flash call failed: %s", e)
            # Fallback: Return first alternative
            return FunctionalResult(
                success=True,
                action="REPLACE_EXERCISE",
                data={
                    "old_exercise": target,
                    "new_exercise": alternatives[0],
                    "fallback": True,
                },
                intent="SWAP_EXERCISE",
            )
    
    async def _handle_autofill_set(
        self, 
        payload: Dict[str, Any], 
        ctx: SessionContext
    ) -> FunctionalResult:
        """
        Handle AUTOFILL_SET intent.
        
        Predicts values for the next set based on history and targets.
        
        Payload:
            exercise_id: Exercise being performed
            set_index: Which set (0-based)
            target_reps: Planned reps
            last_weight: Weight from previous set (optional)
        """
        exercise_id = payload.get("exercise_id", "")
        set_index = payload.get("set_index", 0)
        target_reps = payload.get("target_reps", 8)
        last_weight = payload.get("last_weight")
        
        # Simple autofill logic (can be enhanced with analytics)
        if last_weight:
            # Keep same weight for subsequent sets
            predicted_weight = last_weight
        else:
            # First set: Would need history lookup
            # For now, return placeholder
            predicted_weight = None
        
        return FunctionalResult(
            success=True,
            action="AUTOFILL",
            data={
                "exercise_id": exercise_id,
                "set_index": set_index,
                "predicted_weight": predicted_weight,
                "predicted_reps": target_reps,
            },
            intent="AUTOFILL_SET",
        )
    
    async def _handle_suggest_weight(
        self, 
        payload: Dict[str, Any], 
        ctx: SessionContext
    ) -> FunctionalResult:
        """
        Handle SUGGEST_WEIGHT intent.
        
        Suggests weight based on recent performance and target RIR.
        Uses token-safe v2 get_exercise_progress.
        """
        exercise_id = payload.get("exercise_id", "")
        target_reps = payload.get("target_reps", 8)
        target_rir = payload.get("target_rir", 2)
        
        if not exercise_id:
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": "Missing exercise_id"},
                intent="SUGGEST_WEIGHT",
            )
        
        # Get exercise progress using v2 token-safe endpoint
        progress = get_exercise_progress(
            user_id=ctx.user_id,
            exercise_id=exercise_id,
            window_weeks=4,
        )
        
        if not progress.success:
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": "Could not fetch exercise history"},
                intent="SUGGEST_WEIGHT",
            )
        
        # Use Flash to calculate suggestion
        prompt = f"""Suggest weight for exercise based on recent data.
Target: {target_reps} reps @ RIR {target_rir}
Recent performance: {json.dumps(progress.data, indent=2)}

Calculate appropriate weight. Output:
{{"action": "SUGGEST", "data": {{"weight_kg": <number>, "confidence": "high/medium/low", "rationale": "..."}}}}
"""
        
        try:
            response = self.client.generate_content(prompt)
            result = json.loads(response.text)

            self._track_usage(response, "functional", ctx)

            return FunctionalResult(
                success=True,
                action=result.get("action", "SUGGEST"),
                data=result.get("data", {}),
                intent="SUGGEST_WEIGHT",
            )
        except Exception as e:
            logger.error("Flash suggestion failed: %s", e)
            return FunctionalResult(
                success=False,
                action="ERROR",
                data={"message": "Could not calculate suggestion"},
                intent="SUGGEST_WEIGHT",
            )
    
    async def _handle_monitor_state(
        self, 
        payload: Dict[str, Any], 
        ctx: SessionContext
    ) -> FunctionalResult:
        """
        Handle MONITOR_STATE intent (Silent Observer).
        
        Analyzes workout state diff and decides if intervention is needed.
        Returns null data if no intervention required.
        
        Payload:
            event_type: SET_COMPLETED, WORKOUT_COMPLETED, etc.
            state_diff: Changes in workout state
            workout_state: Current full state (optional)
        """
        event_type = payload.get("event_type", "")
        state_diff = payload.get("state_diff", {})
        
        # Build analysis prompt
        prompt = f"""Analyze this workout state change. Decide if user intervention is STRICTLY necessary.

Event: {event_type}
State diff: {json.dumps(state_diff, indent=2)}

Intervention is needed ONLY for:
- Form concerns (excessive weight drop between sets)
- Fatigue signals (RIR consistently higher than planned)
- Safety concerns (too many failure sets)

If intervention needed, output:
{{"action": "NUDGE", "data": {{"message": "...", "severity": "info/warning/alert"}}}}

If NO intervention needed, output:
{{"action": "NULL", "data": null}}
"""
        
        try:
            response = self.client.generate_content(prompt)
            result = json.loads(response.text)

            self._track_usage(response, "functional", ctx)

            action = result.get("action", "NULL")
            
            if action == "NULL" or action == "NONE":
                # No intervention needed - silent success
                return FunctionalResult(
                    success=True,
                    action="NULL",
                    data=None,
                    intent="MONITOR_STATE",
                )
            
            return FunctionalResult(
                success=True,
                action=action,
                data=result.get("data", {}),
                intent="MONITOR_STATE",
            )
            
        except Exception as e:
            logger.error("Monitor analysis failed: %s", e)
            # Fail silently - don't interrupt workout
            return FunctionalResult(
                success=True,
                action="NULL",
                data=None,
                intent="MONITOR_STATE",
            )


# Singleton instance
_handler: Optional[FunctionalHandler] = None


def get_functional_handler() -> FunctionalHandler:
    """Get or create the singleton FunctionalHandler."""
    global _handler
    if _handler is None:
        _handler = FunctionalHandler()
    return _handler


async def execute_functional_lane(
    routing,
    payload: Dict[str, Any],
    ctx: SessionContext,
) -> Dict[str, Any]:
    """
    Execute a Functional Lane request.
    
    This is the main entry point called by agent_engine_app.py.
    
    Args:
        routing: RoutingResult from router
        payload: Full JSON payload
        ctx: Session context
        
    Returns:
        Dict with result, ready for response
    """
    handler = get_functional_handler()
    result = await handler.handle(routing.intent, payload, ctx)
    
    return {
        "lane": "functional",
        "intent": result.intent,
        "result": result.to_dict(),
    }


__all__ = [
    "FunctionalHandler",
    "FunctionalResult",
    "get_functional_handler",
    "execute_functional_lane",
]
