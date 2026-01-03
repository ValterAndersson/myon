"""
Canvas Orchestrator Agent Engine Entry Point.

This module provides the Vertex AI Agent Engine wrapper with 4-Lane routing.
When USE_SHELL_AGENT=true, requests are routed through the 4-Lane system:

Architecture (4-Lane "Shared Brain"):
- Fast Lane: Regex patterns → direct skill execution (no LLM, <500ms)
- Slow Lane: ShellAgent (gemini-2.5-pro) for conversational reasoning
- Functional Lane: gemini-2.5-flash for JSON-only Smart Button logic
- Worker Lane: Background scripts (not routed here, triggered by PubSub)
"""

import datetime
import json
import logging
import os
from typing import Any, Generator
from collections.abc import Mapping, Sequence

import google.auth
import vertexai
from google.cloud import logging as google_cloud_logging
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Use agent_multi which respects USE_SHELL_AGENT flag
from app.agent_multi import root_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Feature flag for fast lane bypass
USE_SHELL_AGENT = os.getenv("USE_SHELL_AGENT", "false").lower() in ("true", "1", "yes")

# Drop broken GOOGLE_APPLICATION_CREDENTIALS paths to prefer ADC
gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if gac and not os.path.exists(gac):
    try:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        logger.info(f"Ignoring missing GOOGLE_APPLICATION_CREDENTIALS at {gac}")
    except Exception:
        pass


