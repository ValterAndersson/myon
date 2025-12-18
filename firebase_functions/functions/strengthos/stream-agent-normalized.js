const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const { VERTEX_AI_CONFIG } = require('./config');

if (!admin.apps.length) {
  admin.initializeApp();
}
const db = admin.firestore();

const TOOL_LABELS = {
  tool_set_canvas_context: 'Linking canvas context',
  tool_fetch_profile: 'Reviewing athlete profile',
  tool_fetch_recent_sessions: 'Reviewing recent sessions',
  tool_emit_agent_event: 'Logging telemetry',
  tool_request_clarification: 'Requesting clarification',
  tool_format_workout_plan_cards: 'Formatting workout plan',
  tool_format_analysis_cards: 'Formatting analysis cards',
  tool_publish_cards: 'Publishing cards',
};

const TELEMETRY_LABELS = {
  'route.workout_planning': 'Routing to workout planner',
  'route.plan_workout': 'Routing to workout planner',
  'route.analysis': 'Routing to analysis agent',
  'plan_workout': 'Synthesizing workout plan',
  'analysis': 'Reviewing analysis task',
  'card.summary': 'Posting summary',
  'card.auto.plan_workout': 'Publishing workout cards',
  'card.auto.plan_workout.error': 'Workout card publish failed',
  'workout_proposed': 'Session plan published',
  'agent_propose': 'Cards posted to canvas',
};

const HIDDEN_TOOL_EVENTS = new Set([
  'transfer_to_agent',
  'tool_emit_agent_event',
  'tool_publish_cards',
  'tool_set_canvas_context',
]);

function shouldSuppressToolEvent(name = '') {
  if (!name) return false;
  if (HIDDEN_TOOL_EVENTS.has(name)) return true;
  if (name.startsWith('tool_emit_')) return true;
  return false;
}

function describeToolEvent(name, args = {}) {
  if (!name) return 'Working';
  if (name === 'transfer_to_agent' && args.agent_name) {
    return `Routing to ${args.agent_name}`;
  }
  if (name === 'tool_emit_agent_event' && args.event_type) {
    return `Telemetry: ${args.event_type}`;
  }
  return TOOL_LABELS[name] || name.replace(/_/g, ' ');
}

function formatTelemetryEvent(evt) {
  if (!evt || typeof evt !== 'object') return null;
  const { type, payload = {} } = evt;
  const baseLabel = TELEMETRY_LABELS[type];
  if (!type && !baseLabel) return null;
  if (type === 'clarification.request') {
    return {
      type: 'clarification.request',
      agent: 'orchestrator',
      timestamp: Date.now() / 1000,
      content: payload,
    };
  }
  let text = baseLabel || type?.replace(/\./g, ' ') || 'Update';
  if (type === 'card.auto.plan_workout.error' && payload.error) {
    text = `${text}: ${payload.error}`;
  }
  if (type === 'plan_workout' && payload.session && payload.session.title) {
    text = `${text}: ${payload.session.title}`;
  }
  return {
    type: 'status',
    agent: 'orchestrator',
    timestamp: Date.now() / 1000,
    content: {
      text,
      status: text,
      telemetry_type: type,
      payload,
    },
    metadata: { telemetry_type: type },
  };
}

const WORKSPACE_EVENT_TYPES = new Set([
  'status',
  'thinking',
  'thought',
  'toolRunning',
  'toolComplete',
  'message',
  'agent_response',
  'agentResponse',
  'text_commit',
  'error',
  'done',
  'user_prompt',
  'clarification.request'
]);

function sanitizeWorkspaceEvent(evt = {}) {
  const clean = {
    type: evt.type || 'unknown',
    agent: evt.agent || null,
    timestamp: typeof evt.timestamp === 'number' ? evt.timestamp : Date.now() / 1000,
  };
  if (evt.content) clean.content = evt.content;
  if (evt.metadata) clean.metadata = evt.metadata;
  return clean;
}

// Helper: SSE writer for NDJSON lines
function createSSE(res) {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  const write = (obj) => {
    try {
      res.write(`data: ${JSON.stringify(obj)}\n\n`);
    } catch (err) {
      // Ignore write errors after client disconnects
    }
  };

  const close = () => {
    try { res.end(); } catch (_) {}
  };

  return { write, close };
}

// Simple rolling hash for dedupe
function fingerprint(text) {
  const trimmed = (text || '').trim().toLowerCase();
  const sample = trimmed.slice(-128);
  let hash = 5381;
  for (let i = 0; i < sample.length; i++) {
    hash = ((hash << 5) + hash) + sample.charCodeAt(i);
    hash >>>= 0; // force uint32
  }
  return String(hash);
}

