"""Main Multi-Agent Orchestrator - Entry point for the multi-agent system."""

import os
import json
import logging
import time
from typing import Dict, Any, List, Optional, AsyncIterator
from dataclasses import dataclass
import asyncio

from google.adk import Agent
from google.adk.tools import FunctionTool

# Import all agents
from .agents.intent_extractor import intent_extractor_agent, tool_classify_intent
from .agents.dynamic_orchestrator import DynamicOrchestrator, ExecutionPlan
from .agents.profile_agent import profile_agent
from .agents.exercise_selector import exercise_selector_agent
from .agents.card_formatter import card_formatter
from .agents.clarification_agent import clarification_agent

# Import canvas tools
from .libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)

@dataclass
class StreamEvent:
    """Structured stream event for UI consumption."""
    type: str  # status, thinking, tool, card, error
    agent: str
    content: Any
    timestamp: float = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "agent": self.agent,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata or {}
        }

class MultiAgentOrchestrator:
    """
    Main orchestrator that coordinates all agents and manages streaming.
    
    This is the entry point that:
    1. Receives user input
    2. Extracts intent
    3. Creates execution plan
    4. Coordinates agents
    5. Streams results
    6. Publishes cards
    """
    
    def __init__(self):
        self.orchestrator = DynamicOrchestrator(max_parallel=3)
        self._setup_agents()
        self._stream_buffer = []
        self.canvas_client = self._create_canvas_client()
    
    def _create_canvas_client(self) -> CanvasFunctionsClient:
        """Create canvas client for publishing cards."""
        base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
        api_key = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
        
        return CanvasFunctionsClient(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=30
        )
    
    def _setup_agents(self):
        """Register all agents with the orchestrator."""
        # Deterministic agents
        self.orchestrator.register_agent("ProfileAgent", profile_agent)
        self.orchestrator.register_agent("CardFormatter", card_formatter)
        
        # LLM agents (wrapped for execution)
        self.orchestrator.register_agent("IntentExtractor", IntentExtractorWrapper())
        self.orchestrator.register_agent("ExerciseAgent", ExerciseSelectorWrapper())
        self.orchestrator.register_agent("ClarifyAgent", ClarificationWrapper())
        
        # Set streaming callback
        self.orchestrator.set_stream_callback(self._handle_orchestrator_stream)
    
    def _handle_orchestrator_stream(self, event: Dict[str, Any]):
        """Handle stream events from orchestrator."""
        stream_event = StreamEvent(
            type="status",
            agent="orchestrator",
            content=event
        )
        self._stream_buffer.append(stream_event)
    
    async def process_request(
        self,
        message: str,
        canvas_id: str,
        user_id: str,
        correlation_id: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Process user request through the multi-agent pipeline.
        
        Yields stream events as they occur.
        """
        context = {
            "message": message,
            "canvas_id": canvas_id,
            "user_id": user_id,
            "correlation_id": correlation_id or f"corr_{int(time.time() * 1000)}"
        }
        
        # Stream: Starting
        yield StreamEvent(
            type="status",
            agent="orchestrator",
            content={"status": "starting", "message": "Processing your request..."}
        ).to_dict()
        
        # Step 1: Load profile first to avoid asking known info
        yield StreamEvent(
            type="status",
            agent="profile",
            content={"status": "loading", "message": "Loading your profile..."}
        ).to_dict()
        profile = self.orchestrator.agent_registry["ProfileAgent"].analyze_capabilities(context)
        # Merge profile-derived defaults into entities
        profile_entities = {}
        if profile and isinstance(profile, dict):
            cap = profile
            if cap.get("capacity", {}).get("days_per_week"):
                profile_entities["available_days"] = cap["capacity"]["days_per_week"]
            if cap.get("experience", {}).get("level"):
                profile_entities["experience_level"] = cap["experience"]["level"]
            if cap.get("equipment", {}).get("available"):
                profile_entities["equipment"] = cap["equipment"]["available"]
            if cap.get("goals"):
                profile_entities["goals"] = cap["goals"]

        # Step 2: Extract Intent
        yield StreamEvent(
            type="status",
            agent="intent_extractor",
            content={"status": "analyzing", "message": "Understanding what you want..."}
        ).to_dict()
        
        intent = await self._extract_intent(message, context)
        # Merge profile entities to avoid redundant clarifications
        if profile_entities:
            intent.setdefault("entities", {}).update(profile_entities)
        # Keep intent as-is (no schema envelope)
        
        yield StreamEvent(
            type="tool",
            agent="intent_extractor",
            content={"tool": "classify_intent", "result": intent}
        ).to_dict()
        
        # Step 3: Check if clarification needed
        if intent.get("requires_clarification"):
            yield StreamEvent(
                type="status",
                agent="clarification",
                content={"status": "clarifying", "message": "I need a bit more information..."}
            ).to_dict()
            
            # Generate and publish clarification card
            question_card = await self._generate_clarification(intent, context)
            yield StreamEvent(
                type="card",
                agent="clarification",
                content=question_card
            ).to_dict()
            
            # Publish to canvas
            await self._publish_cards([question_card], context)
            
            # Wait for user response via backend
            yield StreamEvent(
                type="status",
                agent="clarification",
                content={"status": "waiting", "message": "Waiting for your answer..."}
            ).to_dict()
            
            # Poll up to 10 seconds
            for _ in range(5):
                resp = self.canvas_client.check_pending_response(
                    user_id=context["user_id"],
                    canvas_id=context["canvas_id"],
                )
                if resp.get("success") and resp.get("data", {}).get("has_response"):
                    answer = resp["data"]["response"]
                    yield StreamEvent(
                        type="status",
                        agent="clarification",
                        content={"status": "received", "message": "Got your answer.", "answer": answer}
                    ).to_dict()
                    # Continue processing after response
                    break
                await asyncio.sleep(2)
            else:
                # Timed out waiting; end early
                yield StreamEvent(
                    type="status",
                    agent="clarification",
                    content={"status": "timeout", "message": "No response yet."}
                ).to_dict()
                return
        
        # Step 4: Create execution plan
        yield StreamEvent(
            type="status",
            agent="planner",
            content={"status": "planning", "message": "Planning the best approach..."}
        ).to_dict()
        
        plan = self.orchestrator.create_plan(intent)
        
        yield StreamEvent(
            type="thinking",
            agent="planner",
            content={"plan": plan.__dict__, "task_count": len(plan.tasks)}
        ).to_dict()
        
        # Step 5: Execute plan
        yield StreamEvent(
            type="status",
            agent="orchestrator",
            content={"status": "executing", "message": "Working on your request..."}
        ).to_dict()
        
        # Execute with streaming
        results = await self._execute_plan_with_streaming(plan, context)
        
        # Step 6: Format cards
        yield StreamEvent(
            type="status",
            agent="formatter",
            content={"status": "formatting", "message": "Preparing your results..."}
        ).to_dict()
        
        cards = await self._format_results_as_cards(results, intent)
        
        # Step 7: Publish cards
        yield StreamEvent(
            type="status",
            agent="publisher",
            content={"status": "publishing", "message": "Saving to canvas..."}
        ).to_dict()
        
        # Normalize before publish (ttl minutes, type names, session_plan reps)
        cards_norm = normalize_cards(cards)
        published_ids = await self._publish_cards(cards_norm, context)
        
        # Final status
        yield StreamEvent(
            type="status",
            agent="orchestrator",
            content={
                "status": "complete",
                "message": "Done!",
                "cards_published": len(published_ids),
                "duration": time.time() - context.get("start_time", time.time())
            }
        ).to_dict()
    
    async def _extract_intent(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract intent using the intent extractor."""
        # For now, use the deterministic tool directly
        # In production, this would call the LLM agent
        return tool_classify_intent(message, context)
    
    async def _generate_clarification(self, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate clarification question card."""
        # Determine what needs clarification
        ambiguities = intent.get("ambiguities", ["goal"])
        
        # Use card formatter to create the card
        question = ambiguities[0] if ambiguities else "What would you like to do?"
        
        # Map ambiguity to question with options
        questions_map = {
            "goal": ("What's your primary training goal?", 
                    ["Build strength", "Build muscle", "Lose fat", "Improve endurance", "General fitness"]),
            "muscle_groups": ("Which areas do you want to focus on?",
                            ["Upper body", "Lower body", "Full body", "Core", "Arms"]),
            "experience": ("What's your training experience?",
                         ["Beginner", "Intermediate", "Advanced"]),
            "duration": ("How long do you want to train?",
                       ["30 minutes", "45 minutes", "60 minutes", "90+ minutes"])
        }
        
        q_text, options = questions_map.get(ambiguities[0], (question, None))
        
        card = card_formatter.format_clarify_question(
            question=q_text,
            options=options,
            question_type="choice" if options else "text"
        )
        
        return card.to_dict()
    
    @observe_fn(name="orchestrator.execute_plan")
    async def _execute_plan_with_streaming(
        self,
        plan: ExecutionPlan,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute plan and stream progress."""
        # This would normally run agents in parallel
        # For now, return mock results
        
        # Simulate parallel execution
        await asyncio.sleep(0.5)
        
        # Mock results based on intent
        if plan.intent.get("primary_intent") == "create_workout":
            return {
                "exercises": [
                    {
                        "id": "bench_press",
                        "name": "Barbell Bench Press",
                        "sets": 4,
                        "reps": "8-10",
                        "primary_muscles": ["chest"],
                        "equipment": "barbell"
                    },
                    {
                        "id": "incline_db_press",
                        "name": "Incline Dumbbell Press",
                        "sets": 3,
                        "reps": "10-12",
                        "primary_muscles": ["chest"],
                        "equipment": "dumbbells"
                    },
                    {
                        "id": "overhead_press",
                        "name": "Overhead Press",
                        "sets": 3,
                        "reps": "8-10",
                        "primary_muscles": ["shoulders"],
                        "equipment": "barbell"
                    },
                    {
                        "id": "lateral_raise",
                        "name": "Lateral Raise",
                        "sets": 3,
                        "reps": "12-15",
                        "primary_muscles": ["shoulders"],
                        "equipment": "dumbbells"
                    }
                ]
            }
        
        return {}
    
    @observe_fn(name="formatter.format_cards")
    async def _format_results_as_cards(
        self,
        results: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Format execution results as cards."""
        cards = []
        
        # Add narration card
        narration = card_formatter.format_agent_narration(
            text="I've created an upper body workout focusing on chest and shoulders.",
            status="complete"
        )
        cards.append(narration.to_dict())
        
        # Add workout cards if exercises present
        if "exercises" in results:
            session_plan = card_formatter.format_session_plan(
                exercises=results["exercises"],
                title="Upper Body Focus"
            )
            cards.append(session_plan.to_dict())
            
            # Add individual exercise cards
            for i, exercise in enumerate(results["exercises"][:2]):  # Limit to first 2
                exercise_card = card_formatter.format_exercise_detail(exercise, order=i)
                cards.append(exercise_card.to_dict())
        
        return cards
    
    @observe_fn(name="publisher.publish_cards")
    async def _publish_cards(
        self,
        cards: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[str]:
        """Publish cards to canvas."""
        try:
            # Attach envelope to each card with schema metadata when enabled
            if is_enabled("guardrails"):
                corr = context.get("correlation_id")
                cards = [attach_envelope(c, schema_version="card_payload.v1", emitted_by="publisher", trace_id=corr) for c in cards]
            result = self.canvas_client.propose_cards(
                canvas_id=context["canvas_id"],
                cards=cards,
                user_id=context["user_id"],
                correlation_id=context.get("correlation_id")
            )
            
            return result.get("data", {}).get("created_card_ids", [])
        except Exception as e:
            logger.error(f"Failed to publish cards: {e}")
            return []

# Agent Wrappers for orchestrator execution
class IntentExtractorWrapper:
    """Wrapper to make intent extractor compatible with orchestrator."""
    
    def analyze_intent(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Extract intent from message."""
        message = context.get("message", "")
        return tool_classify_intent(message, context)

class ExerciseSelectorWrapper:
    """Wrapper for exercise selector agent."""
    
    def select_exercises(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Select exercises based on requirements."""
        # In production, this would call the LLM agent
        # For now, return mock data
        muscle_groups = kwargs.get("muscle_groups", ["chest", "shoulders"])
        
        return {
            "exercises": [
                {
                    "id": "bench_press",
                    "name": "Barbell Bench Press",
                    "primary_muscles": ["chest"],
                    "equipment": "barbell",
                    "sets": 4,
                    "reps": "8-10"
                }
            ],
            "total_volume": 12,
            "estimated_duration": 45
        }

class ClarificationWrapper:
    """Wrapper for clarification agent."""
    
    def generate_questions(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Generate clarification questions."""
        intent = kwargs.get("intent", {})
        ambiguities = intent.get("ambiguities", ["goal"])
        
        return {
            "question": {
                "id": "q_goal",
                "text": "What's your primary training goal?",
                "type": "single_choice",
                "options": ["Build strength", "Build muscle", "Lose fat", "General fitness"]
            },
            "follow_up_needed": len(ambiguities) > 1
        }

# Create global orchestrator instance
multi_agent_orchestrator = MultiAgentOrchestrator()
