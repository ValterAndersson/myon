"""Profile Agent - Deterministic agent for user profile analysis."""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class UserProfile:
    """User profile data structure."""
    user_id: str
    experience_level: str = "intermediate"
    available_equipment: List[str] = None
    goals: List[str] = None
    injuries: List[str] = None
    preferred_exercises: List[str] = None
    avoided_exercises: List[str] = None
    training_days_per_week: int = 3
    session_duration_minutes: int = 60
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            k: v for k, v in self.__dict__.items() 
            if v is not None
        }

class ProfileAgent:
    """
    Deterministic agent for analyzing user capabilities and constraints.
    
    This agent queries Firestore and returns structured user data without
    using LLM reasoning, making it fast and predictable.
    """
    
    def __init__(self):
        self.name = "ProfileAgent"
        self._cache = {}
        try:
            # Lazy import to avoid circulars
            from ..libs.tools_canvas.client import CanvasFunctionsClient
            import os
            base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
            api_key = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
            self._client = CanvasFunctionsClient(base_url=base_url, api_key=api_key)
        except Exception:
            self._client = None
    
    def analyze_capabilities(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Analyze user capabilities based on profile data.
        
        Args:
            context: Execution context with user_id and canvas_id
            include_equipment: Whether to include equipment analysis
            include_experience: Whether to include experience analysis
        
        Returns:
            Structured capabilities analysis
        """
        user_id = context.get("user_id")
        if not user_id:
            return {"error": "No user_id in context"}
        
        # Check cache
        if user_id in self._cache:
            logger.info(f"ProfileAgent: Using cached profile for {user_id}")
            profile = self._cache[user_id]
        else:
            # Fetch from backend; fall back to mock if unavailable
            profile = None
            if self._client:
                try:
                    # Prefer comprehensive profile
                    resp = self._client.get_user(user_id)
                    if resp.get("success"):
                        profile = self._profile_from_backend(user_id, resp)
                    else:
                        # Fallback to lightweight preferences
                        pref = self._client.get_user_preferences(user_id)
                        if pref.get("success"):
                            profile = self._profile_from_prefs(user_id, pref)
                except Exception as e:
                    logger.warning(f"ProfileAgent backend fetch failed: {e}")
            if profile is None:
                profile = self._get_user_profile(user_id)
            self._cache[user_id] = profile
        
        # Analyze capabilities
        capabilities = {
            "user_id": user_id,
            "can_train": True,
            "limitations": [],
            "strengths": [],
            "recommendations": []
        }
        
        # Equipment analysis
        if kwargs.get("include_equipment", True):
            equipment = profile.available_equipment or ["bodyweight"]
            capabilities["equipment"] = {
                "available": equipment,
                "has_barbell": "barbell" in equipment or "full_gym" in equipment,
                "has_dumbbells": "dumbbells" in equipment or "full_gym" in equipment,
                "has_machines": "machines" in equipment or "full_gym" in equipment,
                "is_limited": len(equipment) == 1 and equipment[0] == "bodyweight"
            }
            
            if capabilities["equipment"]["is_limited"]:
                capabilities["limitations"].append("equipment")
                capabilities["recommendations"].append("Focus on bodyweight progressions")
        
        # Experience analysis
        if kwargs.get("include_experience", True):
            experience = profile.experience_level
            capabilities["experience"] = {
                "level": experience,
                "years": self._estimate_years(experience),
                "can_handle_complex": experience in ["intermediate", "advanced"],
                "needs_basics": experience == "beginner"
            }
            
            if experience == "beginner":
                capabilities["limitations"].append("experience")
                capabilities["recommendations"].append("Start with fundamental movements")
            elif experience == "advanced":
                capabilities["strengths"].append("experience")
                capabilities["recommendations"].append("Include advanced techniques")
        
        # Injury considerations
        if profile.injuries:
            capabilities["injuries"] = profile.injuries
            capabilities["limitations"].append("injuries")
            capabilities["avoided_movements"] = self._get_avoided_movements(profile.injuries)
        
        # Training capacity
        capabilities["capacity"] = {
            "days_per_week": profile.training_days_per_week,
            "minutes_per_session": profile.session_duration_minutes,
            "total_weekly_minutes": profile.training_days_per_week * profile.session_duration_minutes,
            "recovery_days": 7 - profile.training_days_per_week
        }
        
        # Goals
        capabilities["goals"] = profile.goals or ["general_fitness"]
        capabilities["training_focus"] = self._determine_focus(profile.goals)
        
        logger.info(f"ProfileAgent: Analyzed capabilities for {user_id}")
        return capabilities
    
    def get_preferences(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Get user exercise preferences."""
        user_id = context.get("user_id")
        if not user_id:
            return {"error": "No user_id in context"}
        
        profile = self._get_user_profile(user_id)
        
        return {
            "preferred_exercises": profile.preferred_exercises or [],
            "avoided_exercises": profile.avoided_exercises or [],
            "session_duration": profile.session_duration_minutes,
            "training_days": profile.training_days_per_week
        }
    
    def _get_user_profile(self, user_id: str) -> UserProfile:
        """
        Get user profile from Firestore.
        
        In production, this would make an actual Firestore query.
        For now, returns mock data.
        """
        # Mock implementation
        mock_profiles = {
            "xLRyVOI0XKSFsTXSFbGSvui8FJf2": UserProfile(
                user_id="xLRyVOI0XKSFsTXSFbGSvui8FJf2",
                experience_level="intermediate",
                available_equipment=["full_gym"],
                goals=["strength", "hypertrophy"],
                training_days_per_week=4,
                session_duration_minutes=60,
                preferred_exercises=["bench_press", "squat", "deadlift"],
                avoided_exercises=["upright_row"]  # Shoulder impingement risk
            )
        }
        
        return mock_profiles.get(user_id, UserProfile(user_id=user_id))

    def _profile_from_backend(self, user_id: str, resp: Dict[str, Any]) -> UserProfile:
        data = resp.get("context", {})
        prefs = data.get("preferences", {})
        # Map backend fields to our profile
        return UserProfile(
            user_id=user_id,
            experience_level=data.get("experienceLevel", "intermediate"),
            available_equipment=self._normalize_equipment(data.get("availableEquipment")),
            goals=self._normalize_goals(data.get("fitnessGoals")),
            training_days_per_week=self._parse_int(data.get("workoutFrequency"), default=3),
            session_duration_minutes=60,
        )

    def _profile_from_prefs(self, user_id: str, pref: Dict[str, Any]) -> UserProfile:
        # Preferences do not include fitness details; return minimal
        return UserProfile(user_id=user_id)

    def _normalize_equipment(self, eq: Any) -> List[str]:
        if not eq:
            return []
        if isinstance(eq, str):
            return [eq]
        if isinstance(eq, list):
            return [str(x) for x in eq]
        return []

    def _normalize_goals(self, goals: Any) -> List[str]:
        if not goals:
            return []
        if isinstance(goals, str):
            return [goals]
        if isinstance(goals, list):
            return [str(x) for x in goals]
        return []

    def _parse_int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return int(value)
            s = str(value).strip()
            # Handle strings like "3 days"
            import re
            m = re.search(r"\d+", s)
            return int(m.group(0)) if m else default
        except Exception:
            return default
    
    def _estimate_years(self, experience_level: str) -> int:
        """Estimate training years from experience level."""
        mapping = {
            "beginner": 0,
            "novice": 1,
            "intermediate": 3,
            "advanced": 5,
            "expert": 8
        }
        return mapping.get(experience_level, 2)
    
    def _get_avoided_movements(self, injuries: List[str]) -> List[str]:
        """Determine movements to avoid based on injuries."""
        avoid_map = {
            "lower_back": ["deadlift", "good_morning", "bent_over_row"],
            "shoulder": ["overhead_press", "upright_row", "dips"],
            "knee": ["deep_squat", "lunges", "leg_extension"],
            "elbow": ["skull_crusher", "close_grip_bench"],
            "wrist": ["front_squat", "clean", "snatch"]
        }
        
        avoided = []
        for injury in injuries:
            avoided.extend(avoid_map.get(injury, []))
        
        return list(set(avoided))
    
    def _determine_focus(self, goals: List[str]) -> str:
        """Determine training focus from goals."""
        if not goals:
            return "general"
        
        if "strength" in goals:
            return "strength"
        elif "hypertrophy" in goals or "muscle" in goals:
            return "hypertrophy"
        elif "endurance" in goals:
            return "endurance"
        elif "weight_loss" in goals or "fat_loss" in goals:
            return "metabolic"
        else:
            return "general"

# Global agent instance
profile_agent = ProfileAgent()
