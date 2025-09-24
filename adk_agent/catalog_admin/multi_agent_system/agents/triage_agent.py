"""
Triage Agent - LLM-powered
Intelligently normalizes exercises with family and variant information.
"""

import logging
from typing import Any, Dict, List, Optional
from .base_llm_agent import BaseLLMAgent, AgentConfig


class TriageAgent(BaseLLMAgent):
    """
    LLM-powered agent for exercise normalization.
    Uses AI to intelligently determine family_slug and variant_key.
    """
    
    def __init__(self, firebase_client):
        config = AgentConfig(
            name="TriageAgent",
            model="gemini-2.5-flash",
            temperature=0.2  # Lower temperature for consistency
        )
        super().__init__(config, firebase_client)
        
        self.system_prompt = """You are an expert exercise categorization specialist.
Your task is to normalize exercise names by determining their family_slug and variant_key.

## Guidelines:
1. family_slug: The core exercise pattern (e.g., "squat", "bench_press", "row")
   - Use underscores for multi-word families
   - Keep it generic, without equipment or variation details
   
2. variant_key: The specific variation identifier (e.g., "equipment:barbell", "grip:wide", "stance:sumo")
   - Format: "attribute:value"
   - Common attributes: equipment, grip, stance, angle, tempo, position
   
3. normalized_name: Clean, standardized exercise name
   - Capitalize properly (e.g., "Barbell Back Squat")
   - Remove redundant words
   - Maintain clarity and specificity

## Examples:
- "BB Back Squat" → family: "squat", variant: "equipment:barbell", name: "Barbell Back Squat"
- "Wide Grip Pull Up" → family: "pull_up", variant: "grip:wide", name: "Wide Grip Pull Up"
- "Incline DB Press" → family: "bench_press", variant: "angle:incline,equipment:dumbbell", name: "Incline Dumbbell Press"
"""

    def process_batch(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a batch of exercises for normalization using LLM.
        """
        normalized = []
        skipped = []
        
        for exercise in exercises:
            try:
                # Check if already normalized
                if exercise.get("family_slug") and exercise.get("variant_key"):
                    skipped.append({
                        "id": exercise.get("id"),
                        "name": exercise.get("name"),
                        "reason": "Already normalized"
                    })
                    continue
                
                # Use LLM to normalize
                result = self.normalize_exercise(exercise)
                
                if result and result.get("success"):
                    # Apply normalization via Firebase
                    self.apply_normalization(exercise, result)
                    normalized.append(result)
                else:
                    skipped.append({
                        "id": exercise.get("id"),
                        "name": exercise.get("name"),
                        "reason": result.get("error", "Normalization failed")
                    })
                    
            except Exception as e:
                self.logger.error(f"Error processing {exercise.get('name')}: {e}")
                skipped.append({
                    "id": exercise.get("id"),
                    "name": exercise.get("name"),
                    "reason": str(e)
                })
        
        return {
            "exercises_normalized": len(normalized),
            "exercises_skipped": len(skipped),
            "normalized": normalized,
            "skipped": skipped
        }
    
    def normalize_exercise(self, exercise: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use LLM to intelligently normalize a single exercise.
        """
        prompt = f"""{self.system_prompt}

Normalize this exercise:
Name: {exercise.get('name')}
Current Equipment: {exercise.get('equipment', [])}
Current Category: {exercise.get('category', 'unknown')}
Current Muscles: {exercise.get('muscles', {})}

Provide a JSON response with:
{{
  "family_slug": "string",
  "variant_key": "string",
  "normalized_name": "string",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

        context = {
            "exercise_data": exercise,
            "existing_families": self.get_existing_families() if self.firebase_client else []
        }
        
        response = self.generate_structured_response(prompt, context)
        
        if response:
            return {
                "success": True,
                "exercise_id": exercise.get("id"),
                "exercise_name": exercise.get("name"),
                "family_slug": response.get("family_slug"),
                "variant_key": response.get("variant_key"),
                "normalized_name": response.get("normalized_name"),
                "confidence": response.get("confidence", 0.8),
                "reasoning": response.get("reasoning", "")
            }
        else:
            return {
                "success": False,
                "exercise_id": exercise.get("id"),
                "exercise_name": exercise.get("name"),
                "error": "Failed to generate normalization"
            }
    
    def get_existing_families(self) -> List[str]:
        """Get list of existing families for context."""
        try:
            if self.firebase_client:
                result = self.firebase_client.get("listFamilies", params={"limit": 100})
                if result and result.get("data"):
                    families = result["data"].get("families", [])
                    return [f["family_slug"] for f in families if f.get("family_slug")]
        except Exception as e:
            self.logger.error(f"Failed to get families: {e}")
        return []
    
    def apply_normalization(self, exercise: Dict[str, Any], normalization: Dict[str, Any]):
        """Apply normalization to exercise via Firebase."""
        if not self.firebase_client:
            return
        
        try:
            updated_exercise = exercise.copy()
            updated_exercise["family_slug"] = normalization["family_slug"]
            updated_exercise["variant_key"] = normalization["variant_key"]
            updated_exercise["name"] = normalization["normalized_name"]
            
            result = self.firebase_client.post(
                "upsertExercise",
                {"exercise": updated_exercise}
            )
            
            if result and result.get("data"):
                self.logger.info(
                    f"Normalized {exercise.get('name')} → "
                    f"{normalization['family_slug']}::{normalization['variant_key']} "
                    f"(confidence: {normalization['confidence']:.2f})"
                )
            else:
                self.logger.error(f"Failed to apply normalization for {exercise.get('name')}")
                
        except Exception as e:
            self.logger.error(f"Error applying normalization: {e}")