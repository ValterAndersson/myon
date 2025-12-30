const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const { VERTEX_AI_CONFIG } = require('./config');

if (!admin.apps.length) {
  admin.initializeApp();
}
const db = admin.firestore();

// Agent version - MUST MATCH initialize-session.js
// When this changes, all existing sessions become stale
const AGENT_VERSION = '2.6.0'; // Session-canvas lifecycle binding

// ============================================================================
// GCP AUTH TOKEN CACHE (1hr TTL - tokens are valid for ~1hr)
// ============================================================================
let cachedGcpToken = null;
let tokenExpiresAt = 0;
const TOKEN_BUFFER_MS = 5 * 60 * 1000; // Refresh 5 min before expiry

async function getGcpAuthToken() {
  const now = Date.now();
  if (cachedGcpToken && now < tokenExpiresAt - TOKEN_BUFFER_MS) {
    logger.debug('[Auth] Using cached GCP token');
    return cachedGcpToken;
  }
  
  logger.info('[Auth] Fetching new GCP token...');
  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
  cachedGcpToken = await auth.getAccessToken();
  tokenExpiresAt = now + (55 * 60 * 1000); // ~55 min (conservative)
  logger.info('[Auth] GCP token cached');
  return cachedGcpToken;
}

// Invalidate cached token on auth errors (401/403)
function invalidateTokenCache() {
  logger.info('[Auth] Invalidating cached GCP token');
  cachedGcpToken = null;
  tokenExpiresAt = 0;
}

// ============================================================================
// TOOL LABELS: SINGLE SOURCE OF TRUTH FOR RUNNING STATE
// These MUST match the _display.running values in the tool definitions.
// The tools emit _display.complete for the result, but we use these for tool_started.
// ============================================================================
const TOOL_LABELS = {
  // === COACH AGENT TOOLS (matches _display.running in coach_agent.py) ===
  tool_get_training_context: 'Loading training context',
  tool_get_analytics_features: 'Analyzing training data',
  tool_get_user_profile: 'Loading profile',
  tool_get_recent_workouts: 'Loading recent workouts',
  tool_get_user_exercises_by_muscle: 'Finding exercises',  // Dynamic in tool, generic here
  tool_search_exercises: 'Searching exercises',
  tool_get_exercise_details: 'Loading exercise details',
  
  // === PLANNER AGENT TOOLS (matches _display.running in planner_agent.py) ===
  tool_propose_workout: 'Creating workout plan',
  tool_propose_routine: 'Creating routine',
  tool_get_planning_context: 'Loading planning context',
  tool_get_next_workout: 'Finding next workout',
  tool_get_template: 'Loading template',
  tool_save_workout_as_template: 'Saving template',
  tool_create_routine: 'Creating routine',
  tool_manage_routine: 'Updating routine',
  tool_ask_user: 'Clarifying',
  tool_send_message: 'Responding',
  
  // ===== WITHOUT tool_ prefix (ADK may strip it) =====
  // Coach agent tools
  get_training_context: 'Loading training context',
  get_analytics_features: 'Analyzing training data',
  get_user_profile: 'Loading profile',
  get_recent_workouts: 'Loading recent workouts',
  get_user_exercises_by_muscle: 'Finding exercises',
  search_exercises: 'Searching exercises',
  get_exercise_details: 'Loading exercise details',
  // Planner agent tools
  propose_workout: 'Creating workout plan',
  propose_routine: 'Creating routine',
  get_planning_context: 'Loading planning context',
  get_next_workout: 'Finding next workout',
  get_template: 'Loading template',
  save_workout_as_template: 'Saving template',
  create_routine: 'Creating routine',
  manage_routine: 'Updating routine',
  ask_user: 'Clarifying',
  send_message: 'Responding',
  
  // Legacy tools (v1.0 - deprecated)
  tool_set_context: 'Setting up',
  tool_record_user_info: 'Recording information',
  tool_create_workout_plan: 'Creating workout plan',
  tool_publish_workout_plan: 'Publishing plan',
  tool_emit_status: 'Logging',
  tool_set_canvas_context: 'Setting up',
  tool_fetch_profile: 'Reviewing profile',
  tool_fetch_recent_sessions: 'Checking history',
  tool_emit_agent_event: 'Logging',
  tool_request_clarification: 'Asking question',
  tool_format_workout_plan_cards: 'Formatting plan',
  tool_format_analysis_cards: 'Formatting analysis',
  tool_publish_cards: 'Publishing',
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
  
  const baseLabel = TOOL_LABELS[name] || name.replace(/_/g, ' ');
  
  // Add parameter details for key tools
  switch (name) {
    case 'tool_search_exercises': {
      const details = [];
      if (args.muscle_group) details.push(args.muscle_group);
      if (args.primary_muscle) details.push(args.primary_muscle);
      if (args.split) details.push(args.split);
      if (args.equipment) details.push(`with ${args.equipment}`);
      if (args.query) details.push(`"${args.query}"`);
      return details.length > 0 ? `${baseLabel}: ${details.join(', ')}` : baseLabel;
    }
    case 'tool_get_recent_workouts':
    case 'tool_fetch_recent_sessions': {
      const limit = args.limit || 5;
      return `${baseLabel} (last ${limit})`;
    }
    case 'tool_create_workout_plan': {
      const title = args.title || 'workout';
      const count = Array.isArray(args.exercises) ? args.exercises.length : 0;
      return count > 0 ? `${baseLabel}: "${title}" with ${count} exercises` : baseLabel;
    }
    case 'tool_ask_user':
    case 'tool_request_clarification': {
      return baseLabel;  // Don't expose the question in the tool event
    }
    default:
      return baseLabel;
  }
}

