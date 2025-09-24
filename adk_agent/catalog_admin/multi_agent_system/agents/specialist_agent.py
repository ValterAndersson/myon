"""
Specialist Agent - LLM-powered
A unified specialist that can take on different expert roles to improve exercises.
"""

import logging
from typing import Any, Dict, List, Optional
from enum import Enum
from .base_llm_agent import BaseLLMAgent, AgentConfig


class SpecialistRole(Enum):
    """Different specialist roles the agent can assume"""
    CREATOR = "creator"
    BIOMECHANICS = "biomechanics"
    ANATOMY = "anatomy"
    CONTENT = "content"
    PROGRAMMING = "programming"


class SpecialistAgent(BaseLLMAgent):
    """
    LLM-powered specialist agent that can assume different expert roles.
    Uses AI to intelligently improve specific aspects of exercises.
    """
    
    def __init__(self, firebase_client, role: SpecialistRole):
        config = AgentConfig(
            name=f"SpecialistAgent_{role.value}",
            model="gemini-2.5-flash",  # Use Flash for all specialists for efficiency
            temperature=0.3 if role == SpecialistRole.ANATOMY else 0.4
        )
        super().__init__(config, firebase_client)
        self.role = role
        self.firebase_client = firebase_client  # Store firebase_client directly
        self.system_prompt = self._get_role_prompt(role)
    
    def _get_role_prompt(self, role: SpecialistRole) -> str:
        """Get the appropriate system prompt for the specialist role."""
        
        prompts = {
            SpecialistRole.CREATOR: """You are an expert exercise designer with deep knowledge of fitness and exercise science.
Your task is to create new exercises based on identified gaps in the catalog.

## Your Expertise:
- Exercise biomechanics and movement patterns
- Equipment variations and progressions
- Sport-specific and rehabilitation exercises
- Creative exercise variations

## When Creating Exercises:
1. Ensure anatomical accuracy
2. Consider equipment availability
3. Define clear movement patterns
4. Specify appropriate difficulty levels
5. Create comprehensive initial drafts

## Output Requirements:
Generate complete exercise definitions with all required fields.""",

            SpecialistRole.BIOMECHANICS: """You are a biomechanics specialist with expertise in human movement science.
Your task is to ensure exercises are correctly categorized from a movement perspective.

QUALITY BAR (must-have):
- Name not placeholder; family_slug + variant_key present; category set; equipment present.
- movement.type set; metadata.level + plane_of_motion set; unilateral when applicable.
- Muscles lists accurate; contribution sums ~1.0.
- Content present (description, execution_notes, common_mistakes, coaching_cues, suitability_notes) and consistent with biomechanics.

## Your Expertise:
- Movement patterns (push, pull, squat, hinge, lunge, carry, rotation)
- Planes of motion (sagittal, frontal, transverse)
- Kinetic chains and force vectors
- Joint actions and ranges of motion
- Stability and mobility requirements

## Analysis Focus:
1. Validate movement.type and set movement.split (upper|lower|full)
2. Set metadata.plane_of_motion and metadata.unilateral where applicable
3. Verify equipment appropriateness; adjust category to compound|isolation accordingly
4. Set appropriate difficulty levels in metadata.level
5. If equipment is clearly identified (e.g., dumbbell, barbell, cable), set variant_key to "equipment:<name>"

## Key Principles:
- Movement quality over load
- Joint-friendly exercise selection
- Progressive overload considerations
- Functional movement patterns""",

            SpecialistRole.ANATOMY: """You are an anatomy specialist with expertise in musculoskeletal science.
Your task is to ensure accurate muscle involvement and contribution profiles.

QUALITY BAR (must-have):
- Name not placeholder; family_slug + variant_key present; category set; equipment present.
- movement.type set; metadata.level + plane_of_motion set; unilateral when applicable.
- Muscles lists accurate; contribution sums ~1.0.
- Content present (description, execution_notes, common_mistakes, coaching_cues, suitability_notes) and consistent with anatomy.

## Your Expertise:
- Muscle anatomy and attachments
- Prime movers vs synergists vs stabilizers
- Muscle fiber types and recruitment
- Contribution percentages in movements
- Muscle group categorization

## Analysis Focus:
1. Identify all involved muscles accurately
2. Distinguish primary from secondary muscles
3. Calculate realistic contribution percentages (must sum to 100%)
4. Assign correct muscle categories
5. Consider muscle length-tension relationships

## Anatomical Accuracy:
- Use proper anatomical terminology
- Consider joint angles and muscle mechanics
- Account for individual variations
- Base on EMG and biomechanical research when possible""",

            SpecialistRole.CONTENT: """You are a fitness content specialist and certified personal trainer.
Your task is to create clear, educational, and engaging exercise content.

QUALITY BAR (must-have):
- Name not placeholder; family_slug + variant_key present; category set; equipment present.
- movement.type set; metadata.level + plane_of_motion set; unilateral when applicable.
- Muscles lists present; contribution sums ~1.0.
- Content must meet bar: description ≥ 50 chars; execution_notes ≥ 4; common_mistakes ≥ 2; coaching_cues 3–5; suitability_notes ≥ 1.

## Your Expertise:
- Exercise instruction and cueing
- Common form errors and corrections
- Progressive teaching methods
- Client communication
- Safety considerations

## Content Requirements (ONLY use these valid fields):
1. description: Clear, concise, informative (50+ chars)
2. execution_notes: Step-by-step instructions (4-7 steps, array of strings)
3. common_mistakes: Practical warnings (2-5 items, array of strings)
4. programming_use_cases: How to use in programs (3-5 items, array of strings)
5. suitability_notes: Who it's good for and safety (array of strings)

## Writing Style:
- Clear and accessible language
- Action-oriented instructions
- Positive and encouraging tone
- Focus on form and technique
- Include breathing patterns""",

            SpecialistRole.PROGRAMMING: """You are a strength and conditioning specialist with expertise in program design.
Your task is to provide programming context and training recommendations.

QUALITY BAR (must-have):
- Name not placeholder; family_slug + variant_key present; category set; equipment present.
- movement.type set; metadata.level + plane_of_motion set; unilateral when applicable.
- Muscles lists present; contribution sums ~1.0.
- Content present and consistent; programming_use_cases (3–5) recommended but non-blocking.

## Your Expertise:
- Periodization and programming
- Training adaptations and stimulus
- Population-specific modifications
- Exercise selection criteria
- Recovery and fatigue management

## Analysis Focus:
1. Define appropriate use cases
2. Specify training stimulus (hypertrophy, strength, power, endurance)
3. Recommend rep ranges and intensities
4. Identify suitable populations
5. Suggest progressions and regressions
6. Consider training frequency and volume

## Programming Principles:
- Progressive overload
- Specificity of training
- Individual differences
- Recovery requirements
- Risk-benefit analysis"""
        }
        
        return prompts.get(role, "You are a fitness specialist.")
    
    def process_batch(self, items: List[Dict[str, Any]], task_description: str = "") -> Dict[str, Any]:
        """
        Process a batch of items based on the specialist role.
        """
        # Handle case where items is wrapped in a dict with 'items' key
        if len(items) == 1 and isinstance(items[0], dict) and 'items' in items[0]:
            items = items[0]['items']
            self.logger.info(f"Unwrapped {len(items)} items from dict")
        
        if self.role == SpecialistRole.CREATOR:
            return self.create_exercises(items)
        else:
            return self.improve_exercises(items)
    
    def create_exercises(self, gaps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create new exercises from identified gaps.
        """
        created = []
        failed = []
        
        for gap in gaps:
            try:
                exercise = self.generate_exercise(gap)
                if exercise:
                    # Create via Firebase
                    result = self.firebase_client.post(
                        "ensureExerciseExists",
                        {"exercise": exercise}
                    )
                    
                    if result and result.get("data"):
                        created.append({
                            "id": result["data"].get("id"),
                            "name": exercise["name"],
                            "gap": gap
                        })
                        self.logger.info(f"Created: {exercise['name']}")
                else:
                    failed.append(gap)
                    
            except Exception as e:
                self.logger.error(f"Failed to create exercise: {e}")
                failed.append(gap)
        
        return {
            "exercises_created": len(created),
            "exercises_failed": len(failed),
            "created": created,
            "failed": failed
        }
    
    def improve_exercises(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Improve exercises based on specialist role.
        """
        improved = []
        skipped = []
        
        for exercise in exercises:
            # Skip invalid items
            if not exercise or not isinstance(exercise, dict):
                self.logger.warning(f"Skipping invalid exercise: {exercise}")
                continue
            
            # Support wrapped payload: { "exercise": {..}, "target_issues": [...] }
            target_issues = []
            if "exercise" in exercise and isinstance(exercise["exercise"], dict):
                target_issues = exercise.get("target_issues", []) or []
                exercise = exercise["exercise"]
            
            try:
                improvements = self.analyze_and_improve(exercise, target_issues)
                if improvements and improvements.get("changes_made"):
                    # Apply improvements via Firebase
                    self.apply_improvements(exercise, improvements)
                    improved.append(improvements)
                else:
                    skipped.append({
                        "id": exercise.get("id", ""),
                        "name": exercise.get("name", "Unknown"),
                        "reason": "No improvements needed"
                    })
                    
            except Exception as e:
                self.logger.error(f"Error improving {exercise.get('name', 'Unknown')}: {e}")
                skipped.append({
                    "id": exercise.get("id", ""),
                    "name": exercise.get("name", "Unknown"),
                    "reason": str(e)
                })
        
        return {
            "exercises_improved": len(improved),
            "exercises_skipped": len(skipped),
            "improvements": improved,
            "skipped": skipped
        }
    
    def generate_exercise(self, gap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate a new exercise based on identified gap.
        """
        prompt = f"""{self.system_prompt}

Create a comprehensive exercise based on this identified gap:
- Exercise Name: {gap.get('exercise_name', 'Unknown')}
- User Intent: {gap.get('user_intent', 'General fitness')}
- Confidence: {gap.get('confidence', 0)}
- Reasoning: {gap.get('reasoning', '')}
- Similar Exercises: {gap.get('similar_exercises', [])}

Generate a complete JSON exercise object with ALL required fields:
{{
  "name": "string",
  "family_slug": "string",
  "variant_key": "string",
  "category": "compound|isolation",
  "equipment": ["string"],
  "movement": {{
    "type": "push|pull|squat|hinge|lunge|carry|rotation|core",
    "split": "upper|lower|full"
  }},
  "muscles": {{
    "primary": ["string"],
    "secondary": ["string"],
    "category": ["string"],
    "contribution": {{"muscle_name": 0.0-1.0}}
  }},
  "metadata": {{
    "level": "beginner|intermediate|advanced",
    "plane_of_motion": "sagittal|frontal|transverse",
    "unilateral": boolean
  }},
  "description": "string (detailed, 50+ chars)",
  "execution_notes": ["string (4-7 steps)"],
  "common_mistakes": ["string (2-5 items)"],
  "programming_use_cases": ["string"],
  "suitability_notes": ["string"],
  "stimulus_tags": ["hypertrophy|strength|power|endurance"],
  "status": "draft",
  "version": 1
}}

Ensure contribution percentages sum to 100%."""

        response = self.generate_structured_response(prompt)
        
        if response and response.get("name"):
            # Validate and clean response
            response["status"] = "draft"
            response["version"] = 1
            
            # Ensure contribution sums to 100%
            if "muscles" in response and "contribution" in response["muscles"]:
                self.normalize_contributions(response["muscles"]["contribution"])
            
            return response
        
        return None
    
    def analyze_and_improve(self, exercise: Dict[str, Any], target_issues: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze exercise and suggest improvements based on role.
        """
        role_prompts = {
            SpecialistRole.BIOMECHANICS: """Analyze biomechanics and suggest improvements for:
- movement.type and movement.split
- metadata.plane_of_motion
- metadata.unilateral
- metadata.level
- category validation
- equipment appropriateness""",
            
            SpecialistRole.ANATOMY: """Analyze anatomy and suggest improvements for:
- muscles.primary (accurate list)
- muscles.secondary (accurate list)
- muscles.category (muscle groups)
- muscles.contribution (percentages summing to 100%)""",
            
            SpecialistRole.CONTENT: """Analyze content and suggest improvements for:
- description (clear, informative, 50+ chars)
- execution_notes (4-7 detailed steps)
- common_mistakes (2-5 practical warnings)
- coaching_cues (3-5 helpful cues)""",
            
            SpecialistRole.PROGRAMMING: """Analyze programming aspects and suggest improvements for:
- programming_use_cases (when to use)
- suitability_notes (who it's for)
- stimulus_tags (training adaptations)
- suggested rep ranges and intensities
- progressions and regressions"""
        }
        
        # Style seed to preserve diversity while keeping determinism across runs
        seed_source = exercise.get('id') or exercise.get('name', '')
        try:
            style_seed = sum(ord(c) for c in str(seed_source)) % 7
        except Exception:
            style_seed = 0
        
        style_profiles = [
            "Concise cues; action-first sentences; include breathing pattern once.",
            "Coach-like tone; emphasize setup and bracing; avoid redundant words.",
            "Technical tone; name joints and planes briefly; keep steps short.",
            "Form-focused; common mistakes called out; end with tempo guidance.",
            "Athletic tone; powerful verbs; stress spinal neutrality.",
            "Beginner-friendly; simpler words; safety emphasis upfront.",
            "PT-informed; joint-friendly alternatives; emphasize pain-free ROM.",
        ]
        selected_style = style_profiles[style_seed]
        
        # Cross-role minimal-change directive
        minimal_change_directive = "Preserve current tone and specifics; improve minimally; do not rewrite fields that are already adequate."
        
        # Focus list from Analyst (if provided)
        issues_str = "\n".join([
            f"- field: {i.get('field','')}; type: {i.get('issue_type','')}; severity: {i.get('severity','')}; desc: {i.get('description','')}"
            for i in (target_issues or [])
        ])

        prompt = f"""{self.system_prompt}

{role_prompts.get(self.role, "Analyze and improve this exercise:")}

Style & consistency directives (profile #{style_seed}):
- {selected_style}
- {minimal_change_directive}
- Do not homogenize language across exercises; vary phrasing consistent with this profile.
- If no meaningful improvements, return changes_made=false.

Target issues to address (from Analyst):
{issues_str if issues_str else "(none provided)"}

Only propose changes to your allowed fields for this role. If the target issues do not relate to your fields, return changes_made=false.

Current Exercise Data:
{self.format_exercise(exercise)}

Provide improvements in JSON format:
{{
  "exercise_id": "{exercise.get('id', '')}",
  "exercise_name": "{exercise.get('name', '')}",
  "changes_made": boolean,
  "improvements": {{}},
  "reasoning": "string",
  "confidence": 0.0-1.0
}}

The "improvements" object should contain only the fields that need updating."""

        response = self.generate_structured_response(prompt)
        
        if response:
            return {
                "exercise_id": exercise.get("id", ""),
                "exercise_name": exercise.get("name", ""),
                "role": self.role.value,
                "changes_made": response.get("changes_made", False),
                "improvements": response.get("improvements", {}),
                "reasoning": response.get("reasoning", ""),
                "confidence": response.get("confidence", 0.8)
            }
        
        return {
            "exercise_id": exercise.get("id", ""),
            "exercise_name": exercise.get("name", ""),
            "changes_made": False
        }
    
    def apply_improvements(self, exercise: Dict[str, Any], improvements: Dict[str, Any]):
        """
        Apply improvements to exercise via Firebase.
        """
        if not improvements.get("changes_made") or not improvements.get("improvements"):
            return
        
        try:
            # Per-role allowlists: specialists can only write owned fields
            allowed_fields_by_role = {
                SpecialistRole.BIOMECHANICS: {"movement", "metadata", "category", "equipment", "variant_key"},
                SpecialistRole.ANATOMY: {"muscles"},
                SpecialistRole.CONTENT: {"description", "execution_notes", "common_mistakes", "coaching_cues"},
                SpecialistRole.PROGRAMMING: {"programming_use_cases", "suitability_notes", "stimulus_tags"},
                SpecialistRole.CREATOR: {"name", "family_slug", "variant_key", "category", "equipment", "movement", "muscles", "metadata", "description", "execution_notes", "common_mistakes", "programming_use_cases", "suitability_notes", "stimulus_tags", "status", "version"},
            }
            allowed_fields = allowed_fields_by_role.get(self.role, set())

            # Start with identity + fetch fresh name to avoid alias conflicts
            update_data: Dict[str, Any] = {}
            current_name = exercise.get("name")
            if exercise.get("id") and hasattr(self, "firebase_client") and self.firebase_client:
                try:
                    fetched = self.firebase_client.post("getExercise", {"exerciseId": exercise["id"]})
                    if fetched and (fetched.get("ok") or fetched.get("success")):
                        ex_data = fetched.get("data", {})
                        # Handle both shapes: { data: { exercise: {...} } } or { data: {...} }
                        ex_obj = ex_data.get("exercise") if isinstance(ex_data, dict) else None
                        if not ex_obj and isinstance(ex_data, dict):
                            ex_obj = ex_data
                        if ex_obj and isinstance(ex_obj, dict):
                            current_name = ex_obj.get("name") or current_name
                            # Also carry current family/variant if available
                            if ex_obj.get("family_slug"):
                                update_data["family_slug"] = ex_obj["family_slug"]
                            if ex_obj.get("variant_key"):
                                update_data["variant_key"] = ex_obj["variant_key"]
                except Exception as _:
                    pass
            
            if not current_name:
                # Without a valid name, server will reject payload
                self.logger.warning("Skipping update due to missing name after fetch")
                return
            
            update_data["name"] = current_name
            
            # Apply only allowed improvements
            for key, value in improvements["improvements"].items():
                if key in allowed_fields:
                    update_data[key] = value
                elif key in {"movement", "metadata", "muscles"} and isinstance(value, dict) and key in allowed_fields:
                    # Defensive branch; already covered by allowed_fields
                    update_data[key] = value
            
            # Remove None values and system fields
            clean_data = {k: v for k, v in update_data.items() 
                         if v is not None and k not in ["_debug_project_id", "updated_at", "created_at", "name_slug"]}

            # Sanitize payload to match server schema expectations
            clean_data = self._sanitize_update_payload(clean_data, self.role)

            # Ensure contribution percentages sum to 100% if updated (post-sanitization)
            if "muscles" in clean_data and isinstance(clean_data["muscles"], dict) and "contribution" in clean_data["muscles"] and isinstance(clean_data["muscles"]["contribution"], dict):
                self.normalize_contributions(clean_data["muscles"]["contribution"])
            
            # Choose endpoint by field support: prefer refine; upsert only when required and safe
            result = None
            refine_supported = {"name", "movement", "equipment", "muscles", "metadata", "execution_notes", "common_mistakes", "programming_use_cases"}
            clean_keys = set(clean_data.keys())
            unsupported_keys = clean_keys - refine_supported
            needs_upsert = len(unsupported_keys) > 0

            # If upsert would be required but variant/family missing, fall back to refine-only to avoid server rejection
            has_family_variant = bool(clean_data.get("family_slug")) and bool(clean_data.get("variant_key"))

            if exercise.get("id") and (not needs_upsert or not has_family_variant):
                # Refine path (drop unsupported keys if any)
                refine_updates = {k: v for k, v in clean_data.items() if k in refine_supported}
                if unsupported_keys and not has_family_variant:
                    self.logger.info(
                        {
                            "specialist": "downgrade_to_refine",
                            "role": self.role.value,
                            "reason": "missing family_slug/variant_key for upsert",
                            "dropped_keys": sorted(list(unsupported_keys))
                        }
                    )
                if refine_updates:
                    result = self.firebase_client.post(
                        "refineExercise",
                        {"exercise_id": exercise["id"], "updates": refine_updates},
                    )
                else:
                    # Nothing refinable; skip
                    self.logger.info({"specialist": "no_refinable_updates", "role": self.role.value})
                    return
            
            if needs_upsert and has_family_variant:
                payload = dict(clean_data)
                if exercise.get("id"):
                    payload["id"] = exercise["id"]
                # optional trace logging
                import os
                if os.getenv("TRACE_WRITES") == "1":
                    self.logger.info(f"[TRACE] upsertExercise payload: {payload}")
                result = self.firebase_client.post("upsertExercise", {"exercise": payload})
                if os.getenv("TRACE_WRITES") == "1":
                    self.logger.info(f"[TRACE] upsertExercise response: {result}")
            
            if result and result.get("data"):
                # Summarize exact changes for QC
                changed_keys = [k for k in clean_data.keys() if k not in {"id", "name"}]
                summary: Dict[str, Any] = {
                    "exercise_id": exercise.get("id"),
                    "name": exercise.get("name"),
                    "role": self.role.value,
                    "confidence": improvements.get("confidence", 0),
                    "changed_keys": changed_keys,
                }
                # Nested summaries
                if "movement" in clean_data and isinstance(clean_data["movement"], dict):
                    summary["movement_fields"] = sorted(list(clean_data["movement"].keys()))
                if "metadata" in clean_data and isinstance(clean_data["metadata"], dict):
                    summary["metadata_fields"] = sorted(list(clean_data["metadata"].keys()))
                if "muscles" in clean_data and isinstance(clean_data["muscles"], dict):
                    m = clean_data["muscles"]
                    summary["muscles_fields"] = sorted([k for k in m.keys() if k != "contribution"]) + (["contribution"] if "contribution" in m else [])
                if "execution_notes" in clean_data:
                    summary["execution_notes_len"] = len(clean_data.get("execution_notes", []) or [])
                if "common_mistakes" in clean_data:
                    summary["common_mistakes_len"] = len(clean_data.get("common_mistakes", []) or [])
                if "programming_use_cases" in clean_data:
                    summary["programming_use_cases_len"] = len(clean_data.get("programming_use_cases", []) or [])
                self.logger.info({"specialist": "improvement_applied", **summary})
            
        except Exception as e:
            self.logger.error(f"Failed to apply improvements: {e}")
    
    def format_exercise(self, exercise: Dict[str, Any]) -> str:
        """Format exercise for prompt."""
        import json
        # Remove unnecessary fields
        clean = {k: v for k, v in exercise.items() if k not in ["created_at", "updated_at", "id"]}
        return json.dumps(clean, indent=2)
    
    def normalize_contributions(self, contributions: Dict[str, float]):
        """Ensure contribution percentages sum to 100%."""
        if not contributions:
            return
        
        total = sum(contributions.values())
        if total > 0 and abs(total - 1.0) > 0.01:
            # Normalize
            for muscle in contributions:
                contributions[muscle] = round(contributions[muscle] / total, 2)

    def _sanitize_update_payload(self, data: Dict[str, Any], role: SpecialistRole) -> Dict[str, Any]:
        """Coerce types and filter fields to match ExerciseUpsertSchema expectations."""
        def as_str(x: Any) -> str:
            return str(x).strip() if isinstance(x, (str, int, float)) else ""

        def as_str_list(arr: Any, max_len: int = 50) -> List[str]:
            if not isinstance(arr, list):
                return []
            out: List[str] = []
            for item in arr[:max_len]:
                s = as_str(item)
                if s:
                    out.append(s)
            return out

        allowed_levels = {"beginner", "intermediate", "advanced"}
        allowed_planes = {"sagittal", "frontal", "transverse"}
        allowed_movement_types = {"push", "pull", "squat", "hinge", "lunge", "carry", "rotation", "core", "legs", "other", "row"}
        allowed_splits = {"upper", "lower", "full"}
        allowed_categories = {"compound", "isolation", "general"}

        sanitized: Dict[str, Any] = {}

        # Identity/context
        if data.get("id"):
            sanitized["id"] = as_str(data["id"]) or data["id"]
        if data.get("name"):
            sanitized["name"] = as_str(data["name"]) or data["name"]
        if data.get("family_slug"):
            sanitized["family_slug"] = as_str(data["family_slug"]).lower().replace(" ", "_")
        if data.get("variant_key"):
            sanitized["variant_key"] = as_str(data["variant_key"]).lower()

        # Category
        if "category" in data:
            cat = as_str(data["category"]).lower()
            sanitized["category"] = cat if cat in allowed_categories else "general"

        # Equipment
        if "equipment" in data:
            sanitized["equipment"] = as_str_list(data["equipment"])[:20]

        # Movement
        if "movement" in data and isinstance(data["movement"], dict):
            mv = data["movement"]
            mv_out: Dict[str, Any] = {}
            if "type" in mv:
                mtype = as_str(mv["type"]).lower()
                mv_out["type"] = mtype if mtype in allowed_movement_types else ("other" if mtype else "other")
            if "split" in mv:
                msplit = as_str(mv["split"]).lower()
                if msplit in allowed_splits:
                    mv_out["split"] = msplit
            if mv_out:
                sanitized["movement"] = mv_out

        # Metadata
        if "metadata" in data and isinstance(data["metadata"], dict):
            md = data["metadata"]
            md_out: Dict[str, Any] = {}
            if "level" in md:
                lvl = as_str(md["level"]).lower()
                md_out["level"] = lvl if lvl in allowed_levels else None
            if "plane_of_motion" in md:
                pom = as_str(md["plane_of_motion"]).lower()
                md_out["plane_of_motion"] = pom if pom in allowed_planes else None
            if "unilateral" in md:
                md_out["unilateral"] = bool(md["unilateral"]) if isinstance(md["unilateral"], (bool, int)) else None
            # Drop Nones
            md_out = {k: v for k, v in md_out.items() if v is not None}
            if md_out:
                sanitized["metadata"] = md_out

        # Muscles
        if "muscles" in data and isinstance(data["muscles"], dict):
            mu = data["muscles"]
            mu_out: Dict[str, Any] = {}
            if "primary" in mu:
                mu_out["primary"] = as_str_list(mu["primary"])[:10]
            if "secondary" in mu:
                mu_out["secondary"] = as_str_list(mu["secondary"])[:15]
            if "category" in mu:
                mu_out["category"] = as_str_list(mu["category"])[:10]
            if "contribution" in mu and isinstance(mu["contribution"], dict):
                contrib = {}
                for k, v in mu["contribution"].items():
                    try:
                        fv = float(v)
                    except Exception:
                        continue
                    if fv < 0:
                        continue
                    contrib[as_str(k)] = fv
                if contrib:
                    self.normalize_contributions(contrib)
                    mu_out["contribution"] = contrib
            if mu_out:
                sanitized["muscles"] = mu_out

        # Content fields
        if "description" in data and isinstance(data["description"], str):
            desc = data["description"].strip()
            if desc:
                sanitized["description"] = desc
        if "execution_notes" in data:
            sanitized["execution_notes"] = as_str_list(data["execution_notes"])[:10]
        if "common_mistakes" in data:
            sanitized["common_mistakes"] = as_str_list(data["common_mistakes"])[:10]

        # Programming fields
        if "programming_use_cases" in data:
            sanitized["programming_use_cases"] = as_str_list(data["programming_use_cases"])[:10]
        if "suitability_notes" in data:
            sanitized["suitability_notes"] = as_str_list(data["suitability_notes"])[:10]
        if "stimulus_tags" in data:
            sanitized["stimulus_tags"] = as_str_list(data["stimulus_tags"])[:10]

        # Status/version if present
        if "status" in data and isinstance(data["status"], str):
            sanitized["status"] = data["status"].strip() or "draft"
        if "version" in data:
            try:
                sanitized["version"] = int(data["version"]) if int(data["version"]) > 0 else 1
            except Exception:
                pass

        return sanitized
