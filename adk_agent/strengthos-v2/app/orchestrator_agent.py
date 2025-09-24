import os
from typing import List

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

# Reuse the existing tool implementations from strengthos_agent
from app.strengthos_agent import (
    get_user,
    get_user_workouts,
    get_workout,
    get_user_templates,
    get_template,
    list_exercises,
    search_exercises,
    get_exercise,
    get_user_routines,
    get_active_routine,
    get_routine,
    create_template,
    update_template,
    delete_template,
    create_routine,
    update_routine,
    delete_routine,
    set_active_routine,
    get_important_facts,
    get_analysis_context,
    get_my_user_id,
    validate_template_payload,
    insert_template,
    update_template_with_validation,
    # Memory helpers
    find_facts_by_text,
    delete_facts_by_text,
    upsert_preference,
    upsert_temporary_condition,
    review_and_decay_memories,
    analyze_recent_performance,
    enforce_brevity,
    delete_fact,
    # New: preferences
    get_user_preferences,
    update_user_preferences,
    # New: active workout
    health,
    propose_session,
    start_active_workout,
    get_active_workout,
    prescribe_set,
    log_set,
    score_set,
    add_exercise,
    swap_exercise,
    complete_active_workout,
    cancel_active_workout,
    note_active_workout,
    # New: catalog/admin
    ensure_exercise_exists,
    upsert_exercise,
    resolve_exercise,
    list_families,
    suggest_family_variant,
    suggest_aliases,
    upsert_alias,
    delete_alias,
    search_aliases,
    normalize_catalog_page,
    backfill_normalize_family,
    approve_exercise,
    refine_exercise,
    merge_exercises,
)

# Optional: non-invasive access to shared Firebase client for vNext
try:
    from libs.tools_firebase import FirebaseFunctionsClient  # type: ignore
except Exception:  # pragma: no cover
    FirebaseFunctionsClient = None  # type: ignore

# Factory to be used by new tool implementations gradually (does not affect current behavior)
def _get_firebase_client() -> "FirebaseFunctionsClient":  # type: ignore
    if FirebaseFunctionsClient is None:
        raise RuntimeError("FirebaseFunctionsClient not available")
    base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    api_key = os.getenv("FIREBASE_API_KEY")
    bearer = os.getenv("FIREBASE_ID_TOKEN")
    return FirebaseFunctionsClient(base_url=base_url, api_key=api_key, bearer_token=bearer)

# Agents by specialization

performance_tools: List[FunctionTool] = [
    FunctionTool(func=get_my_user_id),
    FunctionTool(func=get_analysis_context),
    FunctionTool(func=analyze_recent_performance),
    FunctionTool(func=get_user),
    FunctionTool(func=get_user_workouts),
    FunctionTool(func=get_workout),
    FunctionTool(func=get_user_routines),
    FunctionTool(func=get_active_routine),
    FunctionTool(func=get_important_facts),
    FunctionTool(func=review_and_decay_memories),
    # Preferences helpful for analysis context
    FunctionTool(func=get_user_preferences),
]

routine_design_tools: List[FunctionTool] = [
    FunctionTool(func=get_my_user_id),
    FunctionTool(func=get_analysis_context),
    FunctionTool(func=get_user),
    FunctionTool(func=get_user_templates),
    FunctionTool(func=get_template),
    FunctionTool(func=create_template),
    FunctionTool(func=update_template),
    FunctionTool(func=delete_template),
    FunctionTool(func=get_user_routines),
    FunctionTool(func=get_routine),
    FunctionTool(func=create_routine),
    FunctionTool(func=update_routine),
    FunctionTool(func=delete_routine),
    FunctionTool(func=set_active_routine),
    FunctionTool(func=get_important_facts),
    FunctionTool(func=upsert_preference),
    FunctionTool(func=get_user_preferences),
    FunctionTool(func=update_user_preferences),
    FunctionTool(func=validate_template_payload),
    FunctionTool(func=insert_template),
    FunctionTool(func=update_template_with_validation),
]

data_retrieval_tools: List[FunctionTool] = [
    FunctionTool(func=get_my_user_id),
    FunctionTool(func=list_exercises),
    FunctionTool(func=search_exercises),
    FunctionTool(func=get_exercise),
    FunctionTool(func=get_user_templates),
    FunctionTool(func=get_template),
    FunctionTool(func=get_user_workouts),
    FunctionTool(func=get_workout),
    FunctionTool(func=get_user_preferences),
]

# Template pipeline agents

template_selection_tools: List[FunctionTool] = [
    FunctionTool(func=get_my_user_id),
    FunctionTool(func=get_analysis_context),
    FunctionTool(func=analyze_recent_performance),
    FunctionTool(func=list_exercises),
    FunctionTool(func=search_exercises),
    FunctionTool(func=get_exercise),
    FunctionTool(func=get_important_facts),
    FunctionTool(func=review_and_decay_memories),
    FunctionTool(func=get_user_preferences),
]

template_insert_tools: List[FunctionTool] = [
    FunctionTool(func=validate_template_payload),
    FunctionTool(func=insert_template),
    FunctionTool(func=update_template_with_validation),
]

