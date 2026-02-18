"""
Enrichment Quality Judge — two-stage scorer for exercise content quality.

Stage 1: Deterministic checks (Python) — format validation, length bounds,
         voice patterns, markdown detection
Stage 2: LLM judge (Gemini 2.5 Flash) — 4 weighted quality dimensions

Dimensions:
- Format Compliance (20%): No markdown, correct length, proper array structure
- Style Consistency (35%): Voice, sentence structure, patterns match style guide
- Content Accuracy (30%): Factually correct, specific to this exercise, useful
- Coherence (15%): Items within each field feel unified, no contradictions
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# LLM Judge config
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

# Patterns that should NOT appear in content arrays
_BOLD_RE = re.compile(r'\*\*[^*]+\*\*')
_ITALIC_RE = re.compile(r'(?<!\*)\*[^*]+\*(?!\*)')
_NUMBERED_RE = re.compile(r'^\d+[\.\)]\s')
_STEP_PREFIX_RE = re.compile(r'^step\s*\d+', re.I)
_BULLET_RE = re.compile(r'^[-\u2022*]\s+')
_HEADER_RE = re.compile(r'^#+\s')

# Voice detection patterns
_FIRST_PERSON_RE = re.compile(r'\b(I|my|we|our)\b', re.I)
_THIRD_PERSON_SUBJECT_RE = re.compile(
    r'^(the lifter|the athlete|the user|one should|he|she|they should)',
    re.I,
)


def run_deterministic_checks(
    enriched_exercise: Dict[str, Any],
    original_exercise: Dict[str, Any],
    test_case: Any,
) -> tuple:
    """
    Run deterministic quality checks on enriched exercise content.
    Returns (issues: List[str], penalty: int).
    Penalties capped at 30.
    """
    issues = []
    penalties = {}

    # Check content array fields
    for field_name, min_items, max_items, min_words, max_words in [
        ("execution_notes", 3, 6, 6, 25),
        ("common_mistakes", 2, 5, 4, 20),
        ("suitability_notes", 2, 4, 5, 25),
        ("programming_use_cases", 3, 5, 5, 25),
    ]:
        if field_name not in test_case.fields_to_check:
            continue

        items = enriched_exercise.get(field_name, [])
        if not items:
            if test_case.category != "preserve":
                issues.append(f"Missing {field_name}")
                penalties[f"missing_{field_name}"] = 10
            continue

        if not isinstance(items, list):
            issues.append(f"{field_name} is not an array")
            penalties[f"type_{field_name}"] = 10
            continue

        # Count check
        if len(items) < min_items:
            issues.append(
                f"{field_name}: only {len(items)} items (min {min_items})"
            )
            penalties[f"count_{field_name}"] = 5

        # Per-item checks
        for i, item in enumerate(items):
            if not isinstance(item, str):
                issues.append(f"{field_name}[{i}]: not a string")
                penalties[f"type_item_{field_name}"] = 5
                continue

            words = len(item.split())

            # Length check
            if words < min_words:
                issues.append(
                    f"{field_name}[{i}]: too short ({words} words, min {min_words}): "
                    f"'{item[:50]}'"
                )
                penalties[f"short_{field_name}"] = 3

            if words > max_words:
                issues.append(
                    f"{field_name}[{i}]: too long ({words} words, max {max_words}): "
                    f"'{item[:50]}...'"
                )
                penalties[f"long_{field_name}"] = 3

            # Markdown detection
            if _BOLD_RE.search(item):
                issues.append(f"{field_name}[{i}]: contains **bold** markdown")
                penalties[f"bold_{field_name}"] = 5

            if _HEADER_RE.match(item):
                issues.append(f"{field_name}[{i}]: contains # header markdown")
                penalties[f"header_{field_name}"] = 5

            # Prefix detection
            if _NUMBERED_RE.match(item):
                issues.append(
                    f"{field_name}[{i}]: starts with number prefix: '{item[:30]}'"
                )
                penalties[f"numbered_{field_name}"] = 5

            if _STEP_PREFIX_RE.match(item):
                issues.append(
                    f"{field_name}[{i}]: starts with 'Step N' prefix"
                )
                penalties[f"step_{field_name}"] = 5

            if _BULLET_RE.match(item):
                issues.append(
                    f"{field_name}[{i}]: starts with bullet marker"
                )
                penalties[f"bullet_{field_name}"] = 5

        # Voice checks for execution_notes (should be imperative/second person)
        if field_name == "execution_notes":
            for i, item in enumerate(items):
                if not isinstance(item, str):
                    continue
                if _FIRST_PERSON_RE.search(item):
                    issues.append(
                        f"execution_notes[{i}]: uses first person voice: "
                        f"'{item[:50]}'"
                    )
                    penalties["first_person_en"] = 5
                if _THIRD_PERSON_SUBJECT_RE.match(item):
                    issues.append(
                        f"execution_notes[{i}]: uses third person subject: "
                        f"'{item[:50]}'"
                    )
                    penalties["third_person_en"] = 5

        # Voice checks for common_mistakes (should NOT use "you")
        if field_name == "common_mistakes":
            for i, item in enumerate(items):
                if not isinstance(item, str):
                    continue
                if re.match(r"^you\b", item, re.I):
                    issues.append(
                        f"common_mistakes[{i}]: starts with 'you': '{item[:50]}'"
                    )
                    penalties["you_cm"] = 5

    # Description checks
    if "description" in test_case.fields_to_check:
        desc = enriched_exercise.get("description", "")
        if desc:
            if len(desc) < 50:
                issues.append(f"description too short: {len(desc)} chars (min 50)")
                penalties["short_desc"] = 5
            if len(desc) > 300:
                issues.append(f"description too long: {len(desc)} chars (max 300)")
                penalties["long_desc"] = 3
            # Should not start by repeating the exercise name
            ex_name = enriched_exercise.get("name", "").split(" (")[0].lower()
            if desc.lower().startswith(ex_name):
                issues.append("description starts by repeating the exercise name")
                penalties["name_repeat_desc"] = 3

    total_penalty = min(sum(penalties.values()), 30)
    return issues, total_penalty


# =============================================================================
# STAGE 2: LLM JUDGE
# =============================================================================

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator for exercise catalog content quality.

Score the enriched exercise content on 4 dimensions. Be strict but fair.
Focus on whether the content follows the style guide consistently.

## Test Case
- **Category**: {category} ({category_explanation})
- **Exercise**: {exercise_name}
- **Fields Being Scored**: {fields_to_check}
- **Expected Behavior**: {expected_behavior}
- **Quality Requirements**: {quality_requirements}

## Content Style Guide (the standard to evaluate against)

### execution_notes
- Voice: Second person imperative ("Keep...", "Drive...", "Brace...")
- Each item: ONE concise cue starting with action verb
- Length: 8-20 words per item, 3-6 items total
- Cover: setup, main movement, breathing/bracing

### common_mistakes
- Voice: Third person descriptive, gerund phrase ("Rounding the back...")
- Describe WHAT goes wrong, not the correction
- Length: 6-15 words per item, 2-5 items total
- No "you" or "should"

### suitability_notes
- Voice: Third person declarative, neutral, factual
- Each item: one statement about suitability
- Length: 8-20 words per item, 2-4 items total
- Include positive notes and cautions

### programming_use_cases
- Voice: Third person declarative, complete sentences ending with period
- Describe specific programming contexts
- Length: 10-20 words per item, 3-5 items total
- Vary sentence openers

### description
- Voice: Third person declarative, 1-2 sentences
- Length: 100-250 characters
- Name the movement pattern, state key benefit
- Do NOT repeat the exercise name at the start

## Gold Standard Examples (for reference)
```json
{gold_examples_json}
```

## Original Exercise (before enrichment)
```json
{original_json}
```

## Enriched Exercise (what was produced)
```json
{enriched_json}
```

## Scoring Dimensions

### 1. FORMAT_COMPLIANCE (max 100, weight 20%)
Does the output follow formatting rules?
- No markdown (bold, italic, headers)
- No numbered prefixes or bullet markers
- Array items are within length bounds
- Correct number of items per field
- description within character limits

### 2. STYLE_CONSISTENCY (max 100, weight 35%)
Does every field follow its prescribed voice and structure?
- execution_notes: all imperative, action-verb starts, second person
- common_mistakes: all gerund/descriptive, no "you"/"should"
- suitability_notes: all third person declarative
- programming_use_cases: all complete sentences with periods
- description: third person, doesn't repeat name
- MOST IMPORTANT: Would these read naturally next to the gold examples?
  If you put the enriched content and gold examples side by side, they
  should feel like they were written by the same coach.

### 3. CONTENT_ACCURACY (max 100, weight 30%)
Is the content factually correct and specific to THIS exercise?
- Movement cues are anatomically correct
- Muscles referenced match the actual exercise
- Mistakes listed are real common errors for this movement
- Content is specific (not generic advice that applies to anything)
- No hallucinated claims or dangerous advice

### 4. COHERENCE (max 100, weight 15%)
Do the items within each field feel unified?
- Consistent level of detail across items
- No contradictions between fields
- Items don't repeat each other
- Logical ordering (e.g., setup before movement)
- Appropriate scope for exercise complexity

## Output Format
Respond with ONLY valid JSON (no markdown fences):
{{
  "format_compliance": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }},
  "style_consistency": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }},
  "content_accuracy": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }},
  "coherence": {{
    "score": <0-100>,
    "issues": ["issue1"]
  }}
}}
"""

