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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Drop broken GOOGLE_APPLICATION_CREDENTIALS paths to prefer ADC
gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if gac and not os.path.exists(gac):
    try:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        logger.info(f"Ignoring missing GOOGLE_APPLICATION_CREDENTIALS at {gac}")
    except Exception:
        pass


class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        super().set_up()
        logging_client = google_cloud_logging.Client()
        try:
            logging_client.setup_logging()
        except Exception:
            pass
        self.logger = logging_client.logger(__name__)
        try:
            import google.adk as _adk
            import google.genai as _genai
            logger.info(
                f"Runtime versions: google-adk={getattr(_adk, '__version__', 'unknown')}, google-genai={getattr(_genai, '__version__', 'unknown')}"
            )
        except Exception:
            logger.info("Runtime versions: not available")
        logger.info("Canvas Orchestrator initialized (Cloud Logging configured)")

    def register_operations(self) -> Mapping[str, Sequence]:
        operations = super().register_operations()
        return operations


def _read_requirements(path: str) -> list[str]:
    with open(path) as f:
        return [ln.strip() for ln in f.read().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def deploy_canvas_orchestrator(
    project: str,
    location: str,
    agent_name: str | None = "canvas-orchestrator",
    requirements_file: str = "agent_engine_requirements.txt",
    extra_packages: list[str] = ["./app"],
    env_vars: dict[str, str] = {},
) -> agent_engines.AgentEngine:
    staging_bucket_uri = f"gs://{project}-agent-engine"
    # Best-effort: create bucket if missing
    try:
        from google.cloud import storage
        client = storage.Client(project=project)
        name = staging_bucket_uri.replace("gs://", "")
        bucket = client.bucket(name)
        if not bucket.exists():
            client.create_bucket(bucket, location=location)
    except Exception:
        pass

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket_uri)

    requirements = _read_requirements(requirements_file)

    agent_engine = AgentEngineApp(agent=root_agent)

    env_vars = dict(env_vars or {})
    env_vars = {k: v for k, v in env_vars.items() if str(v).strip() != ""}
    env_vars.setdefault("NUM_WORKERS", "1")
    env_vars.setdefault("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    env_vars.setdefault("FIREBASE_API_KEY", "myon-agent-key-2024")

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
        "description": "Canvas Orchestrator (Router + Workout Orchestrator + Canvas Manager)",
        "extra_packages": extra_packages,
        "env_vars": env_vars,
        "requirements": requirements,
    }
    logging.info(f"Canvas Orchestrator config: {cfg}")

    if existing:
        logging.info(f"Updating existing Canvas Orchestrator: {agent_name}")
        remote = existing[0].update(**cfg)
    else:
        logging.info(f"Creating Canvas Orchestrator: {agent_name}")
        remote = agent_engines.create(**cfg)

    logging.info(f"Deployed agent with resource name: {remote.resource_name}")

    with open("deployment_metadata.json", "w") as f:
        json.dump({"remote_agent_engine_id": remote.resource_name, "deployment_timestamp": datetime.datetime.now().isoformat()}, f, indent=2)
    return remote


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy Canvas Orchestrator Agent")
    parser.add_argument("--project", default=None)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--agent-name", default="canvas-orchestrator")
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

    deploy_canvas_orchestrator(
        project=args.project,
        location=args.location,
        agent_name=args.agent_name,
        requirements_file=args.requirements_file,
        extra_packages=args.extra_packages,
        env_vars=env_vars,
    )