class AgentEngineApp(AdkApp):
    """
    Custom AdkApp with Fast Lane bypass for low-latency copilot commands.
    
    When USE_SHELL_AGENT=true, the stream_query method checks for fast lane
    patterns before invoking the LLM, enabling sub-500ms response times
    for copilot commands like "done", "8 @ 100", "next set".
    """
    
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
        
        mode = "Shell Agent (unified)" if USE_SHELL_AGENT else "Multi-Agent (legacy)"
        logger.info(f"Canvas Orchestrator initialized ({mode}, Cloud Logging configured)")

    def stream_query(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        **kwargs,
    ) -> Generator[dict, None, None]:
        """
        Query with Full Pipeline: Fast Lane bypass, Tool Planner, Critic.
        
        Pipeline stages:
        1. Set context (FIRST - before any logic)
        2. Router: Determine Fast/Slow/Functional lane
        3. Fast Lane: Execute skills directly (no LLM, <500ms)
        4. Functional Lane: Flash-based JSON logic
        5. Slow Lane: Generate plan → Execute with LLM → Critic check
        
        Only active when USE_SHELL_AGENT=true.
        """
        routing = None
        plan = None
        
        # === SET CONTEXT FIRST (Thread-safe via contextvars) ===
        # This MUST happen before any routing or tool execution.
        # Establishes the security boundary for the entire request.
        if USE_SHELL_AGENT:
            try:
                from app.shell.context import SessionContext, set_current_context
                
                # Parse context from message prefix and set as current context
                ctx = SessionContext.from_message(message)
                set_current_context(ctx, message)
                logger.debug("Context set: user=%s canvas=%s", ctx.user_id, ctx.canvas_id)
                
            except Exception as e:
                logger.error("Failed to set context: %s", e)
        
        # === ROUTING: 4-Lane System ===
        if USE_SHELL_AGENT:
            try:
                from app.shell.router import route_request, execute_fast_lane, Lane
                from app.shell.context import SessionContext
                from app.shell.planner import generate_plan, should_generate_plan
                
                # Use route_request which handles both str and JSON payloads
                routing = route_request(message)
                
                # === FAST LANE: Direct skill execution ===
                if routing.lane == Lane.FAST:
                    logger.info("FAST LANE: %s → %s", message[:30], routing.intent)
                    
                    ctx = SessionContext.from_message(message)
                    result = execute_fast_lane(routing, message, ctx)
                    
                    yield self._format_fast_lane_response(result, routing.intent)
                    return
                
                # === FUNCTIONAL LANE: Flash-based JSON logic ===
                if routing.lane == Lane.FUNCTIONAL:
                    logger.info("FUNCTIONAL LANE: intent=%s", routing.intent)
                    
                    ctx = SessionContext.from_message(message)
                    
                    # Parse JSON payload
                    try:
                        import json as json_mod
                        payload = json_mod.loads(message) if isinstance(message, str) else message
                    except (json_mod.JSONDecodeError, TypeError):
                        payload = {"message": message}
                    
                    # Execute async functional handler
                    import asyncio
                    from app.shell.functional_handler import execute_functional_lane
                    
                    # Run async handler in sync context
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(
                            execute_functional_lane(routing, payload, ctx)
                        )
                    finally:
                        loop.close()
                    
                    yield self._format_functional_lane_response(result, routing.intent)
                    return
                
                # === TOOL PLANNER: Generate plan for Slow Lane ===
                if should_generate_plan(routing):
                    plan = generate_plan(routing, message)
                    logger.info("PLANNER: Generated plan for %s", routing.intent)
                    
            except ImportError as e:
                logger.warning("Shell module import failed: %s - falling back to standard", e)
            except Exception as e:
                logger.error("Shell pipeline error: %s - falling back to standard", e)
        
        # === SLOW LANE: LLM execution with optional plan injection ===
        logger.info("SLOW LANE: %s (intent=%s)", message[:50], routing.intent if routing else "unknown")
        
        # Inject planning context if available
        augmented_message = message
        if plan and not plan.skip_planning:
            plan_prompt = plan.to_system_prompt()
            augmented_message = f"{message}\n\n{plan_prompt}"
            logger.info("PLANNER: Injected plan for %s", plan.intent)
        
        # Collect response for critic pass
        collected_text = []
        
        for chunk in super().stream_query(
            user_id=user_id,
            session_id=session_id,
            message=augmented_message,
            **kwargs,
        ):
            # Collect text for critic
            if USE_SHELL_AGENT:
                try:
                    candidates = chunk.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part:
                                collected_text.append(part["text"])
                except Exception:
                    pass
            
            yield chunk
        
        # === CRITIC PASS: Validate response for complex intents ===
        if USE_SHELL_AGENT and routing and collected_text:
            try:
                from app.shell.critic import run_critic, should_run_critic
                
                full_response = "".join(collected_text)
                
                if should_run_critic(routing.intent, len(full_response)):
                    critic_result = run_critic(
                        response=full_response,
                        response_type="coaching" if "ANALYZE" in (routing.intent or "") else "general",
                    )
                    
                    if critic_result.has_errors:
                        logger.warning("CRITIC: Response failed safety check: %s", 
                                      critic_result.error_messages)
                        # Log error but don't block - already streamed
                    elif critic_result.findings:
                        logger.info("CRITIC: %d warnings (passed)", len(critic_result.findings))
                        
            except ImportError as e:
                logger.debug("Critic import failed: %s", e)
            except Exception as e:
                logger.warning("Critic error: %s", e)
    
    def _format_fast_lane_response(self, result: dict, intent: str) -> dict:
        """
        Format fast lane result as ADK-compatible streaming response.
        """
        # Extract text from skill result
        skill_result = result.get("result", {})
        
        if isinstance(skill_result, dict):
            text = skill_result.get("message", "Done.")
        else:
            text = str(skill_result)
        
        return {
            "candidates": [{
                "content": {
                    "parts": [{"text": text}],
                    "role": "model"
                },
                "finish_reason": "STOP",
            }],
            "usage_metadata": {
                "prompt_token_count": 0,
                "candidates_token_count": len(text.split()),
                "total_token_count": len(text.split()),
            },
            "model_version": "fast-lane-bypass",
            "_metadata": {
                "fast_lane": True,
                "intent": intent,
                "latency_class": "fast",
            }
        }
    
    def _format_functional_lane_response(self, result: dict, intent: str) -> dict:
        """
        Format functional lane result as ADK-compatible response.
        
        Functional lane returns JSON, so we wrap it appropriately.
        The frontend can parse the JSON from the text field.
        """
        import json as json_mod
        
        # Extract result from functional handler
        func_result = result.get("result", {})
        
        # For MONITOR_STATE with NULL action, return minimal response
        if func_result.get("action") == "NULL":
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": ""}],  # Empty response for silent observer
                        "role": "model"
                    },
                    "finish_reason": "STOP",
                }],
                "usage_metadata": {
                    "prompt_token_count": 0,
                    "candidates_token_count": 0,
                    "total_token_count": 0,
                },
                "model_version": "functional-lane-flash",
                "_metadata": {
                    "functional_lane": True,
                    "intent": intent,
                    "action": "NULL",
                    "latency_class": "functional",
                }
            }
        
        # Format result as JSON string for frontend parsing
        json_text = json_mod.dumps(func_result, indent=2)
        
        return {
            "candidates": [{
                "content": {
                    "parts": [{"text": json_text}],
                    "role": "model"
                },
                "finish_reason": "STOP",
            }],
            "usage_metadata": {
                "prompt_token_count": 0,
                "candidates_token_count": len(json_text.split()),
                "total_token_count": len(json_text.split()),
            },
            "model_version": "functional-lane-flash",
            "_metadata": {
                "functional_lane": True,
                "intent": intent,
                "action": func_result.get("action", "UNKNOWN"),
                "latency_class": "functional",
            }
        }

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

    # Determine description based on mode
    if USE_SHELL_AGENT:
        description = "Canvas Orchestrator (Shell Agent with Fast Lane bypass)"
    else:
        description = "Canvas Orchestrator (Router + Workout Orchestrator + Canvas Manager)"

    cfg: dict[str, Any] = {
        "agent_engine": agent_engine,
        "display_name": agent_name,
        "description": description,
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
