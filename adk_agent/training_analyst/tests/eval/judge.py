"""
Recommendation Quality Judge — two-stage scorer for training recommendations.

Stage 1: Deterministic checks (Python) — field validation, template penalties
Stage 2: LLM judge (Gemini 2.5 Flash) — 4 weighted quality dimensions

Dimensions:
- Clarity (35%): Is summary+rationale immediately understandable?
- Data Grounding (30%): Are specific numbers/signals cited from input data?
- Actionability (25%): Does the user know what will happen and where?
- Contextual Fit (10%): Does language match the scenario?
"""

import json
import logging
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
    score: float
    weight: float
    sub_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    """Complete scoring result for one test case."""
    test_id: str
    overall_score: float
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
# STAGE 1: DETERMINISTIC CHECKS
# =============================================================================

BARE_TEMPLATE_PATTERNS = [
    re.compile(r"^progression for .+$", re.I),
    re.compile(r"^deload for .+$", re.I),
    re.compile(r"^volume_adjust for .+$", re.I),
]

GENERIC_FALLBACK_PATTERNS = [
    re.compile(r"auto-generated from", re.I),
    re.compile(r"^auto-generated", re.I),
]


def run_deterministic_checks(
    rec_docs: List[Dict],
    test_case: Any,
) -> tuple:
    """
    Run deterministic quality checks on recommendation documents.
    Returns (issues, penalty_points).
    Penalties capped at -30.
    """
    issues = []
    penalties = {}

    if not rec_docs:
        issues.append("No recommendation documents produced")
        return issues, 30

    for i, doc in enumerate(rec_docs):
        rec = doc.get("recommendation", {})
        prefix = f"[rec {i}] " if len(rec_docs) > 1 else ""

        # Required fields
        if not rec.get("summary"):
            issues.append(f"{prefix}Missing summary field")
            penalties["missing_summary"] = 15
        if not rec.get("rationale"):
            issues.append(f"{prefix}Missing rationale field")
            penalties["missing_rationale"] = 10
        if not rec.get("changes"):
            issues.append(f"{prefix}Missing changes array")
            penalties["missing_changes"] = 10

        # Summary is bare template
        summary = rec.get("summary", "")
        for pattern in BARE_TEMPLATE_PATTERNS:
            if pattern.match(summary):
                issues.append(
                    f"{prefix}Summary is bare template: '{summary}'"
                )
                penalties["bare_summary"] = 15
                break

        # Rationale is generic fallback
        rationale = rec.get("rationale", "")
        for pattern in GENERIC_FALLBACK_PATTERNS:
            if pattern.search(rationale):
                issues.append(
                    f"{prefix}Rationale is generic fallback: '{rationale[:60]}'"
                )
                penalties["generic_rationale"] = 10
                break

        # Exercise name validation (not hallucinated)
        training_data = test_case.training_data
        known_exercises = set()
        for ex in training_data.get("workout", {}).get("exercises", []):
            known_exercises.add(ex.get("name", "").strip().lower())
        for series in training_data.get("exercise_series", []):
            known_exercises.add(
                series.get("exercise_name", "").strip().lower()
            )

        # Check if target exercise exists in input
        target_name = ""
        target = doc.get("target", {})
        if target.get("exercise_name"):
            target_name = target["exercise_name"].strip().lower()
        elif rec.get("type") and summary:
            # Try to extract from summary
            pass

        # Weight presence in progression/deload changes
        if test_case.expected_rec_type in ("progression", "deload"):
            for change in rec.get("changes", []):
                if change.get("to") is None or change.get("to") == 0:
                    issues.append(
                        f"{prefix}Missing target weight in "
                        f"{test_case.expected_rec_type} recommendation"
                    )
                    penalties["missing_target_weight"] = 10
                    break

        # Confidence in valid range
        confidence = rec.get("confidence", 0)
        if confidence < 0.7 or confidence > 1.0:
            issues.append(
                f"{prefix}Confidence out of range: {confidence}"
            )
            penalties["confidence_range"] = 5

        # Changes have valid from/to (skip for volume_adjust which uses None)
        rec_type = rec.get("type", "")
        if rec_type != "volume_adjust":
            for change in rec.get("changes", []):
                if change.get("from") is None or change.get("to") is None:
                    issues.append(f"{prefix}Change missing from/to values")
                    penalties["invalid_change"] = 5
                    break
                if change["from"] == change["to"]:
                    issues.append(f"{prefix}Change from==to ({change['from']})")
                    penalties["noop_change"] = 5
                    break

    total_penalty = min(sum(penalties.values()), 30)
    return issues, total_penalty


