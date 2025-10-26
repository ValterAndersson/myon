"""Dynamic Orchestrator - Coordinates multi-agent execution with parallelism."""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class AgentStatus(Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class AgentTask:
    """Represents a task for an agent to execute."""
    id: str
    agent_name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

@dataclass
class ExecutionPlan:
    """Execution plan for multi-agent coordination."""
    plan_id: str
    intent: Dict[str, Any]
    tasks: List[AgentTask]
    required_cards: List[str]
    interaction_points: List[str]
    created_at: float = field(default_factory=time.time)

class DynamicOrchestrator:
    """Orchestrates multi-agent execution with dependency resolution and parallelism."""
    
    def __init__(self, max_parallel: int = 5, timeout: int = 30):
        self.max_parallel = max_parallel
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=max_parallel)
        self.agent_registry = {}
        self.stream_callback = None
        
    def register_agent(self, name: str, agent_instance: Any) -> None:
        """Register an agent for execution."""
        self.agent_registry[name] = agent_instance
        logger.info(f"Registered agent: {name}")
    
    def set_stream_callback(self, callback: callable) -> None:
        """Set callback for streaming updates."""
        self.stream_callback = callback
    
    def _emit_stream(self, message: Dict[str, Any]) -> None:
        """Emit a stream message."""
        if self.stream_callback:
            self.stream_callback({
                "type": "orchestration",
                "timestamp": time.time(),
                **message
            })
    
    def create_plan(self, intent: Dict[str, Any]) -> ExecutionPlan:
        """Create execution plan based on intent."""
        plan_id = f"plan_{int(time.time() * 1000)}"
        tasks = []
        
        # Determine required agents based on intent
        primary_intent = intent.get("primary_intent", "unknown")
        
        if primary_intent == "create_workout":
            # Parallel tasks that don't depend on each other
            tasks.extend([
                AgentTask(
                    id="t1",
                    agent_name="ProfileAgent",
                    action="analyze_capabilities",
                    params={"include_equipment": True, "include_experience": True},
                    depends_on=[]
                ),
                AgentTask(
                    id="t2", 
                    agent_name="HistoryAgent",
                    action="get_recent_workouts",
                    params={"days": 7, "include_volume": True},
                    depends_on=[]
                ),
            ])
            
            # Exercise selection depends on profile
            tasks.append(
                AgentTask(
                    id="t3",
                    agent_name="ExerciseAgent",
                    action="select_exercises",
                    params={
                        "muscle_groups": intent.get("constraints", {}).get("muscle_groups", []),
                        "count": 4
                    },
                    depends_on=["t1"]
                )
            )
            
            # Volume calculation depends on both history and exercises
            tasks.append(
                AgentTask(
                    id="t4",
                    agent_name="VolumeAgent",
                    action="calculate_volume",
                    params={"workout_type": "hypertrophy"},
                    depends_on=["t2", "t3"]
                )
            )
            
            # Card composition depends on everything
            tasks.append(
                AgentTask(
                    id="t5",
                    agent_name="CardComposer",
                    action="compose_workout_cards",
                    params={},
                    depends_on=["t3", "t4"]
                )
            )
            
            required_cards = ["session-plan", "exercise-cards"]
            interaction_points = ["accept-workout", "modify-exercise", "adjust-volume"]
            
        elif primary_intent == "analyze_progress":
            tasks.extend([
                AgentTask(
                    id="t1",
                    agent_name="HistoryAgent",
                    action="analyze_progress",
                    params={"metric": intent.get("entities", {}).get("metric", "strength")},
                    depends_on=[]
                ),
                AgentTask(
                    id="t2",
                    agent_name="CardComposer",
                    action="compose_progress_cards",
                    params={},
                    depends_on=["t1"]
                )
            ])
            
            required_cards = ["progress-chart", "insights"]
            interaction_points = ["drill-down", "change-metric"]
            
        else:
            # Unknown intent - ask for clarification
            tasks.append(
                AgentTask(
                    id="t1",
                    agent_name="ClarifyAgent",
                    action="generate_questions",
                    params={"intent": intent},
                    depends_on=[]
                )
            )
            
            required_cards = ["clarify-questions"]
            interaction_points = ["answer-question"]
        
        return ExecutionPlan(
            plan_id=plan_id,
            intent=intent,
            tasks=tasks,
            required_cards=required_cards,
            interaction_points=interaction_points
        )
    
    def _get_ready_tasks(self, plan: ExecutionPlan) -> List[AgentTask]:
        """Get tasks that are ready to execute (dependencies satisfied)."""
        completed_ids = {t.id for t in plan.tasks if t.status == AgentStatus.COMPLETED}
        ready = []
        
        for task in plan.tasks:
            if task.status == AgentStatus.PENDING:
                if all(dep in completed_ids for dep in task.depends_on):
                    ready.append(task)
        
        return ready
    
    def _execute_task(self, task: AgentTask, context: Dict[str, Any]) -> None:
        """Execute a single agent task."""
        task.status = AgentStatus.RUNNING
        task.start_time = time.time()
        
        self._emit_stream({
            "status": "task_started",
            "task_id": task.id,
            "agent": task.agent_name,
            "action": task.action
        })
        
        try:
            # Get the agent
            agent = self.agent_registry.get(task.agent_name)
            if not agent:
                raise ValueError(f"Agent {task.agent_name} not registered")
            
            # Execute the action
            if hasattr(agent, task.action):
                method = getattr(agent, task.action)
                # Pass context and params
                result = method(context=context, **task.params)
                task.result = result
                task.status = AgentStatus.COMPLETED
                
                self._emit_stream({
                    "status": "task_completed",
                    "task_id": task.id,
                    "agent": task.agent_name,
                    "duration": task.duration
                })
            else:
                raise ValueError(f"Agent {task.agent_name} has no action {task.action}")
                
        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
            logger.error(f"Task {task.id} failed: {e}")
            
            self._emit_stream({
                "status": "task_failed",
                "task_id": task.id,
                "agent": task.agent_name,
                "error": str(e)
            })
        finally:
            task.end_time = time.time()
    
    def execute_plan(self, plan: ExecutionPlan, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute plan with parallel optimization."""
        start_time = time.time()
        
        self._emit_stream({
            "status": "plan_started",
            "plan_id": plan.plan_id,
            "total_tasks": len(plan.tasks)
        })
        
        # Build context with results
        execution_context = {**context, "results": {}}
        
        # Execute tasks with dependency resolution
        futures = {}
        while True:
            # Get ready tasks
            ready_tasks = self._get_ready_tasks(plan)
            
            if not ready_tasks and not futures:
                # No more tasks to execute
                break
            
            # Submit ready tasks (up to max_parallel)
            for task in ready_tasks[:self.max_parallel - len(futures)]:
                future = self.executor.submit(self._execute_task, task, execution_context)
                futures[future] = task
                
                self._emit_stream({
                    "status": "task_queued",
                    "task_id": task.id,
                    "parallel_count": len(futures)
                })
            
            # Wait for at least one task to complete
            if futures:
                done, pending = asyncio.run(
                    asyncio.wait(futures.keys(), return_when=asyncio.FIRST_COMPLETED, timeout=1)
                )
                
                for future in done:
                    task = futures.pop(future)
                    if task.status == AgentStatus.COMPLETED:
                        # Add result to context for dependent tasks
                        execution_context["results"][task.id] = task.result
                    
                    self._emit_stream({
                        "status": "task_done",
                        "task_id": task.id,
                        "remaining": len([t for t in plan.tasks if t.status == AgentStatus.PENDING])
                    })
        
        # Compile final results
        duration = time.time() - start_time
        results = {
            "plan_id": plan.plan_id,
            "duration": duration,
            "tasks_completed": len([t for t in plan.tasks if t.status == AgentStatus.COMPLETED]),
            "tasks_failed": len([t for t in plan.tasks if t.status == AgentStatus.FAILED]),
            "results": execution_context["results"],
            "required_cards": plan.required_cards,
            "interaction_points": plan.interaction_points
        }
        
        self._emit_stream({
            "status": "plan_completed",
            "plan_id": plan.plan_id,
            "duration": duration
        })
        
        return results

# Global orchestrator instance
orchestrator = DynamicOrchestrator(max_parallel=5, timeout=30)
