"""
Apply Gate - Safety gate for catalog mutations.

The apply gate is a hard safety mechanism that prevents accidental catalog
mutations. It requires an explicit environment variable to be set.

Gate hierarchy (all must pass for apply):
1. Hard gate: CATALOG_APPLY_ENABLED=true env var
2. Soft gate: job payload mode=apply (vs dry_run)
3. Optional: Firestore disable flag (future)

This ensures mutations cannot happen accidentally even if code bugs
set mode=apply incorrectly.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Environment variable for hard gate
APPLY_ENABLED_VAR = "CATALOG_APPLY_ENABLED"


class ApplyGateError(Exception):
    """Raised when apply gate blocks a mutation."""
    
    def __init__(self, message: str, gate_type: str = "env_var"):
        super().__init__(message)
        self.gate_type = gate_type


def check_apply_gate() -> bool:
    """
    Check if apply mode is enabled via environment.
    
    Returns:
        True if apply is allowed, False if blocked
    """
    enabled = os.environ.get(APPLY_ENABLED_VAR, "").lower() == "true"
    
    if not enabled:
        logger.warning(
            "Apply gate check: BLOCKED (%s is not set to 'true')",
            APPLY_ENABLED_VAR
        )
    
    return enabled


def require_apply_gate() -> None:
    """
    Raise ApplyGateError if apply gate is not enabled.
    
    Call this before any apply-mode mutation.
    
    Raises:
        ApplyGateError: If gate is not enabled
    """
    if not check_apply_gate():
        raise ApplyGateError(
            f"Apply mode blocked. Set {APPLY_ENABLED_VAR}=true to enable catalog mutations.",
            gate_type="env_var",
        )


def check_mode_gate(mode: str) -> bool:
    """
    Check if mode is 'apply' (vs 'dry_run').
    
    Args:
        mode: Job mode ('apply' or 'dry_run')
        
    Returns:
        True if mode is apply
    """
    return mode == "apply"


def require_all_gates(mode: str) -> None:
    """
    Check all gates for apply mode.
    
    Call this before applying changes. Raises if any gate fails.
    
    Args:
        mode: Job mode
        
    Raises:
        ApplyGateError: If any gate blocks
    """
    if mode != "apply":
        logger.info("Mode is '%s' - skipping apply (dry_run)", mode)
        return
    
    # Check hard gate
    require_apply_gate()
    
    # Future: Add Firestore disable flag check here
    # check_firestore_gate()
    
    logger.info("All apply gates passed - mutations allowed")


def gate_status() -> dict:
    """
    Get current status of all gates.
    
    Returns:
        Dict with gate statuses
    """
    return {
        "env_var_gate": {
            "name": APPLY_ENABLED_VAR,
            "enabled": check_apply_gate(),
            "value": os.environ.get(APPLY_ENABLED_VAR, ""),
        },
        # Future gates
        # "firestore_gate": {...}
    }


__all__ = [
    "ApplyGateError",
    "check_apply_gate",
    "require_apply_gate",
    "check_mode_gate",
    "require_all_gates",
    "gate_status",
    "APPLY_ENABLED_VAR",
]