function describeToolResult(name, summary = '', args = {}) {
  const baseLabel = TOOL_LABELS[name] || name.replace(/_/g, ' ');
  
  // Parse summary for item counts
  const itemMatch = summary.match(/items?:\s*(\d+)/i);
  const itemCount = itemMatch ? parseInt(itemMatch[1], 10) : null;
  
  switch (name) {
    case 'tool_search_exercises': {
      if (itemCount !== null) {
        const muscle = args.muscle_group || args.primary_muscle || '';
        return itemCount > 0 
          ? `Found ${itemCount} ${muscle} exercises`
          : `No ${muscle} exercises found`;
      }
      return 'Search complete';
    }
    case 'tool_get_recent_workouts':
    case 'tool_fetch_recent_sessions': {
      if (itemCount !== null) {
        return itemCount > 0 
          ? `Loaded ${itemCount} recent workouts`
          : 'No recent workouts';
      }
      return 'History loaded';
    }
    case 'tool_get_user_profile':
    case 'tool_fetch_profile':
      return 'Profile loaded';
    case 'tool_propose_workout':
      return 'Workout published';
    case 'tool_propose_routine':
      return 'Routine published';
    case 'tool_get_planning_context':
      return 'Context loaded';
    case 'tool_get_next_workout':
      return 'Found next workout';
    case 'tool_get_template':
      return 'Template loaded';
    case 'tool_save_workout_as_template':
      return 'Template saved';
    case 'tool_create_routine':
      return 'Routine created';
    case 'tool_manage_routine':
      return 'Routine updated';
    case 'tool_create_workout_plan':
      return 'Plan created';
    case 'tool_publish_workout_plan':
      return 'Plan published';
    // Analysis agent tools
    case 'tool_get_analytics_features':
      return 'Training data analyzed';
    case 'tool_get_user_exercises_by_muscle':
      return 'Exercises found';
    // Coach agent tools
    case 'tool_get_training_context':
      return 'Context loaded';
    case 'tool_get_exercise_details':
      return 'Exercise details loaded';
    default:
      return summary || 'Complete';
  }
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
// Track tool args for use in result description
const toolArgsCache = new Map();

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
        toolArgsCache.delete(toolKey);
        return null;
      }
      // Track start time and args for duration/result description
      eventStartTimes.set(toolKey, timestamp);
      toolArgsCache.set(toolKey, adkEvent.args || {});
      
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
        toolArgsCache.delete(toolResultKey);
        return null;
      }
      // Calculate duration if we have start time
      const toolStartTime = eventStartTimes.get(toolResultKey);
      const cachedArgs = toolArgsCache.get(toolResultKey) || {};
      const metadata = toolStartTime ? { start_time: toolStartTime } : {};
      eventStartTimes.delete(toolResultKey);
      toolArgsCache.delete(toolResultKey);
      
      // === SINGLE SOURCE OF TRUTH: Use _display.complete if provided by tool ===
      // Fall back to describeToolResult for legacy tools without _display
      const resultText = adkEvent.displayText || describeToolResult(toolName, adkEvent.summary || '', cachedArgs);
      
      // Add phase to metadata if provided by tool
      if (adkEvent.phase) {
        metadata.phase = adkEvent.phase;
      }
      
      return {
        ...base,
        type: 'toolComplete',
        content: {
          tool: toolName,
          tool_name: toolName,
          result: adkEvent.summary || 'Complete',
          text: resultText,
          phase: adkEvent.phase || null,
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

// Create a fresh Vertex AI session (bypassing cache)
async function createFreshSession(userId, purpose, token, agentId, projectId, location) {
  const createUrl = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/reasoningEngines/${agentId}:query`;
  
  logger.info('[createFreshSession] Creating new Vertex AI session...');
  const response = await axios.post(createUrl, {
    class_method: 'create_session',
    input: { user_id: userId, state: { 'user:id': userId } },
  }, { 
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    timeout: 30000 
  });
  
  const sessionId = response.data?.output?.id || response.data?.output?.session_id || response.data?.id;
  if (!sessionId) {
    throw new Error('Failed to create Vertex AI session - no ID returned');
  }
  
  // Store the new session in Firestore
  const sessionDocRef = db.collection('users').doc(userId).collection('agent_sessions').doc(purpose || 'default');
  await sessionDocRef.set({
    sessionId,
    purpose: purpose || 'default',
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    lastUsedAt: admin.firestore.FieldValue.serverTimestamp()
  });
  
  logger.info('[createFreshSession] Created new session', { sessionId });
  return sessionId;
}

// Invalidate all cached sessions for a user
async function invalidateUserSessions(userId) {
  try {
    const sessionsRef = db.collection('users').doc(userId).collection('agent_sessions');
    const sessions = await sessionsRef.get();
    if (sessions.empty) return 0;
    
    const deleteBatch = db.batch();
    sessions.docs.forEach(doc => deleteBatch.delete(doc.ref));
    await deleteBatch.commit();
    
    logger.info('[invalidateUserSessions] Deleted stale sessions', { userId, count: sessions.size });
    return sessions.size;
  } catch (err) {
    logger.warn('[invalidateUserSessions] Failed to delete sessions', { error: String(err) });
    return 0;
  }
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

    // Auth to Vertex (uses cached token)
    logger.info('[streamAgentNormalized] Getting Vertex AI auth token...');
    const token = await getGcpAuthToken();
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
      messageLength: finalMessage.length,
      url,
    });

    // Request as a stream
    let response;
    try {
      response = await axios({
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
    } catch (axiosErr) {
      logger.error('[streamAgentNormalized] Axios request failed', { 
        error: String(axiosErr?.message || axiosErr),
        response: axiosErr?.response?.data ? String(axiosErr.response.data).slice(0, 500) : null,
        status: axiosErr?.response?.status,
      });
      throw axiosErr;
    }
    
    logger.info('[streamAgentNormalized] Got response from Vertex AI', { 
      status: response.status,
      headers: response.headers ? Object.keys(response.headers) : null,
    });
    
    // Check for non-200 status
    if (response.status >= 400) {
      const errorBody = await new Promise((resolve) => {
        let data = '';
        response.data.on('data', (chunk) => { data += chunk.toString(); });
        response.data.on('end', () => { resolve(data); });
        response.data.on('error', () => { resolve(data); });
      });
      logger.error('[streamAgentNormalized] Vertex AI returned error', { status: response.status, body: errorBody.slice(0, 1000) });
      
      // Invalidate token cache AND session on auth errors (401/403)
      // 401 often means the session was created with an old agent version
      if (response.status === 401 || response.status === 403) {
        invalidateTokenCache();
        // Also invalidate the session - it was likely created with old agent
        await invalidateUserSessions(userId);
        sse.write({ type: 'error', error: 'Session expired after agent update. Please try again.', text: 'Session expired after agent update. Please try again.' });
        done(false, new Error(`Vertex AI returned ${response.status}`));
        return;
      }
      
      sse.write({ type: 'error', error: `Vertex AI error: ${response.status} - ${errorBody.slice(0, 200)}` });
      done(false, new Error(`Vertex AI returned ${response.status}`));
      return;
    }

    // Line-by-line reader with state tracking
    let partial = '';
    let isCurrentlyThinking = false;
    let hasEmittedThinkingEvent = false;
    let lineCount = 0;
    let dataChunkCount = 0;
    
    // === EMIT INITIAL THINKING EVENT IMMEDIATELY ===
    // This ensures the UI shows the agent is working right away
    sse.write({ type: 'thinking', text: 'Analyzing...' });
    isCurrentlyThinking = true;
    hasEmittedThinkingEvent = true;
    
    response.data.on('data', (chunk) => {
      dataChunkCount++;
      logger.debug('[streamAgentNormalized] Received data chunk', { chunkNum: dataChunkCount, length: chunk.length });
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
              let displayText = null;
              let phase = null;
              
              try {
                parsedResponse = typeof resp === 'string' ? JSON.parse(resp) : resp;
                
                // === NEW: Extract _display metadata from tool result (single source of truth) ===
                if (parsedResponse && parsedResponse._display) {
                  const display = parsedResponse._display;
                  displayText = display.complete || null;
                  phase = display.phase || null;
                  logger.debug('[streamAgentNormalized] Found _display metadata', { 
                    tool: name, 
                    displayText, 
                    phase 
                  });
                }
                
                // Fallback: Handle various response formats for legacy tools without _display
                if (!displayText) {
                  if (Array.isArray(parsedResponse)) {
                    summary = `items: ${parsedResponse.length}`;
                  } else if (parsedResponse && typeof parsedResponse === 'object') {
                    if (Array.isArray(parsedResponse.data)) summary = `items: ${parsedResponse.data.length}`;
                    else if (Array.isArray(parsedResponse.items)) summary = `items: ${parsedResponse.items.length}`;
                    else if (Array.isArray(parsedResponse.sessions)) summary = `sessions: ${parsedResponse.sessions.length}`;
                    else if (Array.isArray(parsedResponse.templates)) summary = `templates: ${parsedResponse.templates.length}`;
                    else if (Array.isArray(parsedResponse.workouts)) summary = `workouts: ${parsedResponse.workouts.length}`;
                    else if (Array.isArray(parsedResponse.exercises)) summary = `items: ${parsedResponse.exercises.length}`;
                  }
                }
              } catch (_) {}
              
              // Pass displayText and phase to tool_result so transformToIOSEvent can use them
              sse.write({ type: 'tool_result', name, summary, displayText, phase });
              
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

    response.data.on('end', async () => {
      logger.info('[streamAgentNormalized] Vertex AI stream ended', { 
        dataChunks: dataChunkCount, 
        bufferLength: normalizer.buffer.length,
        sessionId: sessionToUse
      });
      
      // Flush remaining buffer
      const pre = normalizer.preprocess(normalizer.buffer);
      if (pre) {
        sse.write({ type: 'text_commit', text: pre });
      }
      
      // If no data chunks received, the session is likely corrupted/stale
      if (dataChunkCount === 0) {
        logger.warn('[streamAgentNormalized] Stream ended with NO data - invalidating session', { 
          sessionId: sessionToUse 
        });
        
        // Invalidate the cached session so a fresh one is created next time
        // The session is stored at: users/{userId}/agent_sessions/{purpose}
        try {
          // Delete all agent sessions for this user to force refresh
          const sessionsRef = db.collection('users').doc(userId).collection('agent_sessions');
          const sessions = await sessionsRef.get();
          const deleteBatch = db.batch();
          sessions.docs.forEach(doc => deleteBatch.delete(doc.ref));
          await deleteBatch.commit();
          logger.info('[streamAgentNormalized] Deleted stale sessions for user', { userId, count: sessions.size });
        } catch (err) {
          logger.warn('[streamAgentNormalized] Failed to delete stale sessions', { error: String(err) });
        }
        
        sse.write({ type: 'error', error: 'Session expired. Please try again.' });
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
