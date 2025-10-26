"""Card Formatter Agent - Deterministic card formatting with no LLM reasoning."""

import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from uuid import uuid4

@dataclass 
class CardSpec:
    """Specification for a canvas card."""
    type: str
    lane: str
    priority: int
    content: Dict[str, Any]
    actions: List[Dict[str, str]]
    ttl: Dict[str, int]
    meta: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        if not result.get("meta"):
            result.pop("meta", None)
        return result

class CardFormatter:
    """
    Deterministic card formatter that transforms structured data into card specifications.
    
    This is NOT an LLM agent - it's a pure transformation layer that applies
    consistent formatting rules to create cards.
    """
    
    def __init__(self):
        self.name = "CardFormatter"
    
    def format_session_plan(self, exercises: List[Dict[str, Any]], title: str = "Today's Workout") -> CardSpec:
        """
        Format exercise list into a session plan card.
        
        Input: List of exercise dictionaries with sets/reps
        Output: Properly formatted session_plan card
        """
        blocks = []
        for exercise in exercises:
            sets_data = []
            for i in range(exercise.get("sets", 3)):
                sets_data.append({
                    "target": {
                        "reps": exercise.get("reps", "8-12"),
                        "weight": None,  # User will fill during workout
                        "rir": 2  # Default RIR
                    }
                })
            
            blocks.append({
                "exercise_id": exercise["id"],
                "name": exercise["name"],
                "sets": sets_data,
                "notes": exercise.get("notes"),
                "rest_seconds": exercise.get("rest_seconds", 90)
            })
        
        return CardSpec(
            type="session_plan",
            lane="workout",
            priority=90,
            content={
                "title": title,
                "blocks": blocks,
                "estimated_duration": sum(e.get("sets", 3) * 3 for e in exercises),  # 3 min per set
                "total_sets": sum(e.get("sets", 3) for e in exercises)
            },
            actions=[
                {
                    "kind": "apply",
                    "label": "Start Workout",
                    "style": "primary",
                    "iconSystemName": "play.fill"
                },
                {
                    "kind": "modify",
                    "label": "Edit",
                    "style": "secondary",
                    "iconSystemName": "pencil"
                }
            ],
            ttl={"hours": 24}
        )
    
    def format_exercise_detail(self, exercise: Dict[str, Any], order: int = 1) -> CardSpec:
        """Format individual exercise detail card."""
        return CardSpec(
            type="exercise_detail",
            lane="workout",
            priority=80 - order,  # Later exercises have lower priority
            content={
                "exercise_id": exercise["id"],
                "name": exercise["name"],
                "sets": exercise.get("sets", 3),
                "reps": exercise.get("reps", "8-12"),
                "rest_seconds": exercise.get("rest_seconds", 90),
                "primary_muscles": exercise.get("primary_muscles", []),
                "equipment": exercise.get("equipment", "none"),
                "instructions": exercise.get("instructions", []),
                "tips": exercise.get("tips", [])
            },
            actions=[
                {
                    "kind": "swap",
                    "label": "Swap Exercise",
                    "style": "secondary",
                    "iconSystemName": "arrow.triangle.swap"
                },
                {
                    "kind": "info",
                    "label": "View Demo",
                    "style": "secondary",
                    "iconSystemName": "play.rectangle"
                }
            ],
            ttl={"hours": 24}
        )
    
    def format_agent_narration(self, text: str, status: str = "complete") -> CardSpec:
        """Format agent narration/status message."""
        return CardSpec(
            type="agent-message",
            lane="system",
            priority=100,
            content={
                "text": text,
                "status": status,
                "timestamp": int(time.time() * 1000)
            },
            actions=[],
            ttl={"minutes": 5}
        )
    
    def format_clarify_question(
        self, 
        question: str,
        options: Optional[List[str]] = None,
        question_type: str = "choice"
    ) -> CardSpec:
        """Format a clarification question card."""
        questions = [{
            "id": f"q_{uuid4().hex[:8]}",
            "text": question,
            "type": question_type,
            "options": options if question_type == "choice" else None
        }]
        
        actions = []
        if question_type == "text":
            actions = [
                {
                    "kind": "submit",
                    "label": "Submit",
                    "style": "primary",
                    "iconSystemName": "paperplane"
                },
                {
                    "kind": "skip",
                    "label": "Skip",
                    "style": "secondary",
                    "iconSystemName": "forward"
                }
            ]
        # For choice questions, no actions needed (auto-submit on selection)
        
        return CardSpec(
            type="clarify-questions",
            lane="analysis",
            priority=95,
            content={
                "title": "Quick question",
                "questions": questions
            },
            actions=actions,
            ttl={"minutes": 10}
        )
    
    def format_progress_insight(
        self,
        metric: str,
        value: float,
        change: float,
        period: str = "week"
    ) -> CardSpec:
        """Format a progress insight card."""
        trend = "up" if change > 0 else "down" if change < 0 else "stable"
        
        return CardSpec(
            type="progress_insight",
            lane="analysis", 
            priority=70,
            content={
                "metric": metric,
                "current_value": value,
                "change_percent": change,
                "period": period,
                "trend": trend,
                "interpretation": self._interpret_progress(metric, change)
            },
            actions=[
                {
                    "kind": "details",
                    "label": "View Details",
                    "style": "secondary",
                    "iconSystemName": "chart.line.uptrend.xyaxis"
                }
            ],
            ttl={"days": 7}
        )
    
    def format_recommendation(
        self,
        title: str,
        description: str,
        action_text: str,
        priority: str = "medium"
    ) -> CardSpec:
        """Format a recommendation card."""
        priority_map = {"low": 50, "medium": 60, "high": 70}
        
        return CardSpec(
            type="recommendation",
            lane="analysis",
            priority=priority_map.get(priority, 60),
            content={
                "title": title,
                "description": description,
                "priority": priority
            },
            actions=[
                {
                    "kind": "apply",
                    "label": action_text,
                    "style": "primary",
                    "iconSystemName": "checkmark.circle"
                },
                {
                    "kind": "dismiss",
                    "label": "Not Now",
                    "style": "secondary",
                    "iconSystemName": "xmark.circle"
                }
            ],
            ttl={"days": 3}
        )
    
    def format_card_group(self, cards: List[CardSpec], group_title: str) -> List[CardSpec]:
        """
        Format a group of related cards with a group header.
        
        Returns the group header card plus all member cards with group metadata.
        """
        group_id = f"group_{uuid4().hex[:8]}"
        
        # Create group header
        header = CardSpec(
            type="group_header",
            lane="workout",
            priority=100,
            content={
                "title": group_title,
                "card_count": len(cards),
                "group_id": group_id
            },
            actions=[
                {
                    "kind": "accept_all",
                    "label": "Accept All",
                    "style": "primary",
                    "iconSystemName": "checkmark.circle.fill"
                },
                {
                    "kind": "reject_all",
                    "label": "Dismiss All",
                    "style": "secondary",
                    "iconSystemName": "xmark.circle"
                }
            ],
            ttl={"hours": 24}
        )
        
        # Add group metadata to all cards
        grouped_cards = [header]
        for card in cards:
            card.meta = {"group_id": group_id}
            grouped_cards.append(card)
        
        return grouped_cards
    
    def _interpret_progress(self, metric: str, change: float) -> str:
        """Generate simple interpretation of progress."""
        if metric == "strength":
            if change > 5:
                return "Excellent strength gains"
            elif change > 0:
                return "Steady strength progress"
            elif change < -5:
                return "Strength declining - consider deload"
            else:
                return "Strength maintained"
        elif metric == "volume":
            if change > 10:
                return "Significant volume increase"
            elif change > 0:
                return "Progressive overload on track"
            elif change < -10:
                return "Volume reduction - check recovery"
            else:
                return "Volume stable"
        else:
            return "Progress tracked"

# Global formatter instance
card_formatter = CardFormatter()
