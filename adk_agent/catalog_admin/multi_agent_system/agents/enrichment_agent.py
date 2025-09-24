"""
Enrichment Agent - LLM-powered
Intelligently adds aliases and enriches exercise metadata.
"""

import logging
from typing import Any, Dict, List, Optional
from .base_llm_agent import BaseLLMAgent, AgentConfig


class EnrichmentAgent(BaseLLMAgent):
    """
    LLM-powered agent for enriching exercises with aliases and metadata.
    Uses AI to generate intelligent aliases and improve searchability.
    """
    
    def __init__(self, firebase_client):
        config = AgentConfig(
            name="EnrichmentAgent",
            model="gemini-2.5-flash",
            temperature=0.3  # Moderate temperature for creative but sensible aliases
        )
        super().__init__(config, firebase_client)
        
        self.system_prompt = """You are an expert at creating exercise aliases and enriching exercise metadata.
Your task is to generate alternative names and search terms that users might use to find exercises.

## Alias Generation Guidelines:

1. **Common Abbreviations**:
   - Barbell → BB
   - Dumbbell → DB
   - Romanian Deadlift → RDL
   - Overhead Press → OHP
   - Pull Up → PU

2. **Alternative Names**:
   - Bench Press → Chest Press, Bench
   - Squat → Back Squat (if barbell)
   - Deadlift → DL, Deads

3. **Colloquial Terms**:
   - Include gym slang and common nicknames
   - Consider regional variations
   - Add shortened versions

4. **Format Rules**:
   - Aliases should be lowercase with underscores
   - No special characters except underscores
   - Keep them searchable and intuitive

## Quality Criteria:
- Each exercise should have 2-5 aliases
- Aliases must be unique and not conflict with other exercises
- Focus on terms people actually search for
- Avoid overly generic terms that could match many exercises
"""

    def process_batch(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a batch of exercises for enrichment using LLM.
        """
        # Handle case where exercises is wrapped in a dict with 'items' key
        if len(exercises) == 1 and isinstance(exercises[0], dict) and 'items' in exercises[0]:
            exercises = exercises[0]['items']
            self.logger.info(f"Unwrapped {len(exercises)} exercises from items dict")
        
        enriched = []
        skipped = []
        total_aliases_added = 0
        
        for exercise in exercises:
            try:
                # Check if already has sufficient aliases
                current_aliases = exercise.get("aliases", [])
                if len(current_aliases) >= 3:
                    skipped.append({
                        "id": exercise.get("id"),
                        "name": exercise.get("name"),
                        "reason": "Already has sufficient aliases"
                    })
                    continue
                
                # Generate aliases using LLM (prefer slug-friendly, short, equipment-specific where applicable)
                aliases = self.generate_aliases(exercise)
                
                if aliases:
                    # Add aliases via Firebase
                    added_count = self.add_aliases(exercise, aliases)
                    if added_count > 0:
                        enriched.append({
                            "exercise_id": exercise.get("id"),
                            "exercise_name": exercise.get("name"),
                            "aliases_added": added_count,
                            "aliases": aliases[:added_count]
                        })
                        total_aliases_added += added_count
                else:
                    skipped.append({
                        "id": exercise.get("id"),
                        "name": exercise.get("name"),
                        "reason": "No suitable aliases generated"
                    })
                    
            except Exception as e:
                self.logger.error(f"Error enriching {exercise.get('name')}: {e}")
                skipped.append({
                    "id": exercise.get("id"),
                    "name": exercise.get("name"),
                    "reason": str(e)
                })
        
        return {
            "exercises_enriched": len(enriched),
            "exercises_skipped": len(skipped),
            "total_aliases_added": total_aliases_added,
            "enriched": enriched,
            "skipped": skipped
        }
    
    def generate_aliases(self, exercise: Dict[str, Any]) -> List[str]:
        """
        Use LLM to generate intelligent aliases for an exercise.
        """
        prompt = f"""{self.system_prompt}

Generate aliases for this exercise:
Name: {exercise.get('name')}
Equipment: {exercise.get('equipment', [])}
Category: {exercise.get('category', '')}
Family: {exercise.get('family_slug', '')}
Current Aliases: {exercise.get('aliases', [])}

Provide a JSON response with 2-5 unique aliases:
{{
  "aliases": ["alias1", "alias2", ...],
  "reasoning": "brief explanation of choices"
}}

Make sure aliases are:
- Lowercase with underscores (e.g., "bb_squat")
- Different from the exercise name
- Not already in the current aliases list
- Commonly used search terms"""

        response = self.generate_structured_response(prompt)
        
        if response and response.get("aliases"):
            # Validate and clean aliases
            aliases = []
            for alias in response["aliases"]:
                # Clean the alias
                cleaned = alias.lower().replace(" ", "_").replace("-", "_")
                # Remove special characters except underscores
                cleaned = ''.join(c for c in cleaned if c.isalnum() or c == '_')
                
                # Don't add if it's the same as the exercise name
                exercise_name_clean = exercise.get("name", "").lower().replace(" ", "_")
                if cleaned and cleaned != exercise_name_clean:
                    aliases.append(cleaned)
            
            return aliases[:5]  # Limit to 5 aliases
        
        return []
    
    def add_aliases(self, exercise: Dict[str, Any], aliases: List[str]) -> int:
        """
        Add aliases to an exercise via Firebase.
        """
        if not self.tools:
            return 0
        
        added = 0
        exercise_id = exercise.get("id")
        family_slug = exercise.get("family_slug")
        current_aliases = exercise.get("aliases", [])
        
        for alias in aliases:
            # Skip if already exists
            if alias in current_aliases:
                continue
            
            try:
                result = self.tools.upsert_alias(
                    alias_slug=alias,
                    exercise_id=exercise_id,
                    family_slug=family_slug
                )
                
                if result and (result.get("ok") or result.get("success")):
                    added += 1
                    self.logger.info(f"Added alias '{alias}' to {exercise.get('name')}")
                    
            except Exception as e:
                self.logger.warning(f"Failed to add alias '{alias}': {e}")
        
        return added