CATEGORY_EXPLANATIONS = {
    "generate": "Exercise had missing fields. Enrichment should have generated them.",
    "fix": "Exercise had bad/inconsistent content. Enrichment should have improved it.",
    "preserve": "Exercise was already good. Enrichment should have left it mostly alone.",
}


# Token cache for gcloud auth
_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0}


def _get_access_token() -> str:
    """Get GCP access token from gcloud CLI, cached for 50 minutes."""
    import subprocess

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0 and result.stdout.strip():
        _token_cache["token"] = result.stdout.strip()
        _token_cache["expires_at"] = now + 3000  # 50 min
        return _token_cache["token"]
    raise RuntimeError("Cannot obtain GCP access token. Run: gcloud auth login")


def _call_judge_llm(prompt: str) -> Optional[Dict]:
    """Call Gemini via Vertex AI REST API to score enrichment quality."""
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


def _build_judge_prompt(
    test_case: Any,
    original_exercise: Dict[str, Any],
    enriched_exercise: Dict[str, Any],
) -> str:
    """Build the LLM judge prompt."""
    # Extract only the content fields for cleaner display
    content_fields = [
        "description", "execution_notes", "common_mistakes",
        "suitability_notes", "programming_use_cases", "stimulus_tags",
    ]

    original_content = {
        k: v for k, v in original_exercise.items()
        if k in content_fields and v
    }
    enriched_content = {
        k: v for k, v in enriched_exercise.items()
        if k in content_fields and v
    }
    # Also include name for context
    enriched_content["name"] = enriched_exercise.get("name", "")
    original_content["name"] = original_exercise.get("name", "")

    return JUDGE_PROMPT_TEMPLATE.format(
        category=test_case.category,
        category_explanation=CATEGORY_EXPLANATIONS.get(
            test_case.category, ""
        ),
        exercise_name=original_exercise.get("name", "unknown"),
        fields_to_check=", ".join(test_case.fields_to_check),
        expected_behavior=test_case.expected_behavior,
        quality_requirements="\n".join(
            f"  - {r}" for r in test_case.quality_requirements
        ),
        gold_examples_json=json.dumps(
            test_case.gold_examples, indent=2
        ) if test_case.gold_examples else "N/A (use the style guide as reference)",
        original_json=json.dumps(original_content, indent=2),
        enriched_json=json.dumps(enriched_content, indent=2),
    )


