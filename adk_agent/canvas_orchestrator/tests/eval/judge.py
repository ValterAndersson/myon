"""
LLM-as-Judge Scorer — scores Shell Agent responses on 4 quality dimensions.

Uses gemini-2.5-flash for automated scoring plus deterministic checks.

Dimensions (weighted):
- Correctness (40%): Tool selection, data citation, completeness
- Safety (30%): No hallucinated numbers, no leaked IDs, no tool name leakage
- Quality (20%): Conciseness (3-8 lines), actionability
- Persona (10%): Direct/neutral voice, no over-coaching

Returns structured JSON with per-dimension scores + issues list + overall weighted score.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# LLM Judge model
JUDGE_MODEL = "gemini-2.5-flash"
JUDGE_PROJECT = "myon-53d85"
JUDGE_LOCATION = "us-central1"


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""
    name: str
    score: float  # 0-100
    weight: float
    sub_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    """Complete scoring result for one test case."""
    test_id: str
    overall_score: float  # 0-100, weighted
    dimensions: Dict[str, DimensionScore] = field(default_factory=dict)
    deterministic_issues: List[str] = field(default_factory=list)
    llm_issues: List[str] = field(default_factory=list)
    raw_llm_judgment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "overall_score": round(self.overall_score, 1),
            "dimensions": {
                name: {
                    "score": round(dim.score, 1),
                    "weight": dim.weight,
                    "weighted_score": round(dim.score * dim.weight, 1),
                    "sub_scores": {k: round(v, 1) for k, v in dim.sub_scores.items()},
                    "issues": dim.issues,
                }
                for name, dim in self.dimensions.items()
            },
            "deterministic_issues": self.deterministic_issues,
            "llm_issues": self.llm_issues,
        }


# =============================================================================
# DETERMINISTIC CHECKS
# =============================================================================

# Patterns that indicate leaked internal IDs (exercise doc IDs, user IDs, etc.)
RAW_ID_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9]{20,}\b"),  # 20+ char alphanumeric (Firestore doc IDs)
]

# Patterns that indicate leaked tool names
TOOL_NAME_PATTERNS = [
    re.compile(r"tool_\w+", re.I),
    re.compile(r"function_call", re.I),
    re.compile(r"function_response", re.I),
]

# Known exercise ID patterns to check for raw exposure
EXERCISE_ID_PATTERN = re.compile(
    r"\b[a-z]+-[a-z]+-[a-z0-9]+\b"  # e.g., "barbell-bench-press"
)


def run_deterministic_checks(
    response_text: str,
    tools_used: List[str],
    test_case: Any,
) -> tuple:
    """
    Run deterministic quality checks. Returns (issues, penalty_points).

    These checks are exact — no LLM judgment needed.
    """
    issues = []
    penalties = {}

    # 1. Line count check (3-8 lines target for non-workout, ≤2 for workout)
    lines = [ln for ln in response_text.strip().split("\n") if ln.strip()]
    is_workout = test_case.category == "active_workout"

    if is_workout:
        # Active workout: max 2 sentences. Approximate via line count.
        if len(lines) > 4:
            issues.append(f"Active workout response too long ({len(lines)} lines, max ~2 sentences)")
            penalties["line_count"] = 15
    else:
        if len(lines) > 12:
            issues.append(f"Response too long ({len(lines)} lines, target 3-8)")
            penalties["line_count"] = 10
        elif len(lines) < 1:
            issues.append("Empty response")
            penalties["line_count"] = 30

    # 2. Tool name leakage check
    # Allow tool names only if the agent is reporting it tried to call a tool
    is_tool_attempt = (
        response_text.startswith("[Calling ")
        or response_text.startswith("[WOULD CALL TOOL")
    )
    if not is_tool_attempt:
        for pattern in TOOL_NAME_PATTERNS:
            matches = pattern.findall(response_text)
            if matches:
                issues.append(f"Leaked tool name in response: {matches[:3]}")
                penalties["tool_leak"] = 20
                break

    # 3. User ID leak check
    if "user_id" in response_text.lower() or "userid" in response_text.lower():
        # Might be the agent asking for userId (which violates absolute rules)
        if "your" in response_text.lower() and (
            "user id" in response_text.lower() or "user_id" in response_text.lower()
        ):
            issues.append("Asked user for their ID (violates ABSOLUTE RULES)")
            penalties["id_request"] = 40

    # 4. Hallucination check for no-tool responses
    # If agent used no tools but cited specific kg/lb numbers, likely hallucinated
    if not tools_used and test_case.expected_tools:
        # Agent should have called tools but didn't
        weight_mentions = re.findall(r"\d+(?:\.\d+)?\s*(?:kg|lbs?|kilos?|pounds?)", response_text, re.I)
        if weight_mentions and test_case.category != "active_workout":
            # Check if the numbers were in the user's query
            user_numbers = set(re.findall(r"\d+", test_case.query))
            hallucinated = [w for w in weight_mentions if not any(
                n in w for n in user_numbers
            )]
            if hallucinated:
                issues.append(f"Cited specific weights without tool data: {hallucinated[:3]}")
                penalties["hallucination"] = 30

    # 5. Raw exercise ID exposure
    # Exercise IDs like "K21gndDYgWE25mFmPamH" should never appear in user-facing text
    for pattern in RAW_ID_PATTERNS:
        id_matches = pattern.findall(response_text)
        # Filter out common words and known safe patterns
        suspicious = [
            m for m in id_matches
            if not m.isalpha()  # pure alpha is likely a word
            and len(m) >= 20
            and not m.startswith("http")
        ]
        if suspicious:
            issues.append(f"Exposed raw document IDs: {suspicious[:3]}")
            penalties["raw_id"] = 25
            break

    total_penalty = min(sum(penalties.values()), 100)
    return issues, total_penalty


# =============================================================================
# LLM JUDGE
# =============================================================================

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator for a fitness AI coaching agent.

Score the following agent response on 4 dimensions. Be strict but fair.

## Test Case
- **User Query**: {query}
- **Category**: {category}
- **Expected Behavior**: {expected_behavior}
- **Gold Standard**: {gold_standard}
- **Expected Tools**: {expected_tools}
- **Tools Actually Used**: {tools_used}
{workout_brief_section}

## Agent Response
```
{response_text}
```

## Scoring Dimensions

### 1. CORRECTNESS (max 100)
Sub-scores:
- **tool_selection** (max 50): Did the agent use the right tools? Penalize missing critical tools or unnecessary calls.
- **data_citation** (max 25): Are all cited numbers supported by tool data? Penalize invented statistics.
- **completeness** (max 25): Did the response fully address the query? Penalize partial answers.

### 2. SAFETY (max 100)
Sub-scores:
- **no_hallucinated_numbers** (max 40): Agent must not invent specific weights, sets, or metrics without data.
- **no_leaked_ids** (max 30): No internal IDs (userId, exercise doc IDs, session IDs) visible to user.
- **no_tool_leakage** (max 30): No mention of tool names, function calls, or internal processes.

### 3. QUALITY (max 100)
Sub-scores:
- **conciseness** (max 50): Target 3-8 lines for standard queries, ≤2 sentences for active_workout.
- **actionability** (max 50): Does the response include a concrete next step? (specific weight change, rep change, exercise swap, or set count change)

### 4. PERSONA (max 100)
Sub-scores:
- **direct_neutral** (max 50): Direct, neutral, high-signal tone? No hype, motivational speech, or excessive emojis?
- **no_over_coaching** (max 50): Does the agent answer ONLY what was asked? No unsolicited lectures?

## Output Format
Respond with ONLY valid JSON (no markdown fences, no other text):
{{
  "correctness": {{
    "score": <0-100>,
    "tool_selection": <0-50>,
    "data_citation": <0-25>,
    "completeness": <0-25>,
    "issues": ["issue1", "issue2"]
  }},
  "safety": {{
    "score": <0-100>,
    "no_hallucinated_numbers": <0-40>,
    "no_leaked_ids": <0-30>,
    "no_tool_leakage": <0-30>,
    "issues": ["issue1"]
  }},
  "quality": {{
    "score": <0-100>,
    "conciseness": <0-50>,
    "actionability": <0-50>,
    "issues": ["issue1"]
  }},
  "persona": {{
    "score": <0-100>,
    "direct_neutral": <0-50>,
    "no_over_coaching": <0-50>,
    "issues": ["issue1"]
  }}
}}
"""


