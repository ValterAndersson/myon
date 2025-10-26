/**
 * Stream Normalizer for Canvas Agent
 * Converts agent events into Cursor-like UI events
 */

class StreamNormalizer {
  constructor() {
    this.sequence = 0;
    this.activeTools = new Map(); // Track active tool timers
    this.thoughtStartTime = null;
  }

  /**
   * Normalize an agent event for UI consumption
   */
  normalize(event) {
    this.sequence++;
    const timestamp = Date.now();
    
    // Handle different event types
    if (event.type === 'thinking') {
      return this.formatThinking(event, timestamp);
    } else if (event.type === 'thought') {
      return this.formatThought(event, timestamp);
    } else if (event.type === 'tool_start') {
      return this.formatToolStart(event, timestamp);
    } else if (event.type === 'tool_end') {
      return this.formatToolEnd(event, timestamp);
    } else if (event.type === 'message') {
      return this.formatMessage(event, timestamp);
    } else if (event.type === 'card') {
      return this.formatCard(event, timestamp);
    } else {
      // Pass through unknown events
      return {
        type: event.type,
        seq: this.sequence,
        ts: timestamp,
        ...event
      };
    }
  }

  formatThinking(event, timestamp) {
    this.thoughtStartTime = timestamp;
    return {
      type: 'agent_thinking',
      seq: this.sequence,
      ts: timestamp,
      display: 'inline',
      content: {
        status: 'thinking',
        message: 'Thinking'
      }
    };
  }

  formatThought(event, timestamp) {
    const duration = this.thoughtStartTime ? 
      ((timestamp - this.thoughtStartTime) / 1000).toFixed(1) : null;
    
    this.thoughtStartTime = null;
    
    return {
      type: 'agent_thought',
      seq: this.sequence,
      ts: timestamp,
      display: 'inline',
      content: {
        message: event.content.message,
        duration: duration ? `${duration}s` : null
      }
    };
  }

  formatToolStart(event, timestamp) {
    const toolName = event.content.tool;
    this.activeTools.set(toolName, timestamp);
    
    return {
      type: 'agent_tool',
      seq: this.sequence,
      ts: timestamp,
      display: 'inline',
      content: {
        tool: toolName,
        status: 'running',
        description: event.content.description || this.humanizeToolName(toolName)
      }
    };
  }

  formatToolEnd(event, timestamp) {
    const toolName = event.content.tool;
    const startTime = this.activeTools.get(toolName);
    const duration = startTime ? 
      ((timestamp - startTime) / 1000).toFixed(1) : null;
    
    this.activeTools.delete(toolName);
    
    return {
      type: 'agent_tool',
      seq: this.sequence,
      ts: timestamp,
      display: 'inline',
      content: {
        tool: toolName,
        status: event.content.status || 'complete',
        duration: duration ? `${duration}s` : null
      }
    };
  }

  formatMessage(event, timestamp) {
    return {
      type: 'agent_message',
      seq: this.sequence,
      ts: timestamp,
      display: 'block',
      content: {
        text: event.content.text,
        style: 'normal'
      }
    };
  }

  formatCard(event, timestamp) {
    return {
      type: 'agent_card',
      seq: this.sequence,
      ts: timestamp,
      display: 'card',
      content: event.content
    };
  }

  humanizeToolName(toolName) {
    const mappings = {
      'tool_get_user_preferences': 'Looking up profile',
      'tool_search_exercises': 'Searching exercises',
      'tool_calculate_volume': 'Calculating volume',
      'tool_publish_clarify_questions': 'Asking question',
      'tool_canvas_publish': 'Publishing workout',
      'tool_set_user_context': 'Setting context'
    };
    
    return mappings[toolName] || 
      toolName.replace(/^tool_/, '').replace(/_/g, ' ').toLowerCase();
  }
}

module.exports = StreamNormalizer;
