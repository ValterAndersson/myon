import datetime
import json
import logging
import os
from typing import Any
from collections.abc import Mapping, Sequence

import google.auth
import vertexai
from google.cloud import logging as google_cloud_logging
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

from app.agent import root_agent
from app.utils.gcs import create_bucket_if_not_exists


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        """Set up logging for the agent engine app."""
        super().set_up()
        logging_client = google_cloud_logging.Client()
        # Route standard Python logging to Cloud Logging (stdout/stderr still captured separately)
        try:
            logging_client.setup_logging()
        except Exception:
            pass
        self.logger = logging_client.logger(__name__)
        try:
            import google.adk as _adk
            import google.genai as _genai
            logger.info(f"Runtime versions: google-adk={getattr(_adk, '__version__', 'unknown')}, google-genai={getattr(_genai, '__version__', 'unknown')}")
        except Exception:
            logger.info("Runtime versions: not available")
        logger.info("Catalog Admin Agent initialized (Cloud Logging configured)")
    
    def register_operations(self) -> Mapping[str, Sequence]:
        """Registers the operations of the Agent.
        
        Extends the base operations.
        """
        operations = super().register_operations()
        return operations


def _read_requirements(path: str) -> list[str]:
    with open(path) as f:
        return [ln.strip() for ln in f.read().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def deploy_catalog_admin(
    project: str,
    location: str,
    agent_name: str | None = "catalog-admin",
    requirements_file: str = "agent_engine_requirements.txt",
    extra_packages: list[str] = ["./app"],
    env_vars: dict[str, str] = {},
) -> agent_engines.AgentEngine:
    staging_bucket_uri = f"gs://{project}-agent-engine"
    create_bucket_if_not_exists(bucket_name=staging_bucket_uri, project=project, location=location)

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket_uri)

    requirements = _read_requirements(requirements_file)

    agent_engine = AgentEngineApp(agent=root_agent)

    # Prepare env vars
    env_vars = dict(env_vars or {})
    # Drop empty values coming from CLI so they don't fail validation
    env_vars = {k: v for k, v in env_vars.items() if str(v).strip() != ""}
    # Safe defaults
    env_vars.setdefault("NUM_WORKERS", "1")
    env_vars.setdefault("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    # Default API key if not provided
    env_vars.setdefault("FIREBASE_API_KEY", "myon-agent-key-2024")

    # If an engine with this name already exists, inject its numeric id as ADK_APP_NAME
    existing = list(agent_engines.list(filter=f"display_name={agent_name}"))
    if existing:
        try:
            existing_id = existing[0].resource_name.split("/")[-1]
            env_vars.setdefault("ADK_APP_NAME", existing_id)
            logging.info(f"Setting ADK_APP_NAME to existing engine id {existing_id}")
        except Exception:
            pass

    cfg: dict[str, Any] = {
        "agent_engine": agent_engine,
        "display_name": agent_name,
        "description": "Catalog Admin Agent (Exercises & Aliases)",
        "extra_packages": extra_packages,
        "env_vars": env_vars,
        "requirements": requirements,
    }
    logging.info(f"Catalog Admin config: {cfg}")

    if existing:
        logging.info(f"Updating existing Catalog Admin: {agent_name}")
        remote = existing[0].update(**cfg)
    else:
        logging.info(f"Creating Catalog Admin: {agent_name}")
        remote = agent_engines.create(**cfg)

    logging.info(f"Deployed agent with resource name: {remote.resource_name}")

    with open("deployment_metadata.json", "w") as f:
        json.dump({"remote_agent_engine_id": remote.resource_name, "deployment_timestamp": datetime.datetime.now().isoformat()}, f, indent=2)
    return remote


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy Catalog Admin Agent")
    parser.add_argument("--project", default=None)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--agent-name", default="catalog-admin")
    parser.add_argument("--requirements-file", default="agent_engine_requirements.txt")
    parser.add_argument("--extra-packages", nargs="+", default=["./app"])
    parser.add_argument("--set-env-vars")
    args = parser.parse_args()

    env_vars = {}
    if args.set_env_vars:
        for pair in args.set_env_vars.split(","):
            if not pair:
                continue
            k, v = pair.split("=", 1)
            env_vars[k] = v

    if not args.project:
        _, args.project = google.auth.default()

    deploy_catalog_admin(
        project=args.project,
        location=args.location,
        agent_name=args.agent_name,
        requirements_file=args.requirements_file,
        extra_packages=args.extra_packages,
        env_vars=env_vars,
    )


