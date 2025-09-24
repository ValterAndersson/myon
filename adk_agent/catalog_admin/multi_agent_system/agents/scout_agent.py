"""
Scout Agent - LLM-powered
Intelligently identifies gaps in the exercise catalog from search patterns.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from .base_llm_agent import BaseLLMAgent, AgentConfig


class ScoutAgent(BaseLLMAgent):
    """
    LLM-powered agent that analyzes search patterns to find catalog gaps.
    Uses AI to identify missing exercises and suggest additions.
    """
    
    def __init__(self, firebase_client):
        config = AgentConfig(
            name="ScoutAgent",
            model="gemini-2.5-flash",
            temperature=0.4  # Slightly higher for creative gap finding
        )
        super().__init__(config, firebase_client)
        
        self.system_prompt = """You are an expert fitness catalog analyst specializing in identifying gaps.
Your task is to analyze search patterns and identify exercises that users are looking for but can't find.

## Your Responsibilities:
1. Analyze failed search queries to identify patterns
2. Determine if searches indicate missing exercises
3. Suggest new exercises to fill identified gaps
4. Consider exercise variations and equipment alternatives
5. Identify trends in what users are searching for

## Gap Identification Criteria:
- Multiple failed searches for the same exercise
- Searches for common variations not in catalog
- Equipment-specific versions of existing exercises
- Progressive/regressive variations
- Sport-specific or rehabilitation exercises

## Output Requirements:
For each gap, provide:
- Exercise name (clear and specific)
- Confidence score (0.0-1.0)
- Reasoning for inclusion
- Similar existing exercises
- Suggested category and equipment
"""

    def process_batch(self, search_logs: List[Dict[str, Any]], create_drafts: bool = False) -> Dict[str, Any]:
        """
        Process search logs to identify catalog gaps using LLM.
        """
        # Get current catalog for context
        existing_exercises = self.get_existing_exercises()
        
        # Analyze patterns with LLM
        gaps = self.analyze_search_patterns(search_logs, existing_exercises)
        
        # Create draft exercises if requested
        created_exercises = []
        if create_drafts and gaps:
            created_exercises = self.create_draft_exercises(gaps)
        
        return {
            "patterns_found": len(search_logs),
            "gaps_identified": len(gaps),
            "drafts_created": len(created_exercises),
            "gaps": gaps,
            "created_exercises": created_exercises
        }
    
    def analyze_search_patterns(self, search_logs: List[Dict[str, Any]], 
                               existing_exercises: List[str]) -> List[Dict[str, Any]]:
        """
        Use LLM to analyze search patterns and identify gaps.
        """
        if not search_logs:
            return []
        
        # Prepare search data for analysis
        search_summary = self.summarize_searches(search_logs)
        
        prompt = f"""{self.system_prompt}

## Search Pattern Analysis

Failed Searches Summary:
{search_summary}

Current Catalog Size: {len(existing_exercises)} exercises
Sample Existing Exercises: {', '.join(existing_exercises[:20])}

Analyze these search patterns and identify missing exercises that should be added to the catalog.

Provide a JSON response with an array of gaps:
{{
  "gaps": [
    {{
      "exercise_name": "string",
      "confidence": 0.0-1.0,
      "search_frequency": number,
      "reasoning": "string",
      "similar_exercises": ["string"],
      "suggested_category": "compound|isolation",
      "suggested_equipment": ["string"],
      "user_intent": "string"
    }}
  ]
}}

Focus on high-confidence gaps that would genuinely improve the catalog."""

        context = {
            "total_searches": len(search_logs),
            "unique_queries": len(set(log.get("query", "") for log in search_logs)),
            "date_range": self.get_date_range(search_logs)
        }
        
        response = self.generate_structured_response(prompt, context)
        
        if response and response.get("gaps"):
            gaps = response["gaps"]
            # Sort by confidence
            gaps.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            return gaps[:10]  # Return top 10 gaps
        
        return []
    
    def summarize_searches(self, search_logs: List[Dict[str, Any]]) -> str:
        """
        Summarize search logs for LLM analysis.
        """
        # Group by query
        query_counts = {}
        for log in search_logs:
            query = log.get("query", "").lower().strip()
            if query:
                query_counts[query] = query_counts.get(query, 0) + 1
        
        # Sort by frequency
        sorted_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Format for prompt
        summary_lines = []
        for query, count in sorted_queries[:30]:  # Top 30 queries
            summary_lines.append(f"- '{query}': {count} searches")
        
        return "\n".join(summary_lines)
    
    def get_date_range(self, search_logs: List[Dict[str, Any]]) -> str:
        """Get date range of search logs."""
        timestamps = [log.get("timestamp") for log in search_logs if log.get("timestamp")]
        if not timestamps:
            return "Unknown"
        
        try:
            dates = [datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in timestamps]
            min_date = min(dates)
            max_date = max(dates)
            return f"{min_date.date()} to {max_date.date()}"
        except:
            return "Unknown"
    
    def get_existing_exercises(self) -> List[str]:
        """Get list of existing exercise names for context."""
        try:
            if self.firebase_client:
                result = self.firebase_client.get("getExercises", params={"limit": 500})
                if result and result.get("data"):
                    exercises = result["data"].get("items", [])
                    return [ex.get("name", "") for ex in exercises if ex.get("name")]
        except Exception as e:
            self.logger.error(f"Failed to get exercises: {e}")
        return []
    
    def create_draft_exercises(self, gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create draft exercises for identified gaps using LLM.
        """
        created = []
        
        for gap in gaps[:5]:  # Limit to top 5 gaps
            if gap.get("confidence", 0) < 0.7:
                continue  # Skip low confidence gaps
            
            try:
                exercise = self.generate_exercise_draft(gap)
                if exercise:
                    # Create via Firebase
                    result = self.firebase_client.post(
                        "ensureExerciseExists",
                        {"exercise": exercise}
                    )
                    
                    if result and result.get("data"):
                        created.append({
                            "id": result["data"].get("id"),
                            "name": gap["exercise_name"],
                            "confidence": gap["confidence"]
                        })
                        self.logger.info(f"Created draft: {gap['exercise_name']}")
                        
            except Exception as e:
                self.logger.error(f"Failed to create {gap['exercise_name']}: {e}")
        
        return created
    
    def generate_exercise_draft(self, gap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Use LLM to generate a complete exercise draft.
        """
        prompt = f"""Create a complete exercise definition for: {gap['exercise_name']}

Context:
- User Intent: {gap.get('user_intent', 'General fitness')}
- Similar Exercises: {', '.join(gap.get('similar_exercises', []))}
- Suggested Category: {gap.get('suggested_category', 'compound')}
- Suggested Equipment: {gap.get('suggested_equipment', ['bodyweight'])}

Generate a JSON exercise object with:
{{
  "name": "string",
  "family_slug": "string",
  "variant_key": "string",
  "category": "compound|isolation",
  "equipment": ["string"],
  "movement": {{
    "type": "push|pull|squat|hinge|lunge|carry|rotation",
    "split": "upper|lower|full"
  }},
  "muscles": {{
    "primary": ["string"],
    "secondary": ["string"],
    "category": ["string"]
  }},
  "metadata": {{
    "level": "beginner|intermediate|advanced",
    "plane_of_motion": "sagittal|frontal|transverse",
    "unilateral": boolean
  }},
  "description": "string (50+ chars)",
  "status": "draft"
}}"""

        response = self.generate_structured_response(prompt)
        
        if response and response.get("name"):
            # Ensure required fields
            response["status"] = "draft"
            response["version"] = 1
            return response
        
        return None
