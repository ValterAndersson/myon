"""
Catalog Orchestrator Agent
Central coordinator for the multi-agent catalog curation system.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# from vertexai import agent_engines  # Not needed with LLM-based agents
# Use standalone Firebase client to avoid app/__init__.py imports
from utils.firebase_client import FirebaseFunctionsClient


class TaskStatus(Enum):
    """Status of a task in the system"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class AgentType(Enum):
    """Types of worker agents in the system"""
    TRIAGE = "triage"  # Normalizes exercises (family/variant assignment)
    ENRICHMENT = "enrichment"  # Adds aliases
    JANITOR = "janitor"  # Deduplicates within families
    SCOUT = "scout"  # Finds gaps from search logs
    ANALYST = "analyst"  # Analyzes exercise quality
    AUDITOR = "auditor"  # Weekly quality audits
    APPROVAL = "approval"  # Approves production-ready exercises
    CREATOR = "creator"  # Creates new exercises from gaps
    BIOMECHANICS = "biomechanics"  # Improves movement patterns
    ANATOMY = "anatomy"  # Improves muscle mappings
    CONTENT = "content"  # Improves descriptions and instructions
    PROGRAMMING = "programming"  # Improves programming context


@dataclass
class Task:
    """Represents a unit of work for an agent"""
    id: str
    agent_type: AgentType
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class BatchJob:
    """Represents a batch of related tasks"""
    id: str
    tasks: List[Task]
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    @property
    def is_complete(self) -> bool:
        return all(t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] for t in self.tasks)
    
    @property
    def progress(self) -> Tuple[int, int]:
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        return completed, len(self.tasks)