# =============================================================================
# STAGE 2: LLM JUDGE
# =============================================================================

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator for a fitness AI recommendation system.

Score the following recommendation document on 4 dimensions. Be strict but fair.

## Test Case
- **Category**: {category}
- **Analyzer Type**: {analyzer_type}
- **Expected Rec Type**: {expected_rec_type}
- **Expected Signals**: {expected_signals}
- **Gold Summary**: {gold_summary}
- **Gold Rationale**: {gold_rationale}
- **Quality Requirements**: {quality_requirements}

## Input Training Data (what the analyzer received)
```json
{training_data_summary}
```

## Recommendation Document (what was produced)
```json
{rec_doc_json}
```

## Scoring Dimensions

### 1. CLARITY (max 100, weight 35%)
Is the summary+rationale immediately understandable to a gym user?
- Summary should be scannable (one line, no jargon)
- Rationale should explain WHY in 1-2 sentences
- Together they should tell a complete story
- Compare against gold_summary and gold_rationale for quality level

### 2. DATA_GROUNDING (max 100, weight 30%)
Are specific numbers/signals cited from the input training data?
- Weight values (kg) should appear when relevant
- Duration/consistency data (weeks) should be mentioned
- The expected_signals list shows what SHOULD appear
- Penalize vague language when specific numbers are available
- Penalize any numbers not present in the input data (hallucination)

### 3. ACTIONABILITY (max 100, weight 25%)
Does the user know exactly what will happen?
- For auto_pilot: what was changed, where (template name)
- For pending_review: what accepting does, which template changes
- For exercise_scoped: where to apply (next workout, template)
- Changes array should have meaningful from/to values

### 4. CONTEXTUAL_FIT (max 100, weight 10%)
Does language match the scenario?
{scenario_criteria}

## Output Format
Respond with ONLY valid JSON (no markdown fences):
{{
  "clarity": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }},
  "data_grounding": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }},
  "actionability": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }},
  "contextual_fit": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }}
}}
"""

SCENARIO_CRITERIA = {
    "auto_pilot": """
- Past tense ("Applied...", "Updated...", "Reduced...")
- States WHAT changed (specific kg values)
- States WHERE (template name)
- States WHY (signals/reasoning)
- Tone: factual notification, not a suggestion""",

    "pending_review": """
- Imperative ("Try...", "Consider...")
- States what happens on accept (template update)
- Includes template/routine context
- At-a-glance summary with specific numbers
- Tone: confident suggestion with evidence""",

    "exercise_scoped": """