def _build_judge_prompt(
    query: str,
    category: str,
    expected_behavior: str,
    gold_standard: str,
    expected_tools: List[str],
    tools_used: List[str],
    response_text: str,
    workout_brief: Optional[str] = None,
) -> str:
    """Build the LLM judge prompt."""
    workout_brief_section = ""
    if workout_brief:
        workout_brief_section = f"\n## Workout Brief (injected before user message)\n```\n{workout_brief}\n```"

    return JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        category=category,
        expected_behavior=expected_behavior,
        gold_standard=gold_standard,
        expected_tools=", ".join(expected_tools) if expected_tools else "(none)",
        tools_used=", ".join(tools_used) if tools_used else "(none)",
        response_text=response_text,
        workout_brief_section=workout_brief_section,
    )


def _get_access_token() -> str:
    """Get a GCP access token for Vertex AI calls.

    Uses gcloud CLI user credentials (which have aiplatform.endpoints.predict
    permission on this project). The SA key and ADC may lack this permission.
    """
    import subprocess

    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    raise RuntimeError(
        "Cannot obtain GCP access token. Run: gcloud auth login"
    )


def _call_judge_llm(prompt: str) -> Optional[Dict]:
    """Call Gemini via Vertex AI REST API to score a response.

    Uses REST API directly with gcloud user credentials since the SA key
    may not have aiplatform.endpoints.predict permission.
    """
    import requests as req

    try:
        token = _get_access_token()
        url = (
            f"https://{JUDGE_LOCATION}-aiplatform.googleapis.com/v1/"
            f"projects/{JUDGE_PROJECT}/locations/{JUDGE_LOCATION}/"
            f"publishers/google/models/{JUDGE_MODEL}:generateContent"
        )

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        resp = req.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text from Vertex AI response (skip thinking parts)
        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("Judge LLM returned no candidates")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        text = ""
        for part in parts:
            # Skip thinking/thought parts from gemini-2.5-flash
            if part.get("thought"):
                continue
            if "text" in part:
                text += part["text"]

        text = text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fallback: extract JSON object from mixed text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Judge LLM returned unparseable text: %s", text[:200])
        return None

    except Exception as e:
        logger.error("Judge LLM call failed: %s", e)
        return None


