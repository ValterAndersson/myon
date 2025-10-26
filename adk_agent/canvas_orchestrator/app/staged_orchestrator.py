"""Staged Pipeline Orchestrator - Optimized for parallel execution and background operations."""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json

logger = logging.getLogger(__name__)

class StageStatus(Enum):
    """Status of a pipeline stage."""
    PENDING = "pending"
    RUNNING = "running"
    BACKGROUND = "background"
    COMPLETE = "complete"
    FAILED = "failed"
    CACHED = "cached"

@dataclass
class StageResult:
    """Result from a stage execution."""
    stage_name: str
    status: StageStatus
    data: Any
    duration_ms: float
    cached: bool = False
    
@dataclass
class PipelineContext:
    """Shared context across all stages."""
    message: str
    canvas_id: str
    user_id: str
    correlation_id: str
    intent: Optional[Dict[str, Any]] = None
    clarification: Optional[Dict[str, Any]] = None
    cached_data: Dict[str, Any] = field(default_factory=dict)
    background_tasks: List[asyncio.Task] = field(default_factory=list)
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

class StagedOrchestrator:
    """
    Orchestrator that executes stages with intelligent parallelization.
    
    Key features:
    - Speculative execution of likely paths
    - Background data fetching during user interaction
    - Smart caching of intermediate results
    - Progressive enhancement of outputs
    """
    
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.background_executor = None
        
    async def process(
        self,
        message: str,
        canvas_id: str,
        user_id: str,
        correlation_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Process request through staged pipeline."""
        
        context = PipelineContext(
            message=message,
            canvas_id=canvas_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        # Stage 1: Understand (with background triggers)
        async for event in self._stage1_understand(context):
            yield event
        
        # Stage 2: Clarify (if needed)
        if context.intent and context.intent.get("requires_clarification"):
            async for event in self._stage2_clarify(context):
                yield event
            
            # Wait for user response (would be handled by interaction)
            # For now, simulate auto-response
            await asyncio.sleep(0.1)
            context.clarification = {"answer": "upper_body"}
        
        # Stage 3: Pre-Plan (while background jobs complete)
        async for event in self._stage3_preplan(context):
            yield event
        
        # Stage 4-6: Execute (using cached data)
        async for event in self._execute_stages(context):
            yield event
        
        # Stage 7: Present
        async for event in self._stage7_present(context):
            yield event
    
    async def _stage1_understand(self, context: PipelineContext) -> AsyncIterator[Dict[str, Any]]:
        """Stage 1: Understand intent and trigger background operations."""
        start = time.time()
        
        yield {
            "stage": "understand",
            "status": "running",
            "message": "Understanding your request..."
        }
        
        # Quick intent extraction
        context.intent = self._quick_classify(context.message)
        
        # Trigger background data fetching
        background_tasks = [
            self._fetch_user_profile(context),
            self._fetch_exercise_database(context),
            self._fetch_recent_workouts(context),
        ]
        
        for task in background_tasks:
            context.background_tasks.append(asyncio.create_task(task))
        
        duration = (time.time() - start) * 1000
        
        yield {
            "stage": "understand",
            "status": "complete",
            "intent": context.intent,
            "duration_ms": duration,
            "background_triggered": len(context.background_tasks)
        }
        
        context.stage_results["understand"] = StageResult(
            stage_name="understand",
            status=StageStatus.COMPLETE,
            data=context.intent,
            duration_ms=duration
        )
    
    async def _stage2_clarify(self, context: PipelineContext) -> AsyncIterator[Dict[str, Any]]:
        """Stage 2: Generate clarification and pre-compute paths."""
        start = time.time()
        
        yield {
            "stage": "clarify",
            "status": "running",
            "message": "I need a bit more information..."
        }
        
        # Generate clarification question
        question = self._generate_clarification(context.intent)
        
        # Speculatively compute plans for each option
        speculation_tasks = []
        for option in question.get("options", []):
            task = asyncio.create_task(
                self._speculative_plan(context, option)
            )
            speculation_tasks.append(task)
            context.background_tasks.append(task)
        
        duration = (time.time() - start) * 1000
        
        yield {
            "stage": "clarify",
            "status": "complete",
            "card": {
                "type": "clarify_questions",
                "content": question
            },
            "duration_ms": duration,
            "speculative_paths": len(speculation_tasks)
        }
        
        context.stage_results["clarify"] = StageResult(
            stage_name="clarify",
            status=StageStatus.COMPLETE,
            data=question,
            duration_ms=duration
        )
    
    async def _stage3_preplan(self, context: PipelineContext) -> AsyncIterator[Dict[str, Any]]:
        """Stage 3: Show preview while background jobs complete."""
        start = time.time()
        
        yield {
            "stage": "preplan",
            "status": "running",
            "message": "Planning your workout..."
        }
        
        # Wait for critical background tasks with timeout
        critical_tasks = context.background_tasks[:3]  # First 3 are critical
        
        try:
            done, pending = await asyncio.wait(
                critical_tasks,
                timeout=0.5,
                return_when=asyncio.ALL_COMPLETED
            )
            
            # Collect results
            for task in done:
                try:
                    result = task.result()
                    if isinstance(result, tuple) and len(result) == 2:
                        key, data = result
                        context.cached_data[key] = data
                except Exception as e:
                    logger.warning(f"Background task failed: {e}")
        
        except asyncio.TimeoutError:
            logger.info("Some background tasks still running, proceeding with available data")
        
        # Generate preview
        preview = self._generate_preview(context)
        
        duration = (time.time() - start) * 1000
        
        yield {
            "stage": "preplan",
            "status": "complete",
            "preview": preview,
            "duration_ms": duration,
            "data_ready": len(context.cached_data)
        }
        
        context.stage_results["preplan"] = StageResult(
            stage_name="preplan",
            status=StageStatus.COMPLETE,
            data=preview,
            duration_ms=duration
        )
    
    async def _execute_stages(self, context: PipelineContext) -> AsyncIterator[Dict[str, Any]]:
        """Stages 4-6: Plan, format, and execute."""
        
        # Check if we have a cached plan from speculation
        cache_key = self._get_cache_key(context)
        if cache_key in self.cache:
            cached_plan = self.cache[cache_key]
            
            yield {
                "stage": "execute",
                "status": "using_cache",
                "message": "Using optimized plan..."
            }
            
            # Use cached plan
            cards = cached_plan["cards"]
            
        else:
            # Generate fresh plan
            yield {
                "stage": "execute",
                "status": "running",
                "message": "Creating your workout..."
            }
            
            # Stage 4: Plan steps
            plan = await self._plan_workout(context)
            
            # Stage 5: Plan presentation  
            presentation = self._plan_presentation(plan)
            
            # Stage 6: Execute formatting
            cards = self._format_cards(plan, presentation)
            
            # Cache for future
            self.cache[cache_key] = {"plan": plan, "cards": cards}
        
        context.cached_data["cards"] = cards
        
        yield {
            "stage": "execute",
            "status": "complete",
            "card_count": len(cards)
        }
    
    async def _stage7_present(self, context: PipelineContext) -> AsyncIterator[Dict[str, Any]]:
        """Stage 7: Present cards to user."""
        cards = context.cached_data.get("cards", [])
        
        yield {
            "stage": "present",
            "status": "publishing",
            "message": "Saving to canvas..."
        }
        
        # Simulate publishing
        await asyncio.sleep(0.05)
        
        total_duration = (time.time() - context.start_time) * 1000
        
        yield {
            "stage": "present",
            "status": "complete",
            "cards": cards,
            "total_duration_ms": total_duration,
            "stages_completed": len(context.stage_results)
        }
    
    # Helper methods
    
    def _quick_classify(self, message: str) -> Dict[str, Any]:
        """Quick intent classification."""
        message_lower = message.lower()
        
        if "upper body" in message_lower:
            return {
                "primary_intent": "create_workout",
                "muscle_groups": ["chest", "shoulders", "arms"],
                "confidence": 0.9,
                "requires_clarification": False
            }
        elif "workout" in message_lower or "program" in message_lower:
            return {
                "primary_intent": "create_workout",
                "confidence": 0.6,
                "requires_clarification": True,
                "ambiguities": ["muscle_groups", "duration"]
            }
        else:
            return {
                "primary_intent": "unknown",
                "confidence": 0.3,
                "requires_clarification": True
            }
    
    def _generate_clarification(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate clarification question."""
        return {
            "question": "Which muscle groups would you like to focus on?",
            "options": ["Upper body", "Lower body", "Full body", "Core"],
            "type": "single_choice"
        }
    
    async def _fetch_user_profile(self, context: PipelineContext) -> Tuple[str, Dict]:
        """Fetch user profile in background."""
        await asyncio.sleep(0.1)  # Simulate API call
        return ("profile", {
            "experience": "intermediate",
            "equipment": ["barbell", "dumbbells"],
            "goals": ["strength", "muscle"]
        })
    
    async def _fetch_exercise_database(self, context: PipelineContext) -> Tuple[str, List]:
        """Fetch relevant exercises in background."""
        await asyncio.sleep(0.15)  # Simulate database query
        
        # Filter based on intent if available
        muscle_groups = context.intent.get("muscle_groups", [])
        
        exercises = [
            {"id": "bench_press", "name": "Bench Press", "muscles": ["chest"]},
            {"id": "overhead_press", "name": "Overhead Press", "muscles": ["shoulders"]},
            {"id": "pullup", "name": "Pull-up", "muscles": ["back", "biceps"]},
            {"id": "dip", "name": "Dip", "muscles": ["chest", "triceps"]},
        ]
        
        return ("exercises", exercises)
    
    async def _fetch_recent_workouts(self, context: PipelineContext) -> Tuple[str, List]:
        """Fetch recent workout history."""
        await asyncio.sleep(0.08)  # Simulate query
        return ("history", [
            {"date": "2024-01-20", "exercises": ["bench_press", "squat"]},
            {"date": "2024-01-18", "exercises": ["deadlift", "pullup"]},
        ])
    
    async def _speculative_plan(self, context: PipelineContext, option: str) -> None:
        """Pre-compute plan for a possible user choice."""
        # Generate cache key for this path
        cache_key = f"{context.correlation_id}_{option}"
        
        # Simulate planning
        await asyncio.sleep(0.2)
        
        # Create and cache plan
        plan = {
            "option": option,
            "exercises": ["bench_press", "overhead_press", "lateral_raise"],
            "cards": [
                {"type": "session_plan", "content": {"title": f"{option} Workout"}}
            ]
        }
        
        self.cache[cache_key] = plan
    
    def _generate_preview(self, context: PipelineContext) -> Dict[str, Any]:
        """Generate workout preview."""
        return {
            "title": "Upper Body Focus",
            "exercise_count": 4,
            "duration": "45 minutes",
            "intensity": "Moderate"
        }
    
    async def _plan_workout(self, context: PipelineContext) -> Dict[str, Any]:
        """Plan the workout using available data."""
        await asyncio.sleep(0.1)  # Simulate planning
        
        return {
            "exercises": [
                {"name": "Bench Press", "sets": 4, "reps": "8-10"},
                {"name": "Overhead Press", "sets": 3, "reps": "8-10"},
                {"name": "Pull-ups", "sets": 3, "reps": "6-12"},
                {"name": "Lateral Raises", "sets": 3, "reps": "12-15"},
            ]
        }
    
    def _plan_presentation(self, plan: Dict[str, Any]) -> List[str]:
        """Determine card types for presentation."""
        return ["agent_message", "session_plan", "exercise_detail"]
    
    def _format_cards(self, plan: Dict[str, Any], presentation: List[str]) -> List[Dict]:
        """Format cards for display."""
        cards = []
        
        if "agent_message" in presentation:
            cards.append({
                "type": "agent_message",
                "content": {"text": "Here's your upper body workout"}
            })
        
        if "session_plan" in presentation:
            cards.append({
                "type": "session_plan",
                "content": {
                    "title": "Upper Body Focus",
                    "exercises": plan["exercises"]
                }
            })
        
        return cards
    
    def _get_cache_key(self, context: PipelineContext) -> str:
        """Generate cache key for current context."""
        key_data = {
            "intent": context.intent,
            "clarification": context.clarification,
            "user_id": context.user_id
        }
        
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

# Global instance
staged_orchestrator = StagedOrchestrator()
