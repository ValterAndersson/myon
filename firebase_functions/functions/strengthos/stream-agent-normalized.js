const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const { logger } = require('firebase-functions');
const { VERTEX_AI_CONFIG } = require('./config');

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

  const sse = createSSE(res);
  const normalizer = new TextNormalizer({ markdown_policy: req.body?.markdown_policy });

  // emit policy upfront
  sse.write({ type: 'policy', seq: normalizer.nextSeq(), ts: Date.now(), policy: normalizer.policy.markdown_policy });

  // Heartbeat every ~2500ms
  const hb = setInterval(() => {
    sse.write({ type: 'heartbeat', seq: normalizer.nextSeq(), ts: Date.now() });
  }, 2500);

  const done = (ok = true, err) => {
    clearInterval(hb);
    if (err) {
      sse.write({ type: 'error', seq: normalizer.nextSeq(), ts: Date.now(), error: String(err.message || err) });
    }
    sse.write({ type: 'done', seq: normalizer.nextSeq(), ts: Date.now() });
    sse.close();
  };

  try {
    const userId = req.user?.uid || req.auth?.uid || 'anonymous';
    const message = req.body?.message || '';
    const sessionId = req.body?.sessionId || null;

    // Auth to Vertex
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
    const token = await auth.getAccessToken();

    // If no session, create one first
    let sessionToUse = sessionId;
    if (!sessionToUse) {
      const createUrl = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}:query`;
      const createResp = await axios.post(createUrl, {
        class_method: 'create_session',
        input: { user_id: userId, state: { 'user:id': userId } },
      }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } });
      sessionToUse = createResp.data?.output?.id || createResp.data?.output?.session_id || createResp.data?.id;
      sse.write({ type: 'session', seq: normalizer.nextSeq(), ts: Date.now(), sessionId: sessionToUse });
    }

    const url = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}:streamQuery`;
    const payload = {
      class_method: 'stream_query',
      input: { user_id: userId, session_id: sessionToUse, message },
    };

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

    // Line-by-line reader
    let partial = '';
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
              const name = p.function_call.name || 'tool';
              sse.write({ type: 'tool_started', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, name, args: p.function_call.args || {}, display: true });
            }
            if (p.function_response) {
              const name = p.function_response.name || 'tool';
              const resp = p.function_response.response;
              let counts = {};
              let summary = '';
              try {
                const obj = typeof resp === 'string' ? JSON.parse(resp) : resp;
                if (obj && typeof obj === 'object') {
                  if (Array.isArray(obj.data)) counts.items = obj.data.length;
                  if (Array.isArray(obj.sessions)) counts.sessions = obj.sessions.length;
                  if (Array.isArray(obj.templates)) counts.templates = obj.templates.length;
                  if (Array.isArray(obj.workouts)) counts.workouts = obj.workouts.length;
                }
              } catch (_) {}
              if (counts.items) summary = `items: ${counts.items}`;
              sse.write({ type: 'tool_result', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, name, summary, counts });
            }
          }

          // Text parts normalization with list/code detection
          for (const p of parts) {
            if (typeof p.text === 'string' && p.text) {
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
                  sse.write({ type: 'text_delta', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, text: before });
                }
                // Toggle fence state
                if (!normalizer.isFenceOpen) {
                  normalizer.isFenceOpen = true;
                  normalizer.currentFenceLang = match.replace('```', '') || '';
                  sse.write({ type: 'code_block', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, fence_state: 'open', lang: normalizer.currentFenceLang });
                } else {
                  normalizer.isFenceOpen = false;
                  sse.write({ type: 'code_block', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, fence_state: 'close', lang: normalizer.currentFenceLang });
                  normalizer.currentFenceLang = '';
                }
                remainder = remainder.slice(idx + match.length);
              }
              if (remainder) {
                // Detect list items at line starts
                const lines = remainder.split('\n');
                for (let i = 0; i < lines.length; i++) {
                  const line = lines[i];
                  if ((i > 0 || normalizer.buffer.endsWith('\n')) && /^-\s+/.test(line)) {
                    const textOnly = line.replace(/^-\s+/, '');
                    sse.write({ type: 'list_item', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, text: textOnly });
                  }
                }

                normalizer.buffer += remainder;
                sse.write({ type: 'text_delta', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, text: remainder });
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
                  sse.write({ type: 'text_commit', seq: normalizer.nextSeq(), ts: Date.now(), role, messageId, text: commit });
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
        sse.write({ type: 'text_commit', seq: normalizer.nextSeq(), ts: Date.now(), role: 'model', text: pre });
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


