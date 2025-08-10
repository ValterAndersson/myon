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
)

# Agents by specialization

performance_tools: List[FunctionTool] = [
    FunctionTool(func=get_user),
    FunctionTool(func=get_user_workouts),
    FunctionTool(func=get_workout),
    FunctionTool(func=get_user_routines),
    FunctionTool(func=get_active_routine),
    FunctionTool(func=get_important_facts),
]

routine_design_tools: List[FunctionTool] = [
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
]

data_retrieval_tools: List[FunctionTool] = [
    FunctionTool(func=get_user),
    FunctionTool(func=list_exercises),
    FunctionTool(func=search_exercises),
    FunctionTool(func=get_exercise),
    FunctionTool(func=get_user_templates),
    FunctionTool(func=get_template),
    FunctionTool(func=get_user_workouts),
    FunctionTool(func=get_workout),
]


performance_agent = Agent(
    name="PerformanceAnalysisAgent",
    model=os.getenv("PERF_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=(
        "You analyze historical performance, identify trends and insights, and provide actionable summaries. "
        "First, request or fetch the required data in parallel (workouts, routines, important facts). "
        "Then synthesize a concise analysis with key metrics and recommendations."
    ),
    tools=performance_tools,
)

routine_design_agent = Agent(
    name="RoutineDesignAgent",
    model=os.getenv("ROUTINE_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=(
        "You design or modify routines and templates based on user goals, level, equipment, and constraints. "
        "Gather user context and any relevant templates/routines, then propose a plan with clear steps."
    ),
    tools=routine_design_tools,
)

retrieval_agent = Agent(
    name="DataRetrievalAgent",
    model=os.getenv("RETRIEVAL_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "You fetch and summarize requested data quickly and precisely. "
        "Return compact summaries suitable as inputs to other agents."
    ),
    tools=data_retrieval_tools,
)

# Orchestrator agent uses instruction routing. For true agent-as-tool routing,
# use the ADK AgentTool abstraction when available in your environment.
orchestrator_instruction = (
    "Route requests to specialized agents:\n"
    "- PerformanceAnalysisAgent: trends/insights\n"
    "- RoutineDesignAgent: plans/templates\n"
    "- DataRetrievalAgent: fetch/search\n\n"
    "For analysis: fetch data in parallel (workouts, routines, facts) first, then synthesize a concise summary."
)

# In environments without Agent-as-Tool, we expose all tools and rely on routing prompt.
# The instruction strongly biases tool selection akin to sub-agent routing.
root_agent = Agent(
    name="StrengthOS-Orchestrator",
    model=os.getenv("ORCH_MODEL", "gemini-2.5-pro"),
    instruction=orchestrator_instruction,
    tools=list({t.func.__name__: t for t in (
        performance_tools + routine_design_tools + data_retrieval_tools
    )}.values()),
)