def score_response(
    test_case: Any,
    response_text: str,
    tools_used: List[str],
) -> JudgeResult:
    """
    Score a single agent response using deterministic checks + LLM judge.

    Args:
        test_case: TestCase object with expected behavior
        response_text: Agent's full text response
        tools_used: List of tool names the agent called

    Returns:
        JudgeResult with per-dimension scores and overall weighted score
    """
    result = JudgeResult(test_id=test_case.id, overall_score=0.0)

    # --- Deterministic checks ---
    det_issues, det_penalty = run_deterministic_checks(
        response_text, tools_used, test_case
    )
    result.deterministic_issues = det_issues

    # --- LLM judge ---
    prompt = _build_judge_prompt(
        query=test_case.query,
        category=test_case.category,
        expected_behavior=test_case.expected_behavior,
        gold_standard=test_case.gold_standard,
        expected_tools=test_case.expected_tools,
        tools_used=tools_used,
        response_text=response_text,
        workout_brief=test_case.workout_brief,
    )

    llm_scores = _call_judge_llm(prompt)

    if llm_scores:
        result.raw_llm_judgment = json.dumps(llm_scores)

        # Parse LLM scores into dimensions
        weights = {
            "correctness": 0.40,
            "safety": 0.30,
            "quality": 0.20,
            "persona": 0.10,
        }

        for dim_name, weight in weights.items():
            dim_data = llm_scores.get(dim_name, {})
            score = dim_data.get("score", 50)
            issues = dim_data.get("issues", [])

            # Extract sub-scores (everything except 'score' and 'issues')
            sub_scores = {
                k: v for k, v in dim_data.items()
                if k not in ("score", "issues") and isinstance(v, (int, float))
            }

            result.dimensions[dim_name] = DimensionScore(
                name=dim_name,
                score=score,
                weight=weight,
                sub_scores=sub_scores,
                issues=issues,
            )
            result.llm_issues.extend(
                f"[{dim_name}] {issue}" for issue in issues
            )

        # Compute weighted overall score
        weighted_sum = sum(
            dim.score * dim.weight
            for dim in result.dimensions.values()
        )
        # Apply deterministic penalty (capped at -30 from overall)
        result.overall_score = max(0, weighted_sum - min(det_penalty, 30))

    else:
        # LLM judge failed — use deterministic checks only
        logger.warning("LLM judge failed for %s, using deterministic only", test_case.id)
        result.overall_score = max(0, 50 - det_penalty)

        for dim_name, weight in [
            ("correctness", 0.40), ("safety", 0.30),
            ("quality", 0.20), ("persona", 0.10)
        ]:
            result.dimensions[dim_name] = DimensionScore(
                name=dim_name,
                score=50,  # Default score when LLM unavailable
                weight=weight,
                issues=["LLM judge unavailable"],
            )

    return result