// Track event start times for duration calculation
const eventStartTimes = new Map();

// Transform ADK events to iOS-friendly StreamEvent format
function transformToIOSEvent(adkEvent) {
  const timestamp = Date.now() / 1000; // Convert to seconds
  const base = {
    type: 'unknown',
    agent: 'orchestrator',
    timestamp,
    metadata: {}
  };

  // Map ADK event types to iOS event types
  switch (adkEvent.type) {
    case 'tool_started': {
      const toolName = adkEvent.name || 'tool';
      const toolKey = `tool_${toolName}`;
      if (shouldSuppressToolEvent(toolName)) {
        eventStartTimes.delete(toolKey);
        return null;
      }
      // Track start time for duration calculation
      eventStartTimes.set(toolKey, timestamp);
      
      return {
        ...base,
        type: 'toolRunning',
        content: {
          tool: toolName,
          tool_name: toolName,
          args: adkEvent.args,
          text: describeToolEvent(toolName, adkEvent.args)
        },
        metadata: {
          start_time: timestamp
        }
      };
    }
    
    case 'tool_result': {
      const toolName = adkEvent.name || 'tool';
      const toolResultKey = `tool_${toolName}`;
      if (shouldSuppressToolEvent(toolName)) {
        eventStartTimes.delete(toolResultKey);
        return null;
      }
      // Calculate duration if we have start time
      const toolStartTime = eventStartTimes.get(toolResultKey);
      const metadata = toolStartTime ? { start_time: toolStartTime } : {};
      eventStartTimes.delete(toolResultKey);
      
      return {
        ...base,
        type: 'toolComplete',
        content: {
          tool: toolName,
          tool_name: toolName,
          result: adkEvent.summary || 'Complete',
          text: describeToolEvent(toolName, adkEvent.args)
        },
        metadata
      };
    }
    
    case 'text_delta':
      return {
        ...base,
        type: 'message',
        content: {
          text: adkEvent.text || '',
          role: 'assistant',
          is_delta: true
        }
      };
    
    case 'text_commit':
      return {
        ...base,
        type: 'agentResponse',
        content: {
          text: adkEvent.text || '',
          role: 'assistant',
          is_commit: true
        }
      };
    
    case 'thinking':
      // Track thinking start time
      eventStartTimes.set('thinking', timestamp);
      
      return {
        ...base,
        type: 'thinking',
        content: {
          text: adkEvent.text || 'Analyzing...'
        },
        metadata: {
          start_time: timestamp
        }
      };
    
    case 'thought':
      // Calculate thinking duration
      const thinkingStartTime = eventStartTimes.get('thinking');
      const thinkingMeta = thinkingStartTime ? { start_time: thinkingStartTime } : {};
      eventStartTimes.delete('thinking');
      
      return {
        ...base,
        type: 'thought',
        content: {
          text: adkEvent.text || ''
        },
        metadata: thinkingMeta
      };
    
    case 'session':
      return {
        ...base,
        type: 'status',
        content: {
          text: 'Connected',
          session_id: adkEvent.sessionId
        }
      };
    
    case 'done':
      // Clear all tracked times
      eventStartTimes.clear();
      
      return {
        ...base,
        type: 'done',
        content: {}
      };
    
    case 'error':
      // Clear tracked times on error
      eventStartTimes.clear();
      
      return {
        ...base,
        type: 'error',
        content: {
          error: adkEvent.error || 'Unknown error',
          text: adkEvent.error || 'Unknown error'
        }
      };
    
    default:
      // Pass through other events as-is
      return {
        ...base,
        type: adkEvent.type,
        content: adkEvent
      };
  }
}

class TextNormalizer {
  constructor(policy = {}) {
    this.buffer = '';
    this.lastTail = '';
    this.seen = new Set();
    this.seq = 0;
    this.isFenceOpen = false;
    this.currentFenceLang = '';
    this.policy = {
      markdown_policy: {
        bullets: '-',
        max_bullets: 6,
        no_headers: true,
        ...policy.markdown_policy,
      },
    };
  }