class CatalogOrchestrator:
    """
    Main orchestrator that coordinates all catalog curation agents.
    """
    
    def __init__(self, 
                 firebase_base_url: str,
                 firebase_api_key: str,
                 max_parallel_workers: int = 3,
                 log_dir: str = "logs",
                 system_user_id: str = "orchestrator"):
        
        self.firebase_client = FirebaseFunctionsClient(
            base_url=firebase_base_url,
            api_key=firebase_api_key,
            user_id=system_user_id
        )
        self.system_user_id = system_user_id  # Lazy load
        
        self.max_parallel_workers = max_parallel_workers
        self.executor = ThreadPoolExecutor(max_workers=max_parallel_workers)
        
        # Setup logging
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.setup_logging()
        
        # State management
        self.active_jobs: Dict[str, BatchJob] = {}
        self.task_queue: List[Task] = []
        
    def setup_logging(self):
        """Configure logging for the orchestrator"""
        log_file = os.path.join(self.log_dir, f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("CatalogOrchestrator")
        
    # Removed get_catalog_admin_agent - using LLM-based agents directly
        
    def assess_catalog_state(self) -> Dict[str, Any]:
        """
        Query the catalog to understand its current state.
        Returns metrics about what needs to be processed.
        """
        self.logger.info("Assessing catalog state...")
        
        state = {
            "timestamp": datetime.now().isoformat(),
            "exercises": {
                "total": 0,
                "unnormalized": 0,
                "unapproved": 0,
                "without_aliases": 0
            },
            "families": {
                "total": 0,
                "needs_dedup": []
            }
        }
        
        try:
            # Get all exercises
            exercises_response = self.firebase_client.get("getExercises", params={"limit": 1000})
            
            # Handle the response structure
            if exercises_response.get("success") and exercises_response.get("data"):
                all_exercises = exercises_response["data"].get("items", [])
            else:
                all_exercises = exercises_response.get("exercises", [])
            
            state["exercises"]["total"] = len(all_exercises)
            
            # Analyze exercises
            for ex in all_exercises:
                if not ex.get("family_slug"):
                    state["exercises"]["unnormalized"] += 1
                if not ex.get("approved"):
                    state["exercises"]["unapproved"] += 1
                # Check if exercise has aliases (would need to query aliases separately)
                
            # Get families for dedup analysis
            families_response = self.firebase_client.list_families(minSize=2)
            if families_response.get("success") and families_response.get("data"):
                families_list = families_response["data"].get("families", [])
            else:
                families_list = families_response.get("families", [])
            state["families"]["total"] = len(families_list)
            
            self.logger.info(f"Catalog state: {json.dumps(state, indent=2)}")
            
        except Exception as e:
            self.logger.error(f"Failed to assess catalog state: {e}")
            
        return state
    
    def create_batch_job(self, agent_type: AgentType, items: List[Dict[str, Any]], 
                        batch_size: int = 10) -> BatchJob:
        """
        Create a batch job with tasks for a specific agent type.
        Splits items into manageable batches.
        """
        job_id = f"{agent_type.value}_{int(time.time())}"
        tasks = []
        
        # Split items into batches
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            task = Task(
                id=f"{job_id}_task_{i//batch_size}",
                agent_type=agent_type,
                payload={"items": batch}
            )
            tasks.append(task)
            
        job = BatchJob(id=job_id, tasks=tasks)
        self.active_jobs[job_id] = job
        
        self.logger.info(f"Created batch job {job_id} with {len(tasks)} tasks")
        return job
    
    def execute_task(self, task: Task) -> Task:
        """
        Execute a single task by delegating to the appropriate agent.
        """
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        
        try:
            self.logger.info(f"Executing task {task.id} of type {task.agent_type.value}")
            
            if task.agent_type == AgentType.TRIAGE:
                result = self.run_triage_agent(task.payload)
            elif task.agent_type == AgentType.ENRICHMENT:
                result = self.run_enrichment_agent(task.payload)
            elif task.agent_type == AgentType.JANITOR:
                result = self.run_janitor_agent(task.payload)
            elif task.agent_type == AgentType.SCOUT:
                result = self.run_scout_agent(task.payload)
            elif task.agent_type == AgentType.ANALYST:
                result = self.run_analyst_agent(task.payload)
            elif task.agent_type == AgentType.CREATOR:
                result = self.run_specialist_agent(task.payload, "creator")
            elif task.agent_type == AgentType.BIOMECHANICS:
                result = self.run_specialist_agent(task.payload, "biomechanics")
            elif task.agent_type == AgentType.ANATOMY:
                result = self.run_specialist_agent(task.payload, "anatomy")
            elif task.agent_type == AgentType.CONTENT:
                result = self.run_specialist_agent(task.payload, "content")
            elif task.agent_type == AgentType.PROGRAMMING:
                result = self.run_specialist_agent(task.payload, "programming")
            else:
                raise NotImplementedError(f"Agent type {task.agent_type} not implemented yet")
                
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now()
            
            self.logger.info(f"Task {task.id} completed successfully")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.RETRY
                task.retry_count += 1
                self.logger.warning(f"Task {task.id} failed, will retry ({task.retry_count}/{task.max_retries}): {e}")
            else:
                self.logger.error(f"Task {task.id} failed after {task.max_retries} retries: {e}")
                
        return task
    
    def run_triage_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the triage agent to normalize exercises.
        This assigns family_slug and variant_key to exercises.
        """
        # Import here to avoid circular dependencies
        from agents.triage_agent import TriageAgent
        
        triage = TriageAgent(self.firebase_client)
        
        # Get exercises to normalize
        items = payload.get("items", [])
        
        # Process the exercises
        result = triage.process_batch(items)
        
        self.logger.info(f"Triage normalized {result.get('exercises_normalized', 0)} exercises")
        
        return result
    
    def run_enrichment_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the LLM-powered enrichment agent to add aliases to exercises.
        """
        # Import here to avoid circular dependencies
        from agents.enrichment_agent import EnrichmentAgent
        
        enrichment = EnrichmentAgent(self.firebase_client)
        
        # Get exercises to enrich
        items = payload.get("items", [])
        
        # Process the exercises
        result = enrichment.process_batch(items)
        
        self.logger.info(f"Enrichment added {result.get('total_aliases_added', 0)} aliases")
        
        return result
    
    def run_janitor_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the janitor agent to deduplicate exercises within families.
        """
        families = payload.get("families", [])
        results = {"processed": 0, "merged": 0, "failed": 0}
        
        for family_slug in families:
            try:
                # Run normalization for the family
                result = self.firebase_client.post("backfillNormalizeFamily", {
                    "family": family_slug,
                    "apply": True
                })
                
                results["processed"] += 1
                if result.get("ok"):
                    merges = result.get("data", {}).get("merges", [])
                    results["merged"] += len(merges)
                    
            except Exception as e:
                self.logger.error(f"Failed to process family {family_slug}: {e}")
                results["failed"] += 1
                
        return results
    
    def run_scout_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the scout agent to find gaps in the catalog from search patterns.
        """
        # Import here to avoid circular dependencies
        from agents.scout_agent import ScoutAgent
        
        scout = ScoutAgent(self.firebase_client)
        
        # Get search logs (in production, this would come from a logging service)
        search_logs = payload.get("search_logs")
        
        # If no logs provided, generate mock data for testing
        if search_logs is None or (isinstance(search_logs, list) and len(search_logs) == 0):
            self.logger.info("No search logs provided, using mock data for testing")
            search_logs = self._generate_mock_search_logs()
        else:
            self.logger.info(f"Processing {len(search_logs)} provided search logs")
        
        # Process the logs
        result = scout.process_batch(
            search_logs, 
            create_drafts=payload.get("create_drafts", False)
        )
        
        self.logger.info(f"Scout found {result.get('gaps_identified', 0)} gaps, created {result.get('drafts_created', 0)} drafts")
        
        return result
    
    def run_analyst_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the analyst agent to analyze exercise quality.
        """
        # Import here to avoid circular dependencies
        from agents.analyst_agent import AnalystAgent
        
        analyst = AnalystAgent(self.firebase_client)
        
        # Get exercises to analyze
        items = payload.get("items", [])
        
        if not items:
            # If no specific exercises provided, analyze a sample
            exercises_response = self.firebase_client.get("getExercises", params={"limit": 20})
            if exercises_response.get("success") and exercises_response.get("data"):
                items = exercises_response["data"].get("items", [])
            else:
                items = exercises_response.get("exercises", [])
        
        self.logger.debug(f"Analyst received {len(items)} items to analyze")
        self.logger.debug(f"First item type: {type(items[0]) if items else 'No items'}")
        
        # Analyze the batch
        result = analyst.process_batch(items)
        
        self.logger.info(f"Analyst examined {result['exercises_analyzed']} exercises, "
                        f"found {result['total_issues']} issues")
        
        return result
    
    def _generate_mock_search_logs(self) -> List[Dict[str, Any]]:
        """
        Generate mock search logs for testing the scout agent.
        """
        from datetime import datetime, timedelta
        import random
        
        # Common search patterns that might indicate gaps
        patterns = [
            ("zercher squat", 5),
            ("landmine press", 4),
            ("face pulls", 6),
            ("viking press", 3),
            ("jefferson deadlift", 3),
            ("dumbbell pullover", 4),
            ("cable crossover", 5),
            ("sissy squat", 3),
            ("hack squat", 4),
            ("pendlay row", 3)
        ]
        
        logs = []
        base_time = datetime.now() - timedelta(hours=12)
        
        for query, frequency in patterns:
            for i in range(frequency):
                logs.append({
                    "query": query,
                    "timestamp": base_time + timedelta(minutes=random.randint(0, 720)),
                    "confidence": random.uniform(0.1, 0.6),  # Low confidence indicates no good match
                    "failed": random.choice([True, False])
                })
        
        return logs
    
    def execute_batch_job(self, job: BatchJob, parallel: bool = True) -> BatchJob:
        """
        Execute all tasks in a batch job.
        Can run tasks in parallel or sequentially.
        """
        self.logger.info(f"Executing batch job {job.id} with {len(job.tasks)} tasks (parallel={parallel})")
        
        if parallel:
            # Submit all tasks to executor
            futures = {self.executor.submit(self.execute_task, task): task for task in job.tasks}
            
            # Wait for completion
            for future in as_completed(futures):
                task = futures[future]
                try:
                    completed_task = future.result()
                    # Update task in job
                    for i, t in enumerate(job.tasks):
                        if t.id == completed_task.id:
                            job.tasks[i] = completed_task
                            break
                except Exception as e:
                    self.logger.error(f"Task execution failed: {e}")
        else:
            # Execute tasks sequentially
            for i, task in enumerate(job.tasks):
                job.tasks[i] = self.execute_task(task)
                
        job.completed_at = datetime.now()
        self.logger.info(f"Batch job {job.id} completed. Progress: {job.progress[0]}/{job.progress[1]}")
        
        return job
    
    def run_pipeline(self, pipeline_config: Dict[str, Any] = None):
        """
        Run the full pipeline based on current catalog state.
        """
        self.logger.info("=" * 50)
        self.logger.info("Starting catalog curation pipeline")
        self.logger.info("=" * 50)
        
        # Assess current state
        state = self.assess_catalog_state()
        
        # Phase 1: Triage unnormalized exercises
        if state["exercises"]["unnormalized"] > 0:
            self.logger.info(f"Found {state['exercises']['unnormalized']} unnormalized exercises")
            
            # Get unnormalized exercises
            exercises_response = self.firebase_client.get("getExercises", params={"limit": 1000})
            if exercises_response.get("success") and exercises_response.get("data"):
                all_exercises = exercises_response["data"].get("items", [])
            else:
                all_exercises = exercises_response.get("exercises", [])
            unnormalized = [ex for ex in all_exercises if not ex.get("family_slug")]
            
            if unnormalized:
                job = self.create_batch_job(AgentType.TRIAGE, unnormalized, batch_size=5)
                self.execute_batch_job(job, parallel=True)
                
        # Phase 2: Enrich exercises without aliases
        if state["exercises"]["total"] > 0:
            self.logger.info("Checking for exercises needing aliases...")
            
            # Get exercises that might need aliases (simplified - you'd check actual aliases)
            exercises_response = self.firebase_client.get("getExercises", params={"limit": 100})
            if exercises_response.get("success") and exercises_response.get("data"):
                all_exercises = exercises_response["data"].get("items", [])
            else:
                all_exercises = exercises_response.get("exercises", [])
            approved_exercises = [ex for ex in all_exercises 
                                 if ex.get("approved") and ex.get("family_slug")][:10]  # Limit for testing
            
            if approved_exercises:
                job = self.create_batch_job(AgentType.ENRICHMENT, approved_exercises, batch_size=5)
                self.execute_batch_job(job, parallel=True)
                
        # Phase 3: Deduplicate families (run less frequently)
        # This would typically be scheduled weekly
        
        self.logger.info("Pipeline execution completed")
        self.generate_summary_report()
        
    def generate_summary_report(self) -> Dict[str, Any]:
        """
        Generate a summary report of all completed jobs.
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "jobs_completed": len([j for j in self.active_jobs.values() if j.is_complete]),
            "jobs_in_progress": len([j for j in self.active_jobs.values() if not j.is_complete]),
            "tasks_by_status": {},
            "tasks_by_agent": {}
        }
        
        for job in self.active_jobs.values():
            for task in job.tasks:
                # Count by status
                status = task.status.value
                report["tasks_by_status"][status] = report["tasks_by_status"].get(status, 0) + 1
                
                # Count by agent type
                agent = task.agent_type.value
                report["tasks_by_agent"][agent] = report["tasks_by_agent"].get(agent, 0) + 1
                
        self.logger.info(f"Summary Report: {json.dumps(report, indent=2)}")
        
        # Save report to file
        report_file = os.path.join(self.log_dir, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
            
        return report
    
    def run_specialist_agent(self, payload: Dict[str, Any], role: str) -> Dict[str, Any]:
        """
        Run a specialist agent with a specific role.
        """
        # Import here to avoid circular dependencies
        from agents.specialist_agent import SpecialistAgent, SpecialistRole
        
        # Map role string to enum
        role_map = {
            "creator": SpecialistRole.CREATOR,
            "biomechanics": SpecialistRole.BIOMECHANICS,
            "anatomy": SpecialistRole.ANATOMY,
            "content": SpecialistRole.CONTENT,
            "programming": SpecialistRole.PROGRAMMING
        }
        
        specialist_role = role_map.get(role)
        if not specialist_role:
            raise ValueError(f"Unknown specialist role: {role}")
        
        specialist = SpecialistAgent(self.firebase_client, specialist_role)
        
        # Get items to process - handle both list and dict with items key
        items = payload.get("items", [])
        if not items and isinstance(payload, list):
            items = payload
        task_description = payload.get("task_description", "")
        
        # Process the items
        result = specialist.process_batch(items, task_description)
        
        self.logger.info(f"Specialist ({role}) processed {len(items)} items")
        
        return result


if __name__ == "__main__":
    # Configuration
    FIREBASE_BASE_URL = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")
    CATALOG_ADMIN_ENGINE_ID = "projects/919326069447/locations/us-central1/reasoningEngines/5176575510360096768"
    
    # Initialize orchestrator
    orchestrator = CatalogOrchestrator(
        firebase_base_url=FIREBASE_BASE_URL,
        firebase_api_key=FIREBASE_API_KEY,
        catalog_admin_engine_id=CATALOG_ADMIN_ENGINE_ID,
        log_dir="/Users/valterandersson/Documents/myon/adk_agent/catalog_admin/multi_agent_system/logs"
    )
    
    # Run the pipeline
    orchestrator.run_pipeline()
