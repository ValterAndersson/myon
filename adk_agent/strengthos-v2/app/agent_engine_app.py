# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# mypy: disable-error-code="attr-defined"
import copy
import datetime
import json
import logging
import os
from collections.abc import Mapping, Sequence
from typing import Any

import google.auth
import vertexai
from google.adk.artifacts import GcsArtifactService
from google.adk.sessions import VertexAiSessionService
from google.adk.memory import InMemoryMemoryService
from google.cloud import logging as google_cloud_logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, export
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

from app.agent import root_agent
from app.utils.gcs import create_bucket_if_not_exists
from app.utils.tracing import CloudTraceLoggingSpanExporter
from app.utils.typing import Feedback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        """Set up logging for the agent engine app."""
        super().set_up()
        logging_client = google_cloud_logging.Client()
        self.logger = logging_client.logger(__name__)
        logger.info(f"AgentEngineApp initialized")

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")

    def register_operations(self) -> Mapping[str, Sequence]:
        """Registers the operations of the Agent.

        Extends the base operations to include feedback registration functionality.
        """
        operations = super().register_operations()
        operations[""] = operations[""] + ["register_feedback"]
        return operations


def deploy_agent_engine_app(
    project: str,
    location: str,
    agent_name: str | None = None,
    requirements_file: str = ".requirements.txt",
    extra_packages: list[str] = ["./app"],
    env_vars: dict[str, str] = {},
) -> agent_engines.AgentEngine:
    """Deploy the agent engine app to Vertex AI."""

    staging_bucket_uri = f"gs://{project}-agent-engine"
    
    # Create staging bucket
    create_bucket_if_not_exists(
        bucket_name=staging_bucket_uri, project=project, location=location
    )

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket_uri)

    # Read requirements
    with open(requirements_file) as f:
        requirements = f.read().strip().split("\n")

    agent_engine = AgentEngineApp(
        agent=root_agent
    )

    # Set worker parallelism to 1
    env_vars["NUM_WORKERS"] = "1"
    
    # Add Firebase API key if available
    if os.environ.get("FIREBASE_API_KEY"):
        env_vars["FIREBASE_API_KEY"] = os.environ["FIREBASE_API_KEY"]

    # Common configuration for both create and update operations
    agent_config = {
        "agent_engine": agent_engine,
        "display_name": agent_name,
        "description": "StrengthOS fitness assistant",
        "extra_packages": extra_packages,
        "env_vars": env_vars,
    }
    logging.info(f"Agent config: {agent_config}")
    agent_config["requirements"] = requirements

    # Check if an agent with this name already exists
    existing_agents = list(agent_engines.list(filter=f"display_name={agent_name}"))
    if existing_agents:
        # Update the existing agent with new configuration
        logging.info(f"Updating existing agent: {agent_name}")
        remote_agent = existing_agents[0].update(**agent_config)
    else:
        # Create a new agent if none exists
        logging.info(f"Creating new agent: {agent_name}")
        remote_agent = agent_engines.create(**agent_config)

    config = {
        "remote_agent_engine_id": remote_agent.resource_name,
        "deployment_timestamp": datetime.datetime.now().isoformat(),
    }
    config_file = "deployment_metadata.json"

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    logging.info(f"Agent Engine ID written to {config_file}")

    return remote_agent


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deploy agent engine app to Vertex AI")
    parser.add_argument(
        "--project",
        default=None,
        help="GCP project ID (defaults to application default credentials)",
    )
    parser.add_argument(
        "--location",
        default="us-central1",
        help="GCP region (defaults to us-central1)",
    )
    parser.add_argument(
        "--agent-name",
        default="strengthos-v2",
        help="Name for the agent engine",
    )
    parser.add_argument(
        "--requirements-file",
        default=".requirements.txt",
        help="Path to requirements.txt file",
    )
    parser.add_argument(
        "--extra-packages",
        nargs="+",
        default=["./app"],
        help="Additional packages to include",
    )
    parser.add_argument(
        "--set-env-vars",
        help="Comma-separated list of environment variables in KEY=VALUE format",
    )
    args = parser.parse_args()

    # Parse environment variables if provided
    env_vars = {}
    if args.set_env_vars:
        for pair in args.set_env_vars.split(","):
            key, value = pair.split("=", 1)
            env_vars[key] = value

    if not args.project:
        _, args.project = google.auth.default()

    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🤖 DEPLOYING AGENT TO VERTEX AI AGENT ENGINE 🤖         ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    deploy_agent_engine_app(
        project=args.project,
        location=args.location,
        agent_name=args.agent_name,
        requirements_file=args.requirements_file,
        extra_packages=args.extra_packages,
        env_vars=env_vars,
    )