  // Normalize bullets and strip headings
  preprocess(input) {
    if (!input) return '';
    let text = input
      .replace(/[\u2022\u2023]/g, '-') // •, ‣ → '-'
      .replace(/\r/g, '')
      .replace(/\t\*\s/g, '- ')
      .replace(/^\*\s/gm, '- ')
      .replace(/^•\s/gm, '- ')
      .replace(/^\-\s*/gm, '- ');

    // Collapse stacked hyphen bullets like "- - " → "- "
    text = text.replace(/^\s*[-•]+\s+/gm, '- ');

    // If a bullet appears inline as " - ", treat it as a list item boundary
    // Convert " ... - Something" to "\n- Something" when not inside code
    text = text.replace(/([^\n])\s-\s(?!-)/g, '$1\n- ');

    // Remove stray hyphen before punctuation ("- ." → ".")
    text = text.replace(/-\s*([\.,!\?])/g, '$1');

    // Ensure a space after sentence punctuation when followed by a letter (fixes "performance.Based")
    text = text.replace(/([\.!\?])(\S)/g, (m, p1, p2) => `${p1} ${p2}`);

    // Drop trailing hyphens at end of lines introduced mid-stream ("working sets-\n" → "working sets\n")
    text = text.replace(/-\s*$/gm, '');

    // Collapse multiple spaces
    text = text.replace(/\s{2,}/g, ' ');

    if (this.policy.markdown_policy?.no_headers) {
      text = text
        .split('\n')
        .filter((ln) => !(ln.trim().startsWith('# ')
          || ln.trim().startsWith('## ')
          || ln.trim().startsWith('### ')))
        .join('\n');
    }
    return text;
  }

  // Decide safe commit boundary avoiding open code-fences
  computeCommitWindow(text, allowPartial) {
    if (allowPartial) return { commit: text, keep: '' };
    const delimiters = ['\n\n', '. ', '! ', '? ', '\n- ', '\n* ', '\n1. '];
    let cut = -1;
    let matched = '';
    for (const d of delimiters) {
      const idx = text.lastIndexOf(d);
      if (idx !== -1) { matched = d; cut = idx + d.length; break; }
    }
    const fenceCount = (text.match(/```/g) || []).length;
    const isFenceOpen = fenceCount % 2 === 1;
    if (isFenceOpen) return { commit: '', keep: text }; // never commit inside open fence
    // If boundary found is the start of a list item ("\n- ", "\n* ", "\n1. "),
    // commit BEFORE the delimiter so we don't flush a dangling bullet marker
    if (cut !== -1) {
      if (matched === '\n- ' || matched === '\n* ' || matched === '\n1. ') {
        const idx = text.lastIndexOf(matched);
        return { commit: text.slice(0, idx), keep: text.slice(idx) };
      }
      return { commit: text.slice(0, cut), keep: text.slice(cut) };
    }
    return { commit: '', keep: text };
  }

  dedupeTrailing(addition, minLen = 6) {
    const add = (addition || '').trim();
    if (!add) return '';
    const tail = this.lastTail || this.buffer.slice(-200);
    if (tail && (tail.endsWith(add) || tail.includes(add))) return '';
    const window = this.buffer.slice(-800);
    if (window.includes(add) && add.length >= minLen) return '';
    const fp = fingerprint(add);
    if (this.seen.has(fp)) return '';
    this.seen.add(fp);
    return addition;
  }

  nextSeq() { this.seq += 1; return this.seq; }
}

async function streamAgentNormalizedHandler(req, res) {
  // CORS preflight handled by outer middleware when wrapped
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method Not Allowed' });
    return;
  }

  logger.info('[streamAgentNormalized] Handler invoked', { 
    body: req.body, 
    method: req.method,
    headers: { authorization: req.headers.authorization ? 'present' : 'missing' }
  });

  const sseRaw = createSSE(res);
  const normalizer = new TextNormalizer({ markdown_policy: req.body?.markdown_policy });
  const workspaceWrites = [];
  let persistWorkspaceEntry = () => {};

  const enqueueWorkspaceEntry = (ref, correlationId) => (event) => {
    if (!event || !WORKSPACE_EVENT_TYPES.has(event.type)) return;
    const record = {
      entry: sanitizeWorkspaceEvent(event),
      type: event.type,
      agent: event.agent || null,
      correlation_id: correlationId || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    };
    workspaceWrites.push(
      ref.add(record).catch((err) => {
        logger.warn('[streamAgentNormalized] workspace entry write failed', { error: String(err?.message || err) });
      })
    );
  };

  // Wrap SSE writer to transform ADK events to iOS StreamEvent format
  const sse = {
    write: (adkEvent) => {
      const iosEvent = transformToIOSEvent(adkEvent);
      if (!iosEvent) return;
      logger.debug('[streamAgentNormalized] Emitting event', { type: iosEvent.type });
      sseRaw.write(iosEvent);
      persistWorkspaceEntry(iosEvent);
    },
    close: () => sseRaw.close()
  };

  // Emit initial status
  sse.write({ type: 'status', content: { text: 'Connecting...' } });
  logger.info('[streamAgentNormalized] Emitted initial status');

  // Heartbeat every ~2500ms - send as status events
  const hb = setInterval(() => {
    sse.write({ type: 'heartbeat' });
  }, 2500);

  const finalizeWorkspaceWrites = () => Promise.allSettled(workspaceWrites).catch(() => {});

  const done = (ok = true, err) => {
    clearInterval(hb);
    if (err) {
      sse.write({ type: 'error', error: String(err.message || err) });
    }
    sse.write({ type: 'done' });
    finalizeWorkspaceWrites().finally(() => sse.close());
  };

  try {
    const userId = req.user?.uid || req.auth?.uid || 'anonymous';
    const message = req.body?.message || '';
    const sessionId = req.body?.sessionId || null;
    const canvasId = req.body?.canvasId;
    const correlationId = req.body?.correlationId || null;
    
    if (!canvasId) {
      sse.write({ type: 'error', error: 'canvasId is required' });
      done(false, new Error('canvasId is required'));
      return;
    }
    
    const workspaceRef = db
      .collection('users')
      .doc(userId)
      .collection('canvases')
      .doc(canvasId)
      .collection('workspace_entries');
    persistWorkspaceEntry = enqueueWorkspaceEntry(workspaceRef, correlationId);
    
    // Canvas Orchestrator agent ID
    const agentId = '8723635205937561600';
    const projectId = VERTEX_AI_CONFIG.projectId;
    const location = VERTEX_AI_CONFIG.location;

    // Auth to Vertex
    logger.info('[streamAgentNormalized] Getting Vertex AI auth token...');
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
    const token = await auth.getAccessToken();
    logger.info('[streamAgentNormalized] Got Vertex AI auth token');

    // If no session, create one first
    let sessionToUse = sessionId;
    if (!sessionToUse) {
      logger.info('[streamAgentNormalized] Creating new session...');
      const createUrl = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/reasoningEngines/${agentId}:query`;
      const createResp = await axios.post(createUrl, {
        class_method: 'create_session',
        input: { user_id: userId, state: { 'user:id': userId } },
      }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } });
      sessionToUse = createResp.data?.output?.id || createResp.data?.output?.session_id || createResp.data?.id;
      logger.info('[streamAgentNormalized] Created session', { sessionId: sessionToUse });
      sse.write({ type: 'session', sessionId: sessionToUse });
    } else {
      logger.info('[streamAgentNormalized] Using existing session', { sessionId: sessionToUse });
    }