- No template jargon
- Observation-first language
- Includes where to apply (next workout or template)
- Gentle for sparse data cases
- Tone: insight + actionable suggestion""",
}


def _get_scenario_criteria(category: str) -> str:
    return SCENARIO_CRITERIA.get(category, "No specific criteria.")


def _build_judge_prompt(
    test_case: Any,
    rec_docs: List[Dict],
    analyzer_output: Dict,
) -> str:
    """Build the LLM judge prompt."""
    # Summarize training data with actual numbers so judge can verify grounding
    td = test_case.training_data
    exercise_details = []
    for ex in td.get("workout", {}).get("exercises", []):
        detail = {"name": ex.get("name")}
        if ex.get("top_weight_kg"):
            detail["weight_kg"] = ex["top_weight_kg"]
        if ex.get("rep_range"):
            detail["reps"] = ex["rep_range"]
        if ex.get("avg_rir") is not None:
            detail["avg_rir"] = ex["avg_rir"]
        if ex.get("e1rm"):
            detail["e1rm"] = ex["e1rm"]
        if ex.get("working_sets"):
            detail["sets"] = ex["working_sets"]
        exercise_details.append(detail)

    series_details = []
    for s in td.get("exercise_series", []):
        weeks = s.get("weeks", [])
        sdetail = {
            "exercise": s.get("exercise_name"),
            "weeks_of_data": len(weeks),
        }
        if weeks:
            latest = weeks[-1]
            sdetail["latest_e1rm"] = latest.get("e1rm_max")
            sdetail["latest_load"] = latest.get("load_max")
            sdetail["latest_avg_rir"] = latest.get("avg_rir")
        series_details.append(sdetail)

    data_summary = {
        "exercises_in_workout": exercise_details,
        "rollup_weeks": len(td.get("recent_rollups", [])),
        "exercise_series": series_details,
    }

    return JUDGE_PROMPT_TEMPLATE.format(
        category=test_case.category,
        analyzer_type=test_case.analyzer_type,
        expected_rec_type=test_case.expected_rec_type,
        expected_signals=", ".join(test_case.expected_signals),
        gold_summary=test_case.gold_summary,
        gold_rationale=test_case.gold_rationale,
        quality_requirements="\n".join(
            f"  - {r}" for r in test_case.quality_requirements
        ),
        training_data_summary=json.dumps(data_summary, indent=2),
        rec_doc_json=json.dumps(rec_docs, indent=2, default=str),
        scenario_criteria=_get_scenario_criteria(test_case.category),
    )


def _get_access_token() -> str:
    """Get a GCP access token for Vertex AI calls."""
    import subprocess

    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    raise RuntimeError("Cannot obtain GCP access token. Run: gcloud auth login")


def _call_judge_llm(prompt: str) -> Optional[Dict]:
    """Call Gemini via Vertex AI REST API to score a recommendation."""
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
            url, json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("Judge LLM returned no candidates")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        text = ""
        for part in parts:
            if part.get("thought"):
                continue
            if "text" in part:
                text += part["text"]

        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

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


def score_recommendation(
    test_case: Any,
    rec_docs: List[Dict],
    analyzer_output: Dict,
) -> JudgeResult:
    """
    Score recommendation documents using deterministic checks + LLM judge.

    Returns JudgeResult with per-dimension scores and overall weighted score.
    """
    result = JudgeResult(test_id=test_case.id, overall_score=0.0)

    # Stage 1: Deterministic checks
    det_issues, det_penalty = run_deterministic_checks(rec_docs, test_case)
    result.deterministic_issues = det_issues

    # Stage 2: LLM judge
    prompt = _build_judge_prompt(test_case, rec_docs, analyzer_output)
    llm_scores = _call_judge_llm(prompt)

    if llm_scores:
        result.raw_llm_judgment = json.dumps(llm_scores)

        weights = {
            "clarity": 0.35,
            "data_grounding": 0.30,
            "actionability": 0.25,
            "contextual_fit": 0.10,
        }

        for dim_name, weight in weights.items():
            dim_data = llm_scores.get(dim_name, {})
            score = dim_data.get("score", 50)
            issues = dim_data.get("issues", [])

            sub_scores = {
                k: v for k, v in dim_data.items()
                if k not in ("score", "issues") and isinstance(v, (int, float))
            }

            result.dimensions[dim_name] = DimensionScore(
                name=dim_name, score=score, weight=weight,
                sub_scores=sub_scores, issues=issues,
            )
            result.llm_issues.extend(
                f"[{dim_name}] {issue}" for issue in issues
            )

        weighted_sum = sum(
            dim.score * dim.weight for dim in result.dimensions.values()
        )
        result.overall_score = max(0, weighted_sum - min(det_penalty, 30))

    else:
        logger.warning(
            "LLM judge failed for %s, using deterministic only", test_case.id
        )
        result.overall_score = max(0, 50 - det_penalty)
        for dim_name, weight in [
            ("clarity", 0.35), ("data_grounding", 0.30),
            ("actionability", 0.25), ("contextual_fit", 0.10),
        ]:
            result.dimensions[dim_name] = DimensionScore(
                name=dim_name, score=50, weight=weight,
                issues=["LLM judge unavailable"],
            )

    return result