# New: Active Workout tool group
active_workout_tools: List[FunctionTool] = [
    FunctionTool(func=health),
    FunctionTool(func=propose_session),
    FunctionTool(func=start_active_workout),
    FunctionTool(func=get_active_workout),
    FunctionTool(func=prescribe_set),
    FunctionTool(func=log_set),
    FunctionTool(func=score_set),
    FunctionTool(func=add_exercise),
    FunctionTool(func=swap_exercise),
    FunctionTool(func=complete_active_workout),
    FunctionTool(func=cancel_active_workout),
    FunctionTool(func=note_active_workout),
]

# New: Catalog/Admin tool group
catalog_admin_tools: List[FunctionTool] = [
    FunctionTool(func=ensure_exercise_exists),
    FunctionTool(func=upsert_exercise),
    FunctionTool(func=resolve_exercise),
    FunctionTool(func=list_families),
    FunctionTool(func=suggest_family_variant),
    FunctionTool(func=suggest_aliases),
    FunctionTool(func=upsert_alias),
    FunctionTool(func=delete_alias),
    FunctionTool(func=search_aliases),
    FunctionTool(func=normalize_catalog_page),
    FunctionTool(func=backfill_normalize_family),
    FunctionTool(func=approve_exercise),
    FunctionTool(func=refine_exercise),
    FunctionTool(func=merge_exercises),
]

# (Removed list_available_tools utility; not exposing this as a tool.)

performance_agent = Agent(
    name="PerformanceAnalysisAgent",
    model=os.getenv("PERF_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=(
        "Be brief and analytical. No filler or engagement.\n"
        "Announce actions in one short line before tool calls (e.g., 'Fetching recent workouts...').\n"
        "Fetch needed data in parallel via get_analysis_context, then provide: 3–6 compact bullets of insights + 1–3 actionable steps.\n"
        "Favor numbers, trends, and decisions over narration."
    ),
    tools=performance_tools,
)

routine_design_agent = Agent(
    name="RoutineDesignAgent",
    model=os.getenv("ROUTINE_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=(
        "Be concise and schema-precise. No filler.\n"
        "Announce actions briefly before tool calls.\n"
        "Design/modify templates with exact numbers (no ranges). Validate with validate_template_payload, then insert/update.\n"
        "Use user constraints and memories; update preferences when confidently inferred."
    ),
    tools=routine_design_tools,
)

retrieval_agent = Agent(
    name="DataRetrievalAgent",
    model=os.getenv("RETRIEVAL_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "Keep outputs minimal. Announce action, fetch, then return a 1–3 line summary with key numbers only."
    ),
    tools=data_retrieval_tools,
)

template_selection_agent = Agent(
    name="TemplateSelectionAgent",
    model=os.getenv("TEMPLATE_SELECTION_MODEL", "gemini-2.5-pro"),
    instruction=(
        "Announce actions. Use get_analysis_context to gather context in parallel.\n"
        "Select exercises and exact set/rep/RIR schemes using evidence-based guidance.\n"
        "Output a proposed template object (exact schema) ready for validation. No extra narration."
    ),
    tools=template_selection_tools,
)

template_insert_agent = Agent(
    name="TemplateInsertAgent",
    model=os.getenv("TEMPLATE_INSERT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "Announce actions. Validate with validate_template_payload; if valid, insert/update.\n"
        "Do not alter numbers; ensure fields match schema exactly. Return only operation result (no fluff)."
    ),
    tools=template_insert_tools,
)

# Orchestrator agent uses instruction routing. For true agent-as-tool routing,
# use the ADK AgentTool abstraction when available in your environment.
orchestrator_instruction = (
    "You are the StrengthOS Orchestrator. Be concise, tool-driven, and actionable.\n\n"
    "Policy:\n"
    "- Be brief; avoid filler. Max 6 bullets or 6 short sentences.\n"
    "- Announce actions before tool calls in one short line.\n"
    "- Validate templates before insert/update; ask to apply changes.\n"
    "- On memory edits, comply immediately and confirm.\n\n"
    "Routing hints: Performance → analysis tools; Planning → template/routine tools; Active workout → active workout tools; Catalog → catalog/admin tools."
)

# In environments without Agent-as-Tool, we expose all tools and rely on routing prompt.
# The instruction strongly biases tool selection akin to sub-agent routing.
root_agent = Agent(
    name="StrengthOS_Orchestrator",
    model=os.getenv("ORCH_MODEL", "gemini-2.5-pro"),
    instruction=orchestrator_instruction,
    tools=list({t.func.__name__: t for t in (
        performance_tools + routine_design_tools + data_retrieval_tools + template_selection_tools + template_insert_tools + active_workout_tools + catalog_admin_tools + [
            FunctionTool(func=find_facts_by_text),
            FunctionTool(func=delete_facts_by_text),
            FunctionTool(func=delete_fact),
            FunctionTool(func=upsert_preference),
            FunctionTool(func=upsert_temporary_condition),
            FunctionTool(func=review_and_decay_memories),
            FunctionTool(func=enforce_brevity),
        ]
    )}.values()),
)