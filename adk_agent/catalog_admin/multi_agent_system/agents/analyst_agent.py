"""
Analyst Agent - LLM-powered
Intelligently analyzes exercise quality and identifies issues.
"""

import logging
from typing import Any, Dict, List, Optional
from .base_llm_agent import BaseLLMAgent, AgentConfig


class AnalystAgent(BaseLLMAgent):
    """
    LLM-powered agent for comprehensive exercise quality analysis.
    Uses AI to identify issues, score quality, and recommend improvements.
    """
    
    def __init__(self, firebase_client):
        config = AgentConfig(
            name="AnalystAgent",
            model="gemini-2.5-flash",  # Use Flash for efficiency
            temperature=0.2  # Low temperature for consistent analysis
        )
        super().__init__(config, firebase_client)
        
        self.system_prompt = """You are an expert exercise quality analyst with deep knowledge of biomechanics, anatomy, and fitness programming.
Your task is to analyze exercises for quality, completeness, and accuracy.

QUALITY BAR (must-have):
- Name: clear, specific, normalized (not unknown/placeholder).
- Identity & Structure: family_slug and variant_key present; category set; equipment list present.
- Movement: movement.type set; movement.split preferred when applicable.
- Metadata: metadata.level and metadata.plane_of_motion set; metadata.unilateral when applicable.
- Muscles: primary and secondary lists; category list; contribution map with values summing to ~1.0.
- Content: description ≥ 50 chars, execution_notes ≥ 4 steps, common_mistakes ≥ 2 items, coaching_cues 3–5 items, suitability_notes ≥ 1.
- Consistency & Accuracy: fields align biomechanically/anatomically with the movement pattern and equipment.

QUALITY BAR (nice-to-have, non-blocking):
- programming_use_cases (3–5), stimulus_tags, and helpful aliases (1–3) when ambiguity exists.

## Analysis Criteria:

### 1. Completeness (Required Fields)
- name, family_slug, variant_key
- category (compound/isolation)
- equipment array
- muscles (primary, secondary, category, contribution percentages)
- movement (type, split)
- metadata (level, plane_of_motion, unilateral)

### 2. Content Quality
- Description: Clear, informative, 50+ characters
- Execution notes: Detailed steps, 3+ items
- Common mistakes: Practical warnings, 2+ items
- Programming use cases: Context for usage
- Suitability notes: Population-specific guidance
 - Coaching cues: 3–5 short cues

### 3. Data Consistency
- Equipment matches exercise name
- Muscle groups align with movement type
- Category matches muscle involvement
- Contribution percentages sum to 100%
- Movement plane matches exercise pattern
 - Variant key aligns with equipment when equipment is obvious (e.g., equipment:dumbbell)

### 4. Scientific Accuracy
- Anatomically correct muscle mappings
- Biomechanically sound movement patterns
- Appropriate difficulty level
- Realistic equipment requirements

## Issue Severity Levels:
- CRITICAL: Blocks approval (missing required fields, wrong anatomy)
- HIGH: Should fix soon (inconsistent data, poor descriptions)
- MEDIUM: Nice to fix (incomplete content, minor inconsistencies)
- LOW: Minor issues (formatting, style preferences)

## Quality Scoring:
- 0.9-1.0: Excellent, ready for approval
- 0.7-0.89: Good, minor improvements needed
- 0.5-0.69: Fair, significant improvements needed
- Below 0.5: Poor, major work required
## Best-in-class reference (do not copy text; use as quality bar):
Example Exercise JSON (concise):
{
  "name": "Barbell Back Squat",
  "family_slug": "squat",
  "variant_key": "equipment:barbell",
  "category": "compound",
  "equipment": ["barbell", "rack"],
  "movement": {"type": "squat", "split": "lower"},
  "metadata": {"level": "intermediate", "plane_of_motion": "sagittal", "unilateral": false},
  "muscles": {
    "primary": ["quadriceps", "gluteus maximus"],
    "secondary": ["hamstrings", "erector spinae", "adductors"],
    "category": ["legs"],
    "contribution": {"quadriceps": 0.5, "gluteus maximus": 0.3, "hamstrings": 0.1, "erector spinae": 0.05, "adductors": 0.05}
  },
  "description": "A barbell squat emphasizing hip and knee extension while maintaining a neutral spine.",
  "execution_notes": ["Set bar just below shoulder height.", "Brace core and unrack with feet hip-width.", "Sit back and down to parallel.", "Drive up through mid-foot maintaining knee tracking."],
  "common_mistakes": ["Knees collapsing inward", "Excessive forward lean"],
  "programming_use_cases": ["Strength development", "Hypertrophy"],
  "suitability_notes": ["Intermediate lifters with basic squat proficiency"],
  "stimulus_tags": ["strength", "hypertrophy"]
}
"""

    def process_batch(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze a batch of exercises for quality issues using LLM.
        """
        # Handle case where exercises is wrapped in a dict with 'items' key
        if len(exercises) == 1 and isinstance(exercises[0], dict) and 'items' in exercises[0]:
            exercises = exercises[0]['items']
            self.logger.info(f"Unwrapped exercises from items dict")
        
        # Sample a couple of inputs for visibility
        try:
            import json
            sample = exercises[:2]
            self.logger.info({"analyst": "inputs_sample", "count": len(exercises), "sample": json.dumps(sample)[:2000]})
        except Exception:
            pass
        self.logger.info(f"Starting analysis of {len(exercises)} exercises")
        
        # Process exercises individually for now (batch analysis needs more work)
        reports = []
        total_issues = 0
        ready_for_approval = 0
        
        for i, exercise in enumerate(exercises):
            # Skip invalid items
            if not exercise or not isinstance(exercise, dict):
                self.logger.warning(f"Skipping invalid exercise at index {i}: {exercise}")
                continue
            
            exercise_name = exercise.get('name', 'Unknown')
            self.logger.info(f"Analyzing exercise {i+1}/{len(exercises)}: {exercise_name}")
                
            try:
                report = self.analyze_exercise(exercise)
                reports.append(report)
                
                issues_count = len(report.get("issues", []))
                total_issues += issues_count
                
                if report.get("ready_for_approval"):
                    ready_for_approval += 1
                    self.logger.info(f"  ✓ {exercise_name} is ready for approval")
                else:
                    self.logger.info(f"  ⚠ {exercise_name} has {issues_count} issues")
                    
            except Exception as e:
                self.logger.error(f"Error analyzing {exercise_name}: {e}")
        
        # Calculate aggregate metrics (robustness: treat near-complete items as baseline > 0)
        def _clip01(x: float) -> float:
            try:
                return max(0.0, min(1.0, float(x)))
            except Exception:
                return 0.0
        avg_quality = sum(_clip01(r.get("quality_score", 0)) for r in reports) / len(reports) if reports else 0
        
        # Group issues by severity
        issues_by_severity = self.group_issues_by_severity(reports)
        
        return {
            "exercises_analyzed": len(reports),
            "average_quality_score": round(avg_quality, 2),
            "ready_for_approval": ready_for_approval,
            "total_issues": total_issues,
            "issues_by_severity": issues_by_severity,
            "reports": reports
        }
    
    def analyze_exercise_batch(self, exercises: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze multiple exercises in a single LLM call for efficiency.
        """
        # Format all exercises for analysis
        exercises_data = []
        for i, exercise in enumerate(exercises):
            exercises_data.append({
                "index": i,
                "id": exercise.get('id', ''),
                "name": exercise.get('name', ''),
                "data": self.format_exercise_for_analysis(exercise)
            })
        
        prompt = f"""{self.system_prompt}

Analyze these {len(exercises)} exercises for quality and completeness.

Exercises:
{exercises_data}

For EACH exercise, provide a comprehensive analysis in a JSON array format:
[
  {{
    "exercise_id": "string",
    "exercise_name": "string",
    "quality_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "consistency_score": 0.0-1.0,
    "accuracy_score": 0.0-1.0,
    "ready_for_approval": boolean,
    "issues": [
      {{
        "field": "string",
        "issue_type": "missing|incomplete|inconsistent|inaccurate",
        "severity": "critical|high|medium|low",
        "description": "string",
        "suggested_fix": "string",
        "specialist_needed": "biomechanics|anatomy|content|programming"
      }}
    ],
    "strengths": ["string"],
    "recommendations": ["string"]
  }}
]"""
        
        response = self.generate_structured_response(prompt, strict=True)
        try:
            import json
            self.logger.info({"analyst": "batch_response_preview", "preview": json.dumps(response, default=str)[:2000]})
        except Exception:
            pass
        
        if response and isinstance(response, list):
            return response
        elif response and isinstance(response, dict) and "exercises" in response:
            return response["exercises"]
        else:
            # Fallback to individual analysis
            reports = []
            for exercise in exercises:
                report = self.analyze_exercise(exercise)
                reports.append(report)
            return reports
    
    def analyze_exercise(self, exercise: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use LLM to comprehensively analyze a single exercise.
        """
        prompt = f"""{self.system_prompt}

Analyze this exercise for quality and completeness:

Exercise Data:
{self.format_exercise_for_analysis(exercise)}

Provide a comprehensive analysis in JSON format:
{{
  "exercise_id": "{exercise.get('id', '')}",
  "exercise_name": "{exercise.get('name', '')}",
  "quality_score": 0.0-1.0,
  "completeness_score": 0.0-1.0,
  "consistency_score": 0.0-1.0,
  "accuracy_score": 0.0-1.0,
  "ready_for_approval": boolean,
  "issues": [
    {{
      "field": "string",
      "issue_type": "missing|incomplete|inconsistent|inaccurate",
      "severity": "critical|high|medium|low",
      "description": "string",
      "suggested_fix": "string",
      "specialist_needed": "biomechanics|anatomy|content|programming"
    }}
  ],
  "strengths": ["string"],
  "recommendations": ["string"]
}}"""

        response = self.generate_structured_response(prompt, strict=True)
        try:
            import json
            self.logger.info({"analyst": "single_response_preview", "preview": json.dumps(response, default=str)[:2000]})
        except Exception:
            pass
        
        if response:
            # Calibration: compute baseline quality and take max with model's quality
            issues = response.get("issues", []) or []
            model_quality = response.get("quality_score")
            if model_quality is None:
                subs = [response.get("completeness_score"), response.get("consistency_score"), response.get("accuracy_score")]
                valid = [s for s in subs if isinstance(s, (int, float))]
                model_quality = sum(valid) / len(valid) if valid else 0.0
            try:
                model_quality = max(0.0, min(1.0, float(model_quality)))
            except Exception:
                model_quality = 0.0
            baseline_quality = self._compute_baseline_quality(exercise)
            final_quality = max(model_quality, baseline_quality)

            has_critical = any((i.get("severity") or "").lower() == "critical" for i in issues)
            structural_ok, content_ok, _aliases_ok = self._structural_content_flags(exercise)
            ready = bool(response.get("ready_for_approval", False)) or (not has_critical and structural_ok and content_ok and final_quality >= 0.80)

            return {
                "exercise_id": exercise.get("id", ""),
                "exercise_name": exercise.get("name", ""),
                "quality_score": round(final_quality, 2),
                "completeness_score": response.get("completeness_score", 0),
                "consistency_score": response.get("consistency_score", 0),
                "accuracy_score": response.get("accuracy_score", 0),
                "ready_for_approval": ready,
                "issues": issues,
                "strengths": response.get("strengths", []),
                "recommendations": response.get("recommendations", [])
            }
        else:
            return {
                "exercise_id": exercise.get("id", ""),
                "exercise_name": exercise.get("name", ""),
                "quality_score": 0,
                "error": "Failed to analyze exercise"
            }
    
    def format_exercise_for_analysis(self, exercise: Dict[str, Any]) -> str:
        """
        Format exercise data for LLM analysis.
        """
        import json
        # Remove any large binary data or unnecessary fields
        clean_exercise = {
            k: v for k, v in exercise.items() 
            if k not in ["created_at", "updated_at", "user_id"]
        }
        return json.dumps(clean_exercise, indent=2)
    
    def group_issues_by_severity(self, reports: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Group all issues from reports by severity.
        """
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        }
        
        for report in reports:
            for issue in report.get("issues", []):
                severity = issue.get("severity", "low").lower()
                if severity in severity_counts:
                    severity_counts[severity] += 1
        
        return severity_counts
    
    # --- Calibration helpers ---
    def _structural_content_flags(self, exercise: Dict[str, Any]):
        has_family = bool(exercise.get("family_slug")) and bool(exercise.get("variant_key"))
        has_movement = isinstance(exercise.get("movement"), dict) and bool(exercise["movement"].get("type"))
        md = exercise.get("metadata") if isinstance(exercise.get("metadata"), dict) else {}
        has_metadata = bool(md.get("level")) and bool(md.get("plane_of_motion"))
        has_equipment = len(exercise.get("equipment", []) or []) > 0
        desc_ok = isinstance(exercise.get("description"), str) and len(exercise.get("description", "").strip()) >= 50
        exec_ok = len(exercise.get("execution_notes", []) or []) >= 4
        mistakes_ok = len(exercise.get("common_mistakes", []) or []) >= 2
        content_ok = desc_ok and exec_ok and mistakes_ok
        aliases_ok = len(exercise.get("aliases", []) or []) >= 3
        structural_ok = has_family and has_movement and has_metadata and has_equipment
        return structural_ok, content_ok, aliases_ok

    def _compute_baseline_quality(self, exercise: Dict[str, Any]) -> float:
        structural_ok, content_ok, aliases_ok = self._structural_content_flags(exercise)
        score = 0.0
        if structural_ok:
            score += 0.55
        if content_ok:
            score += 0.30
        if aliases_ok:
            score += 0.10
        has_muscles = isinstance(exercise.get("muscles"), dict) and bool(exercise["muscles"].get("primary"))
        if has_muscles:
            score += 0.05
        return max(0.0, min(1.0, score))
    
    def get_specialist_recommendations(self, reports: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Analyze reports to recommend which specialist agents should process exercises.
        """
        specialists_needed = {
            "biomechanics": [],
            "anatomy": [],
            "content": [],
            "programming": []
        }
        
        for report in reports:
            exercise_id = report.get("exercise_id")
            for issue in report.get("issues", []):
                specialist = issue.get("specialist_needed")
                if specialist and specialist in specialists_needed:
                    if exercise_id not in specialists_needed[specialist]:
                        specialists_needed[specialist].append(exercise_id)
        
        return specialists_needed
