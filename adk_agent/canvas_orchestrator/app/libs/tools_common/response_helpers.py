"""
Response helpers for handling API responses from Firebase Functions.

Provides consistent parsing of responses, error detection, and self-healing
error formatting for agents to retry failed requests.
"""

from typing import Any, Dict, Optional, Tuple


def parse_api_response(resp: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Parse an API response and detect success/failure.
    
    Returns:
        Tuple of (success, data, error_details)
        - success: True if the API call succeeded
        - data: The response data if successful
        - error_details: Structured error info if failed (for agent self-correction)
    """
    if not isinstance(resp, dict):
        return False, None, {"error": "Invalid response format", "raw": str(resp)[:500]}
    
    # Check for explicit success flag
    success = resp.get("success", True)  # Default to True for backwards compat
    
    if not success:
        # Extract error details for agent self-correction
        error_details = {
            "error": resp.get("error", "Unknown error"),
            "code": resp.get("code"),
        }
        
        # Include self-healing details if present
        details = resp.get("details")
        if isinstance(details, dict):
            error_details["hint"] = details.get("hint")
            error_details["validation_errors"] = details.get("errors")
            error_details["expected_schema"] = details.get("expected_schema")
            error_details["attempted"] = details.get("attempted")
        
        return False, None, error_details
    
    # Success - extract data
    data = resp.get("data") or resp
    return True, data, None


def format_validation_error_for_agent(error_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a validation error response for the agent to understand and retry.
    
    Returns a structured dict that the agent can use to self-correct.
    """
    result = {
        "status": "validation_error",
        "retryable": True,
        "message": error_details.get("error", "Validation failed"),
    }
    
    # Include the hint for quick understanding
    if error_details.get("hint"):
        result["hint"] = error_details["hint"]
    
    # Include specific validation errors
    if error_details.get("validation_errors"):
        result["errors"] = [
            {
                "path": e.get("path", ""),
                "message": e.get("message", ""),
            }
            for e in error_details["validation_errors"][:5]  # Limit to 5 errors
        ]
    
    # Include the expected schema (truncated if too large)
    schema = error_details.get("expected_schema")
    if schema:
        schema_str = str(schema)
        if len(schema_str) > 2000:
            result["expected_schema_summary"] = "Schema too large. Key requirements from hint."
        else:
            result["expected_schema"] = schema
    
    # Include what was attempted (truncated)
    attempted = error_details.get("attempted")
    if attempted:
        result["attempted_summary"] = summarize_attempted(attempted)
    
    return result


def summarize_attempted(attempted: Any) -> Dict[str, Any]:
    """Create a summary of what was attempted for debugging."""
    if not isinstance(attempted, dict):
        return {"type": str(type(attempted))}
    
    summary = {"keys": list(attempted.keys())[:10]}
    
    # For card proposals
    if "cards" in attempted and isinstance(attempted["cards"], list):
        summary["cards"] = [
            {
                "type": c.get("type", "?"),
                "content_keys": list(c.get("content", {}).keys())[:5] if isinstance(c.get("content"), dict) else [],
            }
            for c in attempted["cards"][:3]
        ]
    
    return summary


def extract_list_from_response(
    resp: Dict[str, Any],
    *keys: str,
) -> list:
    """
    Extract a list from a nested response structure.
    
    Tries each key path in order (e.g., "data.items", "items", "data").
    Returns empty list if not found or not a list.
    
    Example:
        extract_list_from_response(resp, "data.items", "items", "data")
    """
    for key_path in keys:
        parts = key_path.split(".")
        value = resp
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break
        
        if isinstance(value, list):
            return value
    
    return []
