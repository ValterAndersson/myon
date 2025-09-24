"""
Scheduler for the Multi-Agent Catalog Curation System
Manages scheduled runs of different agents based on their optimal frequencies.
"""

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import schedule
import threading

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.orchestrator import CatalogOrchestrator, AgentType


class ScheduleFrequency(Enum):
    """Frequency of scheduled tasks"""
    EVERY_15_MINUTES = "15min"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    NIGHTLY = "nightly"


@dataclass
class ScheduledTask:
    """Represents a scheduled task"""
    name: str
    agent_type: AgentType
    frequency: ScheduleFrequency
    config: Dict[str, Any]
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    enabled: bool = True


class CatalogScheduler:
    """
    Manages scheduled execution of catalog curation tasks.
    """
    
    def __init__(self, orchestrator: CatalogOrchestrator, config_file: str = None):
        self.orchestrator = orchestrator
        self.logger = logging.getLogger("CatalogScheduler")
        self.running = False
        self.thread = None
        
        # Load configuration
        self.config_file = config_file or "scheduler_config.json"
        self.load_config()
        
        # Setup scheduled tasks
        self.setup_schedules()
        
    def load_config(self):
        """Load scheduler configuration from file"""
        default_config = {
            "tasks": [
                {
                    "name": "Triage New Exercises",
                    "agent_type": "TRIAGE",
                    "frequency": "15min",
                    "enabled": True,
                    "config": {
                        "batch_size": 10,
                        "parallel": True
                    }
                },
                {
                    "name": "Enrich with Aliases",
                    "agent_type": "ENRICHMENT",
                    "frequency": "daily",
                    "enabled": True,
                    "config": {
                        "batch_size": 5,
                        "parallel": True,
                        "max_exercises": 50
                    }
                },
                {
                    "name": "Deduplicate Families",
                    "agent_type": "JANITOR",
                    "frequency": "weekly",
                    "enabled": True,
                    "config": {
                        "parallel": False,
                        "dry_run": False
                    }
                },
                {
                    "name": "Find Gaps from Search",
                    "agent_type": "SCOUT",
                    "frequency": "hourly",
                    "enabled": False,  # Disabled until implemented
                    "config": {
                        "min_frequency": 3
                    }
                },
                {
                    "name": "Quality Audit",
                    "agent_type": "AUDITOR",
                    "frequency": "weekly",
                    "enabled": False,  # Disabled until implemented
                    "config": {
                        "dry_run": True
                    }
                }
            ],
            "global_settings": {
                "max_parallel_jobs": 2,
                "quiet_hours": {
                    "enabled": False,
                    "start": "22:00",
                    "end": "06:00"
                }
            }
        }
        
        # Try to load existing config
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                self.logger.info(f"Loaded config from {self.config_file}")
            except Exception as e:
                self.logger.error(f"Failed to load config: {e}, using defaults")
                self.config = default_config
        else:
            self.config = default_config
            self.save_config()
            
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            self.logger.info(f"Saved config to {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            
    def setup_schedules(self):
        """Setup scheduled tasks based on configuration"""
        for task_config in self.config["tasks"]:
            if not task_config["enabled"]:
                self.logger.info(f"Task '{task_config['name']}' is disabled")
                continue
                
            frequency = task_config["frequency"]
            task_func = lambda tc=task_config: self.run_scheduled_task(tc)
            
            if frequency == "15min":
                schedule.every(15).minutes.do(task_func)
                self.logger.info(f"Scheduled '{task_config['name']}' every 15 minutes")
            elif frequency == "hourly":
                schedule.every().hour.do(task_func)
                self.logger.info(f"Scheduled '{task_config['name']}' every hour")
            elif frequency == "daily":
                schedule.every().day.at("09:00").do(task_func)
                self.logger.info(f"Scheduled '{task_config['name']}' daily at 09:00")
            elif frequency == "nightly":
                schedule.every().day.at("02:00").do(task_func)
                self.logger.info(f"Scheduled '{task_config['name']}' nightly at 02:00")
            elif frequency == "weekly":
                schedule.every().sunday.at("03:00").do(task_func)
                self.logger.info(f"Scheduled '{task_config['name']}' weekly on Sunday at 03:00")
                
    def run_scheduled_task(self, task_config: Dict[str, Any]):
        """Execute a scheduled task"""
        task_name = task_config["name"]
        agent_type = AgentType[task_config["agent_type"]]
        
        self.logger.info(f"=" * 50)
        self.logger.info(f"Running scheduled task: {task_name}")
        self.logger.info(f"Agent type: {agent_type.value}")
        self.logger.info(f"=" * 50)
        
        try:
            # Check quiet hours
            if self.is_quiet_hours():
                self.logger.info(f"Skipping {task_name} - quiet hours")
                return
                
            # Run the appropriate task based on agent type
            if agent_type == AgentType.TRIAGE:
                self.run_triage_task(task_config["config"])
            elif agent_type == AgentType.ENRICHMENT:
                self.run_enrichment_task(task_config["config"])
            elif agent_type == AgentType.JANITOR:
                self.run_janitor_task(task_config["config"])
            else:
                self.logger.warning(f"Agent type {agent_type} not implemented yet")
                
            # Log completion
            self.log_task_completion(task_name)
            
        except Exception as e:
            self.logger.error(f"Failed to run task {task_name}: {e}")
            
    def run_triage_task(self, config: Dict[str, Any]):
        """Run the triage task to normalize exercises"""
        # Get unnormalized exercises
        exercises = self.orchestrator.firebase_client.get("getExercises", params={"limit": 1000})
        unnormalized = [ex for ex in exercises.get("exercises", []) 
                       if not ex.get("family_slug")]
        
        if not unnormalized:
            self.logger.info("No unnormalized exercises found")
            return
            
        self.logger.info(f"Found {len(unnormalized)} unnormalized exercises")
        
        # Create and execute batch job
        job = self.orchestrator.create_batch_job(
            AgentType.TRIAGE, 
            unnormalized, 
            batch_size=config.get("batch_size", 10)
        )
        self.orchestrator.execute_batch_job(job, parallel=config.get("parallel", True))
        
    def run_enrichment_task(self, config: Dict[str, Any]):
        """Run the enrichment task to add aliases"""
        # Get exercises that need aliases
        max_exercises = config.get("max_exercises", 50)
        exercises = self.orchestrator.firebase_client.get("getExercises", params={"limit": max_exercises})
        
        # Filter for approved exercises with family (these are good candidates)
        candidates = [ex for ex in exercises.get("exercises", []) 
                     if ex.get("approved") and ex.get("family_slug")]
        
        if not candidates:
            self.logger.info("No exercises needing enrichment found")
            return
            
        self.logger.info(f"Processing {len(candidates)} exercises for alias enrichment")
        
        # Create and execute batch job
        job = self.orchestrator.create_batch_job(
            AgentType.ENRICHMENT,
            candidates,
            batch_size=config.get("batch_size", 5)
        )
        self.orchestrator.execute_batch_job(job, parallel=config.get("parallel", True))
        
    def run_janitor_task(self, config: Dict[str, Any]):
        """Run the janitor task to deduplicate families"""
        # Get families with multiple exercises
        families = self.orchestrator.firebase_client.list_families(minSize=2)
        family_slugs = [f["slug"] for f in families.get("families", [])]
        
        if not family_slugs:
            self.logger.info("No families needing deduplication found")
            return
            
        self.logger.info(f"Processing {len(family_slugs)} families for deduplication")
        
        # For janitor, we process families sequentially to avoid conflicts
        for family_slug in family_slugs:
            try:
                result = self.orchestrator.firebase_client.post("backfillNormalizeFamily", {
                    "family": family_slug,
                    "apply": not config.get("dry_run", False)
                })
                
                if result.get("ok"):
                    merges = result.get("data", {}).get("merges", [])
                    if merges:
                        self.logger.info(f"Family {family_slug}: {len(merges)} merges")
                else:
                    self.logger.error(f"Failed to process family {family_slug}")
                    
            except Exception as e:
                self.logger.error(f"Error processing family {family_slug}: {e}")
                
    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours"""
        quiet_config = self.config["global_settings"].get("quiet_hours", {})
        if not quiet_config.get("enabled", False):
            return False
            
        now = datetime.now().time()
        start_time = datetime.strptime(quiet_config["start"], "%H:%M").time()
        end_time = datetime.strptime(quiet_config["end"], "%H:%M").time()
        
        if start_time <= end_time:
            return start_time <= now <= end_time
        else:  # Crosses midnight
            return now >= start_time or now <= end_time
            
    def log_task_completion(self, task_name: str):
        """Log task completion to file"""
        log_entry = {
            "task": task_name,
            "timestamp": datetime.now().isoformat(),
            "success": True
        }
        
        log_file = os.path.join(
            self.orchestrator.log_dir,
            f"scheduler_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")
            
    def start(self):
        """Start the scheduler in a background thread"""
        if self.running:
            self.logger.warning("Scheduler already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler)
        self.thread.daemon = True
        self.thread.start()
        self.logger.info("Scheduler started")
        
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Scheduler stopped")
        
    def _run_scheduler(self):
        """Main scheduler loop"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    def run_once(self, agent_type: str):
        """Manually trigger a specific agent type once"""
        task_config = next((t for t in self.config["tasks"] 
                          if t["agent_type"] == agent_type), None)
        
        if not task_config:
            self.logger.error(f"No task configured for agent type {agent_type}")
            return
            
        self.run_scheduled_task(task_config)
        
    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        return {
            "running": self.running,
            "next_runs": [
                {
                    "job": str(job),
                    "next_run": job.next_run.isoformat() if job.next_run else None
                }
                for job in schedule.jobs
            ],
            "enabled_tasks": [
                t["name"] for t in self.config["tasks"] if t["enabled"]
            ]
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Catalog Curation Scheduler")
    parser.add_argument("--mode", choices=["daemon", "once", "status"], default="once",
                       help="Run mode: daemon (continuous), once (single run), or status")
    parser.add_argument("--agent", choices=["TRIAGE", "ENRICHMENT", "JANITOR", "SCOUT", "AUDITOR"],
                       help="Agent type to run (for 'once' mode)")
    parser.add_argument("--config", help="Path to config file")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize components
    FIREBASE_BASE_URL = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")
    CATALOG_ADMIN_ENGINE_ID = "projects/919326069447/locations/us-central1/reasoningEngines/5176575510360096768"
    
    orchestrator = CatalogOrchestrator(
        firebase_base_url=FIREBASE_BASE_URL,
        firebase_api_key=FIREBASE_API_KEY,
        catalog_admin_engine_id=CATALOG_ADMIN_ENGINE_ID,
        log_dir="/Users/valterandersson/Documents/myon/adk_agent/catalog_admin/multi_agent_system/logs"
    )
    
    scheduler = CatalogScheduler(orchestrator, config_file=args.config)
    
    if args.mode == "daemon":
        print("Starting scheduler in daemon mode...")
        scheduler.start()
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.stop()
            print("\nScheduler stopped")
            
    elif args.mode == "once":
        if args.agent:
            print(f"Running {args.agent} agent once...")
            scheduler.run_once(args.agent)
        else:
            print("Running full pipeline once...")
            orchestrator.run_pipeline()
            
    elif args.mode == "status":
        status = scheduler.get_status()
        print(json.dumps(status, indent=2))
