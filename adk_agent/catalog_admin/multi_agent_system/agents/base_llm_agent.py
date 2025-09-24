"""
Base LLM Agent
Foundation for all intelligent agents in the multi-agent system.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import google.generativeai as genai


@dataclass
class AgentConfig:
    """Configuration for an LLM agent"""
    name: str
    model: str = "gemini-2.5-flash"  # Fast, efficient model for specialized tasks
    temperature: float = 0.3  # Lower for more consistent outputs
    max_retries: int = 3
    use_reasoning: bool = False  # Set to True to use gemini-2.5-pro for complex reasoning
    

class BaseLLMAgent:
    """
    Base class for LLM-powered specialist agents.
    Provides common functionality for all intelligent agents.
    """
    
    def __init__(self, config: AgentConfig, firebase_client=None):
        self.config = config
        self.firebase_client = firebase_client
        self.logger = logging.getLogger(config.name)
        
        # Initialize Firebase tools if client provided
        self.tools = None
        if firebase_client:
            from .firebase_tools import FirebaseTools
            self.tools = FirebaseTools(firebase_client)
        
        # Initialize Gemini
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable required")
        
        genai.configure(api_key=api_key)
        
        # Use Pro model if reasoning is needed, otherwise use the configured model
        model_name = "gemini-2.5-pro" if config.use_reasoning else config.model
        
        # Create the model with specific configuration
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": config.temperature,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )
        
    def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a response from the LLM with optional context.
        """
        try:
            # Build the full prompt with context
            full_prompt = self._build_prompt(prompt, context)
            
            # Log the agent action
            self.logger.info(f"{self.config.name} processing request...")
            self.logger.debug(f"Prompt preview: {prompt[:200]}...")
            
            # Generate response
            response = self.model.generate_content(full_prompt)
            
            if response:
                # Handle multi-part responses
                try:
                    if response.text:
                        self.logger.info(f"{self.config.name} generated response successfully")
                        return response.text
                except ValueError:
                    # Response has multiple parts, extract text
                    if response.parts:
                        text_parts = []
                        for part in response.parts:
                            if hasattr(part, 'text'):
                                text_parts.append(part.text)
                        if text_parts:
                            combined_text = '\n'.join(text_parts)
                            self.logger.info(f"{self.config.name} generated multi-part response successfully")
                            return combined_text
                    
                    # Try candidates if parts didn't work
                    if response.candidates:
                        for candidate in response.candidates:
                            if candidate.content and candidate.content.parts:
                                text_parts = []
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text'):
                                        text_parts.append(part.text)
                                if text_parts:
                                    combined_text = '\n'.join(text_parts)
                                    self.logger.info(f"{self.config.name} generated response from candidates successfully")
                                    return combined_text
            
            self.logger.error(f"No response from model for prompt: {prompt[:100]}...")
            return ""
                
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return ""
    
    # --- Model control helpers ---
    def switch_to_reasoning_model(self) -> None:
        """Reconfigure the underlying model to use gemini-2.5-pro for deeper reasoning."""
        try:
            import google.generativeai as genai  # type: ignore
            self.config.use_reasoning = True
            self.model = genai.GenerativeModel(
                model_name="gemini-2.5-pro",
                generation_config={
                    "temperature": self.config.temperature,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                },
            )
            self.logger.info({"llm": "switched_to_reasoning_model"})
        except Exception as e:
            self.logger.warning(f"Failed to switch to reasoning model: {e}")
    
    def generate_structured_response(self, prompt: str, context: Optional[Dict[str, Any]] = None, strict: bool = False) -> Dict[str, Any]:
        """
        Generate a structured JSON response from the LLM.
        """
        # Add JSON instruction to prompt
        if strict:
            json_prompt = f"{prompt}\n\nRespond with valid minified JSON only (no code fences, no comments, double quotes), and nothing else."
        else:
            json_prompt = f"{prompt}\n\nRespond with valid minified JSON only (no code fences, no comments, double quotes), and nothing else."

        def _extract_json_text(text: str) -> str:
            # Try code-fenced extraction
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end > start:
                    return text[start:end]
            if "```" in text:
                parts = text.split("```")
                if len(parts) >= 2:
                    candidate = parts[1]
                    if candidate.startswith("json"):
                        candidate = candidate[4:]
                    return candidate
            # Heuristic: find outermost braces
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                return text[first_brace:last_brace+1]
            # Heuristic: array form
            first_bracket = text.find("[")
            last_bracket = text.rfind("]")
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                return text[first_bracket:last_bracket+1]
            return text

        import json

        response_text = self.generate_response(json_prompt, context)
        # Verbose logging of raw LLM output (truncated)
        try:
            raw_preview = (response_text or "")[:2000]
            self.logger.info({"llm": "raw_response", "preview": raw_preview, "truncated": len(response_text or "") > 2000})
        except Exception:
            pass
        if not response_text:
            return {}

        # Strict mode: single extraction and parse, no repair
        if strict:
            try:
                cleaned = _extract_json_text(response_text).strip()
                import json
                return json.loads(cleaned)
            except Exception as e:
                # Log parse error with truncated raw
                try:
                    self.logger.info({"llm": "strict_parse_failed", "error": str(e), "raw_preview": (response_text or "")[:1000]})
                except Exception:
                    self.logger.error(f"Strict JSON parse failed: {e}")
                return {}

        # Non-strict: try limited repair attempts
        attempts = 0
        raw_text = response_text
        while attempts < max(2, self.config.max_retries // 2):
            attempts += 1
            cleaned = _extract_json_text(raw_text).strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                try:
                    repair_prompt = (
                        "You are a JSON fixer. Convert the following to strictly valid minified JSON with double quotes and no comments. "
                        "Return JSON only.\n\nINPUT:\n" + cleaned
                    )
                    raw_text = self.generate_response(repair_prompt)
                    if not raw_text:
                        break
                except Exception as _:
                    break
        try:
            return json.loads(_extract_json_text(response_text))
        except Exception:
            self.logger.error("Failed to parse JSON after repair attempts")
            self.logger.debug(f"Raw response: {response_text}")
            return {}
    
    def _build_prompt(self, base_prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Build a complete prompt with context.
        """
        parts = [base_prompt]
        
        if context:
            context_str = "\n## Context:\n"
            for key, value in context.items():
                if isinstance(value, dict) or isinstance(value, list):
                    import json
                    context_str += f"- {key}: {json.dumps(value, indent=2)}\n"
                else:
                    context_str += f"- {key}: {value}\n"
            parts.insert(0, context_str)
        
        return "\n".join(parts)
    
    def process_batch(self, items: List[Any], task_description: str) -> Dict[str, Any]:
        """
        Process a batch of items using the LLM.
        Override this in subclasses for specific processing logic.
        """
        raise NotImplementedError("Subclasses must implement process_batch")
