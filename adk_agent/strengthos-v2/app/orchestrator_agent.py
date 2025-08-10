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
)

# Agents by specialization

performance_tools: List[FunctionTool] = [
    FunctionTool(func=get_my_user_id),
    FunctionTool(func=get_analysis_context),
    FunctionTool(func=get_user),
    FunctionTool(func=get_user_workouts),
    FunctionTool(func=get_workout),
    FunctionTool(func=get_user_routines),
    FunctionTool(func=get_active_routine),
    FunctionTool(func=get_important_facts),
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
]

# Template pipeline agents

template_selection_tools: List[FunctionTool] = [
    FunctionTool(func=get_my_user_id),
    FunctionTool(func=get_analysis_context),
    FunctionTool(func=list_exercises),
    FunctionTool(func=search_exercises),
    FunctionTool(func=get_exercise),
    FunctionTool(func=get_important_facts),
]

template_insert_tools: List[FunctionTool] = [
    FunctionTool(func=validate_template_payload),
    FunctionTool(func=insert_template),
    FunctionTool(func=update_template_with_validation),
]

performance_agent = Agent(
    name="PerformanceAnalysisAgent",
    model=os.getenv("PERF_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=(
        "Announce actions before tool calls (e.g., 'Fetching recent workouts...'). "
        "Use evidence-based reasoning (volume landmarks, progressive overload). "
        "Fetch needed data in parallel via get_analysis_context, then synthesize concise insights and recommendations."
    ),
    tools=performance_tools,
)

routine_design_agent = Agent(
    name="RoutineDesignAgent",
    model=os.getenv("ROUTINE_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=(
        "Announce actions before tool calls. Use science-based methods and user constraints. "
        "Design/modify routines and templates with exact numbers (no ranges). "
        "Validate payloads before insert/update."
    ),
    tools=routine_design_tools,
)

retrieval_agent = Agent(
    name="DataRetrievalAgent",
    model=os.getenv("RETRIEVAL_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "Announce actions briefly before each call. Fetch and summarize data compactly for other agents."
    ),
    tools=data_retrieval_tools,
)

template_selection_agent = Agent(
    name="TemplateSelectionAgent",
    model=os.getenv("TEMPLATE_SELECTION_MODEL", "gemini-2.5-pro"),
    instruction=(
        "Announce actions. Use get_analysis_context to gather user context and history in parallel, "
        "then select exercises and set/rep/RIR schemes using evidence-based guidance (Israetel, Nippard, studies). "
        "Output a proposed template object with exact numbers, ready for validation."
    ),
    tools=template_selection_tools,
)

template_insert_agent = Agent(
    name="TemplateInsertAgent",
    model=os.getenv("TEMPLATE_INSERT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "Announce actions. Validate with validate_template_payload; if valid, call insert_template or update_template_with_validation. "
        "Do not alter numbers; ensure fields match schema exactly. Return operation result."
    ),
    tools=template_insert_tools,
)

# Orchestrator agent uses instruction routing. For true agent-as-tool routing,
# use the ADK AgentTool abstraction when available in your environment.
orchestrator_instruction = (
    "You are the orchestrator. Route to sub-agents and enforce concise analytical output.\n\n"
    "Routing:\n"
    "- PerformanceAnalysisAgent: trends/insights.\n"
    "- RoutineDesignAgent: plans/templates.\n"
    "- DataRetrievalAgent: fetch/search.\n"
    "- TemplateSelectionAgent → TemplateInsertAgent: validate then insert/update.\n\n"
    "Output policy (strict):\n"
    "- Be brief; avoid filler.\n"
    "- Prefer compact bullets with bold labels; ≤6 bullets.\n"
    "- No headings unless asked.\n"
    "- Use '-', '*', or numbers only (no '•').\n\n"
    "Procedure:\n"
    "- Fetch data in parallel (workouts, routines, facts) first if needed.\n"
    "- Announce actions in one short line before tool calls.\n"
    "- Then produce a concise answer per policy."
)

# In environments without Agent-as-Tool, we expose all tools and rely on routing prompt.
# The instruction strongly biases tool selection akin to sub-agent routing.
root_agent = Agent(
    name="StrengthOS_Orchestrator",
    model=os.getenv("ORCH_MODEL", "gemini-2.5-pro"),
    instruction=orchestrator_instruction,
    tools=list({t.func.__name__: t for t in (
        performance_tools + routine_design_tools + data_retrieval_tools + template_selection_tools + template_insert_tools
    )}.values()),
)