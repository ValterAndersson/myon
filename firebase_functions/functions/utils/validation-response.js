/**
 * Self-Healing Validation Response Utility
 * 
 * Formats validation errors in a way that allows agents to self-correct.
 * Returns both what was attempted AND the expected schema, enabling
 * agents to compare and fix their requests.
 * 
 * Usage:
 *   const { formatValidationResponse, getHintForErrors } = require('../utils/validation-response');
 *   
 *   if (!valid) {
 *     const details = formatValidationResponse(req.body, errors, schema);
 *     return fail(res, 'INVALID_ARGUMENT', 'Schema validation failed', details, 400);
 *   }
 */

/**
 * Format validation errors for self-healing agents
 * 
 * @param {Object} input - The original request body that failed validation
 * @param {Array} errors - Array of AJV validation errors
 * @param {Object} schema - The JSON Schema that was used for validation
 * @returns {Object} Structured error response with attempted, errors, hint, and expected_schema
 */
function formatValidationResponse(input, errors, schema = null) {
  // Truncate large input to avoid bloated responses
  const inputStr = JSON.stringify(input);
  const truncatedInput = inputStr.length > 2000 
    ? { 
        _truncated: true, 
        _original_size: inputStr.length,
        // Include summary of what was sent
        summary: summarizeInput(input)
      }
    : input;

  const response = {
    // What the agent tried to send
    attempted: truncatedInput,
    
    // Specific validation errors with paths
    errors: errors.map(e => ({
      path: e.instancePath || e.dataPath || '',
      message: e.message,
      keyword: e.keyword,
      params: e.params
    })),
    
    // Human-readable hint for quick understanding
    hint: getHintForErrors(errors),
  };

  // Include the actual JSON schema if provided
  if (schema) {
    response.expected_schema = schema;
  }

  return response;
}

/**
 * Generate human-readable hints based on validation error types
 * 
 * @param {Array} errors - Array of AJV validation errors
 * @returns {string} Human-readable hint string
 */
function getHintForErrors(errors) {
  const hints = [];
  
  for (const e of errors) {
    const path = e.instancePath || 'root';
    
    switch (e.keyword) {
      case 'required':
        const missing = e.params?.missingProperty;
        hints.push(`Missing required property '${missing}' at ${path}`);
        break;
        
      case 'type':
        const expectedType = e.params?.type;
        hints.push(`Wrong type at ${path}: expected ${expectedType}`);
        break;
        
      case 'minimum':
        hints.push(`Value too small at ${path}: minimum is ${e.params?.limit}`);
        break;
        
      case 'maximum':
        hints.push(`Value too large at ${path}: maximum is ${e.params?.limit}`);
        break;
        
      case 'minLength':
        hints.push(`String too short at ${path}: minimum length is ${e.params?.limit}`);
        break;
        
      case 'maxLength':
        hints.push(`String too long at ${path}: maximum length is ${e.params?.limit}`);
        break;
        
      case 'minItems':
        hints.push(`Array too short at ${path}: minimum items is ${e.params?.limit}`);
        break;
        
      case 'maxItems':
        hints.push(`Array too long at ${path}: maximum items is ${e.params?.limit}`);
        break;
        
      case 'enum':
        const allowed = e.params?.allowedValues?.join(', ');
        hints.push(`Invalid value at ${path}: must be one of [${allowed}]`);
        break;
        
      case 'pattern':
        hints.push(`Invalid format at ${path}: must match pattern ${e.params?.pattern}`);
        break;
        
      case 'additionalProperties':
        hints.push(`Unexpected property '${e.params?.additionalProperty}' at ${path}`);
        break;
        
      default:
        hints.push(`Validation error at ${path}: ${e.message}`);
    }
  }
  
  if (hints.length === 0) {
    hints.push('Check the expected_schema field for the correct structure');
  }
  
  return hints.join('. ');
}

/**
 * Create a summary of the input for truncated responses
 * 
 * @param {Object} input - The original input
 * @returns {Object} Summary object
 */
function summarizeInput(input) {
  if (!input || typeof input !== 'object') {
    return { type: typeof input };
  }
  
  const summary = {};
  
  // For proposeCards-style input
  if (input.cards && Array.isArray(input.cards)) {
    summary.cards = input.cards.map(c => ({
      type: c.type,
      lane: c.lane,
      content_keys: c.content ? Object.keys(c.content) : []
    }));
  }
  
  // Include top-level keys
  summary.keys = Object.keys(input);
  
  return summary;
}

module.exports = {
  formatValidationResponse,
  getHintForErrors,
  summarizeInput
};
