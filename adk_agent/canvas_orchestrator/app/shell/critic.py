"""
Critic - Response validation for complex coaching advice and artifact creation.

The Critic runs a second-pass check on Shell Agent responses for:
1. Hallucination detection (claims without data backing)
2. Safety violations (dangerous advice)
3. Metric accuracy (correct interpretation of analytics data)

ONLY activated for Slow Lane responses involving:
- Complex coaching advice
- Artifact creation (workouts, routines)

Fast Lane responses skip the Critic entirely.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CriticSeverity(str, Enum):
    """Severity levels for critic findings."""
    INFO = "info"          # FYI, not blocking
    WARNING = "warning"    # Should review, but not blocking
    ERROR = "error"        # Blocks response, must fix


@dataclass
class CriticFinding:
    """A single finding from the critic."""
    severity: CriticSeverity
    category: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class CriticResult:
    """Result of critic evaluation."""
    passed: bool
    findings: List[CriticFinding]
    
    @property
    def has_errors(self) -> bool:
        return any(f.severity == CriticSeverity.ERROR for f in self.findings)
    
    @property
    def error_messages(self) -> List[str]:
        return [f.message for f in self.findings if f.severity == CriticSeverity.ERROR]


# ============================================================================
# SAFETY PATTERNS - Flag dangerous advice
# ============================================================================

SAFETY_PATTERNS = [
    # Pain-related advice that should be flagged
    (re.compile(r"\b(work through|push through|ignore)\b.{0,20}\bpain\b", re.I),
     "Advising to ignore pain is dangerous", CriticSeverity.ERROR),
    
    # Extreme volume recommendations
    (re.compile(r"\b(40|50|60)\+?\s+sets?\b.{0,20}\b(per\s+muscle|weekly)\b", re.I),
     "Extreme volume recommendation (>30 sets/muscle/week)", CriticSeverity.WARNING),
    
    # Dangerous rep ranges for certain exercises
    (re.compile(r"\b(deadlift|squat|clean)\b.{0,30}\b(1|2)\s+reps?\b.{0,20}\b(max|failure)\b", re.I),
     "1-2 rep max on compound lift without safety context", CriticSeverity.WARNING),
]


# ============================================================================
# HALLUCINATION PATTERNS - Claims without data
# ============================================================================

HALLUCINATION_PATTERNS = [
    # Specific numbers without "data shows" or "analytics indicate"
    (re.compile(r"your\s+(e1rm|1rm|max)\s+(is|was|hit)\s+\d+", re.I),
     "Specific e1RM claim - verify data was fetched"),
    
    # Progress claims without data reference
    (re.compile(r"you('ve|.have)\s+(gained|lost|improved)\s+\d+", re.I),
     "Specific progress claim - verify data was fetched"),
]


# ============================================================================
# METRIC INTERPRETATION - Check analytics claims
# ============================================================================

def _check_metric_interpretation(
    response: str,
    analytics_data: Optional[Dict[str, Any]] = None
) -> List[CriticFinding]:
    """
    Check if metric interpretations match the data.
    
    Args:
        response: Agent response text
        analytics_data: Analytics data that was used (if available)
        
    Returns:
        List of findings about metric interpretation
    """
    findings = []
    
    # If no analytics data provided, can't verify claims
    if not analytics_data:
        # Check if response makes specific claims without data
        for pattern, description in HALLUCINATION_PATTERNS:
            if pattern.search(response):
                findings.append(CriticFinding(
                    severity=CriticSeverity.WARNING,
                    category="hallucination",
                    message=description,
                    suggestion="Ensure analytics tools were called before making data claims"
                ))
        return findings
    
    # TODO: Verify specific claims against analytics_data
    # This would compare response claims to actual data values
    
    return findings


def _check_safety(response: str) -> List[CriticFinding]:
    """
    Check for safety violations in response.
    
    Args:
        response: Agent response text
        
    Returns:
        List of safety-related findings
    """
    findings = []
    
    for pattern, description, severity in SAFETY_PATTERNS:
        if pattern.search(response):
            findings.append(CriticFinding(
                severity=severity,
                category="safety",
                message=description,
                suggestion="Review and modify advice to be safer"
            ))
    
    return findings


def _check_artifact_quality(
    response: str,
    artifact_data: Optional[Dict[str, Any]] = None
) -> List[CriticFinding]:
    """
    Check artifact creation quality.
    
    Args:
        response: Agent response text
        artifact_data: Created artifact data (if available)
        
    Returns:
        List of artifact quality findings
    """
    findings = []
    
    if not artifact_data:
        return findings
    
    # Check workout artifacts
    if artifact_data.get("type") == "session_plan":
        blocks = artifact_data.get("content", {}).get("blocks", [])
        
        # Too few exercises
        if len(blocks) < 3:
            findings.append(CriticFinding(
                severity=CriticSeverity.WARNING,
                category="artifact_quality",
                message=f"Workout has only {len(blocks)} exercises (minimum 3 recommended)",
            ))
        
        # Check for missing exercise IDs
        missing_ids = [b["name"] for b in blocks if not b.get("exercise_id")]
        if missing_ids:
            findings.append(CriticFinding(
                severity=CriticSeverity.WARNING,
                category="artifact_quality",
                message=f"Exercises missing IDs: {', '.join(missing_ids[:3])}",
                suggestion="Use search_exercises to get valid exercise IDs"
            ))
    
    return findings


def run_critic(
    response: str,
    response_type: str = "general",
    analytics_data: Optional[Dict[str, Any]] = None,
    artifact_data: Optional[Dict[str, Any]] = None,
) -> CriticResult:
    """
    Run critic evaluation on a response.
    
    Args:
        response: Agent response text
        response_type: Type of response ("coaching", "artifact", "general")
        analytics_data: Analytics data used (for verification)
        artifact_data: Created artifact (for quality check)
        
    Returns:
        CriticResult with pass/fail and findings
    """
    findings: List[CriticFinding] = []
    
    # Always check safety
    findings.extend(_check_safety(response))
    
    # Check metric interpretation for coaching responses
    if response_type in ("coaching", "general"):
        findings.extend(_check_metric_interpretation(response, analytics_data))
    
    # Check artifact quality
    if response_type == "artifact" and artifact_data:
        findings.extend(_check_artifact_quality(response, artifact_data))
    
    # Determine pass/fail
    passed = not any(f.severity == CriticSeverity.ERROR for f in findings)
    
    if findings:
        logger.info("CRITIC: %d findings (%s)", 
                   len(findings), 
                   "PASS" if passed else "FAIL")
        for f in findings:
            logger.info("  [%s] %s: %s", f.severity.value.upper(), f.category, f.message)
    
    return CriticResult(passed=passed, findings=findings)


def should_run_critic(routing_intent: Optional[str], response_length: int) -> bool:
    """
    Determine if critic should run for this response.
    
    Criteria:
    - Skip for Fast Lane (already executed)
    - Run for coaching/analysis intents
    - Run for artifact creation
    - Run for long responses (>500 chars)
    
    Args:
        routing_intent: Detected intent from router
        response_length: Length of response in characters
        
    Returns:
        True if critic should run
    """
    # Intents that require critic
    critic_intents = {
        "ANALYZE_PROGRESS",
        "PLAN_ARTIFACT",
        "PLAN_ROUTINE",
        "EDIT_PLAN",
    }
    
    if routing_intent in critic_intents:
        return True
    
    # Long responses get critic pass
    if response_length > 500:
        return True
    
    return False


__all__ = [
    "CriticSeverity",
    "CriticFinding",
    "CriticResult",
    "run_critic",
    "should_run_critic",
]