    const url = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/reasoningEngines/${agentId}:streamQuery`;
    
    // Prepend context hint with canvas_id and user_id for Canvas Orchestrator
    const contextHint = `(context: canvas_id=${canvasId} user_id=${userId} corr=${correlationId || 'none'})`;
    const finalMessage = message ? `${contextHint}\n${message}` : contextHint;
    
    const payload = {
      class_method: 'stream_query',
      input: { user_id: userId, session_id: sessionToUse, message: finalMessage },
    };

    logger.info('[streamAgentNormalized] Sending stream request to Vertex AI', { 
      agentId, 
      sessionId: sessionToUse,
      messageLength: finalMessage.length
    });

    // Request as a stream
    const response = await axios({
      method: 'post',
      url,
      data: payload,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      responseType: 'stream',
      timeout: 60000,
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
      validateStatus: (status) => status >= 200 && status < 500,
    });
    
    logger.info('[streamAgentNormalized] Got response from Vertex AI', { status: response.status });

    // Line-by-line reader with state tracking
    let partial = '';
    let isCurrentlyThinking = false;
    let hasEmittedThinkingEvent = false;
    
    response.data.on('data', (chunk) => {
      partial += chunk.toString('utf8');
      const lines = partial.split('\n');
      partial = lines.pop();
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const evt = JSON.parse(trimmed);

          const role = evt?.content?.role || evt?.role || 'model';
          const parts = (evt?.content?.parts || []);
          const messageId = evt?.id || evt?.invocationId || null;

          // Map function calls/responses to tool events
          for (const p of parts) {
            if (p.function_call) {
              // If we were thinking and now calling a tool, emit thought completion
              if (isCurrentlyThinking && hasEmittedThinkingEvent) {
                sse.write({ type: 'thought', text: '' });
                isCurrentlyThinking = false;
                hasEmittedThinkingEvent = false;
              }
              
              const name = p.function_call.name || 'tool';
              sse.write({ type: 'tool_started', name, args: p.function_call.args || {} });
            }
            if (p.function_response) {
              const name = p.function_response.name || 'tool';
              const resp = p.function_response.response;
              let summary = '';
              let parsedResponse = null;
              try {
                parsedResponse = typeof resp === 'string' ? JSON.parse(resp) : resp;
                if (parsedResponse && typeof parsedResponse === 'object') {
                  if (Array.isArray(parsedResponse.data)) summary = `items: ${parsedResponse.data.length}`;
                  else if (Array.isArray(parsedResponse.sessions)) summary = `sessions: ${parsedResponse.sessions.length}`;
                  else if (Array.isArray(parsedResponse.templates)) summary = `templates: ${parsedResponse.templates.length}`;
                  else if (Array.isArray(parsedResponse.workouts)) summary = `workouts: ${parsedResponse.workouts.length}`;
                }
              } catch (_) {}
              sse.write({ type: 'tool_result', name, summary });
              
              if (parsedResponse && Array.isArray(parsedResponse.events)) {
                for (const evt of parsedResponse.events) {
                  if (evt && typeof evt === 'object') {
                    const formatted = formatTelemetryEvent(evt);
                    sse.write(formatted || evt);
                  }
                }
              }
              
              // After tool completes, agent is thinking about next step
              if (!isCurrentlyThinking) {
                sse.write({ type: 'thinking', text: 'Analyzing...' });
                isCurrentlyThinking = true;
                hasEmittedThinkingEvent = true;
              }
            }
          }

          // Text parts normalization with list/code detection
          for (const p of parts) {
            if (typeof p.text === 'string' && p.text) {
              // If we were thinking and now have text response, emit thought completion
              if (isCurrentlyThinking && hasEmittedThinkingEvent) {
                sse.write({ type: 'thought', text: '' });
                isCurrentlyThinking = false;
                hasEmittedThinkingEvent = false;
              }
              
              const incoming = normalizer.preprocess(p.text);
              const candidate = normalizer.dedupeTrailing(incoming);
              if (!candidate) continue;

              // Detect code fence transitions
              const fenceMatches = candidate.match(/```[a-zA-Z0-9_-]*/g) || [];
              let remainder = candidate;
              for (const match of fenceMatches) {
                const idx = remainder.indexOf(match);
                const before = remainder.slice(0, idx);
                if (before) {
                  normalizer.buffer += before;
                  sse.write({ type: 'text_delta', text: before });
                }
                // Toggle fence state
                if (!normalizer.isFenceOpen) {
                  normalizer.isFenceOpen = true;
                  normalizer.currentFenceLang = match.replace('```', '') || '';
                  // Code blocks aren't mapped to iOS events yet, skip for now
                } else {
                  normalizer.isFenceOpen = false;
                  normalizer.currentFenceLang = '';
                }
                remainder = remainder.slice(idx + match.length);
              }
              if (remainder) {
                // Skip list item detection for simplicity
                normalizer.buffer += remainder;
                sse.write({ type: 'text_delta', text: remainder });
              }

              // Emit commit if safe
              const { commit, keep } = normalizer.computeCommitWindow(normalizer.buffer, false);
              if (commit) {
                // Coalesce tiny trailing commits that lack terminal punctuation
                const trimmed = commit.trim();
                const endsWell = /[\.!\?]$/.test(trimmed);
                if (trimmed.length < 40 && !endsWell) {
                  // keep everything for next pass
                } else {
                  sse.write({ type: 'text_commit', text: commit });
                  normalizer.buffer = keep;
                  normalizer.lastTail = (commit + keep).slice(-200);
                }
              }
            }
          }
        } catch (e) {
          // non-JSON line, ignore
        }
      }
    });

    response.data.on('end', () => {
      // Flush remaining buffer
      const pre = normalizer.preprocess(normalizer.buffer);
      if (pre) {
        sse.write({ type: 'text_commit', text: pre });
      }
      done(true);
    });

    response.data.on('error', (err) => {
      logger.error('[streamAgentNormalized] upstream error', { error: String(err) });
      done(false, err);
    });
  } catch (err) {
    logger.error('[streamAgentNormalized] handler error', { error: String(err?.message || err) });
    done(false, err);
  }
}

module.exports = { streamAgentNormalizedHandler };