# =============================================================================
# MAIN SCORER
# =============================================================================

def score_enrichment(
    test_case: Any,
    original_exercise: Dict[str, Any],
    enriched_exercise: Dict[str, Any],
    skip_llm: bool = False,
) -> JudgeResult:
    """
    Score enrichment quality using deterministic checks + LLM judge.

    Returns JudgeResult with per-dimension scores and overall weighted score.
    """
    result = JudgeResult(test_id=test_case.id, overall_score=0.0)

    # Stage 1: Deterministic checks
    det_issues, det_penalty = run_deterministic_checks(
        enriched_exercise, original_exercise, test_case,
    )
    result.deterministic_issues = det_issues

    if skip_llm:
        result.overall_score = max(0, 80 - det_penalty)
        for dim_name, weight in [
            ("format_compliance", 0.20),
            ("style_consistency", 0.35),
            ("content_accuracy", 0.30),
            ("coherence", 0.15),
        ]:
            result.dimensions[dim_name] = DimensionScore(
                name=dim_name, score=80, weight=weight,
                issues=["LLM judge skipped"],
            )
        return result

    # Stage 2: LLM judge
    prompt = _build_judge_prompt(test_case, original_exercise, enriched_exercise)
    llm_scores = _call_judge_llm(prompt)

    if llm_scores:
        result.raw_llm_judgment = json.dumps(llm_scores)

        weights = {
            "format_compliance": 0.20,
            "style_consistency": 0.35,
            "content_accuracy": 0.30,
            "coherence": 0.15,
        }

        for dim_name, weight in weights.items():
            dim_data = llm_scores.get(dim_name, {})
            score = dim_data.get("score", 50)
            dim_issues = dim_data.get("issues", [])

            sub_scores = {
                k: v for k, v in dim_data.items()
                if k not in ("score", "issues") and isinstance(v, (int, float))
            }

            result.dimensions[dim_name] = DimensionScore(
                name=dim_name, score=score, weight=weight,
                sub_scores=sub_scores, issues=dim_issues,
            )
            result.llm_issues.extend(
                f"[{dim_name}] {issue}" for issue in dim_issues
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
            ("format_compliance", 0.20),
            ("style_consistency", 0.35),
            ("content_accuracy", 0.30),
            ("coherence", 0.15),
        ]:
            result.dimensions[dim_name] = DimensionScore(
                name=dim_name, score=50, weight=weight,
                issues=["LLM judge unavailable"],
            )

    return result
