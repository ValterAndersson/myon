/**
 * Server caps, response builders, and cursor utilities for Training Analytics API
 * 
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 5
 */

const { HttpsError } = require('firebase-functions/v2/https');

/**
 * Universal server caps
 */
const CAPS = {
  // Pagination
  DEFAULT_LIMIT: 50,
  MAX_LIMIT: 200,
  
  // Projection
  MAX_FIELDS: 20,
  
  // Response size
  MAX_RESPONSE_BYTES: 32768,        // 32 KB hard limit
  TARGET_RESPONSE_BYTES: 15360,     // 15 KB target for summaries
  
  // Series
  MAX_WEEKS: 52,
  DEFAULT_WEEKS: 12,
  
  // Lists
  MAX_TOP_EXERCISES: 5,
  MAX_PROXY_TRENDS: 3,
  MAX_EXERCISE_IDS_FILTER: 10,
  
  // Batching
  FIRESTORE_BATCH_LIMIT: 500,
};

/**
 * Allowed fields for set_facts projection
 */
const ALLOWED_FIELDS = [
  'set_id', 'workout_id', 'workout_date', 'workout_end_time',
  'exercise_id', 'exercise_name', 'set_index',
  'reps', 'weight_kg', 'rir', 'rpe', 'is_warmup', 'is_failure',
  'volume', 'e1rm', 'e1rm_confidence',
  'equipment', 'movement_pattern', 'is_isolation',
  'muscle_group_keys', 'muscle_keys'
];

/**
 * Cursor version for format changes
 */
const CURSOR_VERSION = 1;

/**
 * Encode cursor to opaque base64 string
 * @param {Object} payload - Cursor payload
 * @returns {string} - Base64 encoded cursor
 */
function encodeCursor(payload) {
  const cursorData = {
    ...payload,
    version: CURSOR_VERSION,
  };
  return Buffer.from(JSON.stringify(cursorData)).toString('base64url');
}

/**
 * Decode cursor with validation
 * @param {string} cursor - Base64 encoded cursor
 * @param {string} expectedSort - Expected sort mode
 * @returns {Object|null} - Decoded payload or null if invalid
 */
function decodeCursor(cursor, expectedSort) {
  if (!cursor) return null;
  
  try {
    const payload = JSON.parse(Buffer.from(cursor, 'base64url').toString());
    
    // Validate version
    if (payload.version !== CURSOR_VERSION) {
      console.warn('Invalid cursor version:', payload.version);
      return null;
    }
    
    // Validate sort matches (if sort is in cursor)
    if (payload.sort && payload.sort !== expectedSort) {
      console.warn('Cursor sort mismatch:', payload.sort, '!=', expectedSort);
      return null;
    }
    
    return payload;
  } catch (err) {
    console.warn('Cursor decode failed:', err.message);
    return null;
  }
}

/**
 * Enforce query caps and return clamped values
 * @param {Object} request - Request object with limit, fields, window_weeks, target
 * @returns {Object} - { limit, fields, weeks }
 */
function enforceQueryCaps(request) {
  // Clamp limit
  const limit = Math.min(
    Math.max(1, request.limit || CAPS.DEFAULT_LIMIT),
    CAPS.MAX_LIMIT
  );
  
  // Validate and clamp fields
  const fields = (request.fields || [])
    .filter(f => ALLOWED_FIELDS.includes(f))
    .slice(0, CAPS.MAX_FIELDS);
  
  // Clamp weeks
  const weeks = Math.min(
    Math.max(1, request.window_weeks || CAPS.DEFAULT_WEEKS),
    CAPS.MAX_WEEKS
  );
  
  // Validate exercise_ids length
  if (request.target?.exercise_ids?.length > CAPS.MAX_EXERCISE_IDS_FILTER) {
    throw new HttpsError(
      'invalid-argument',
      `exercise_ids exceeds max ${CAPS.MAX_EXERCISE_IDS_FILTER}`
    );
  }
  
  return { limit, fields, weeks };
}

/**
 * Validate exactly one target is specified
 * @param {Object} target - Target object { muscle_group?, muscle?, exercise_ids?, exercise_name? }
 * @throws {HttpsError} - If validation fails
 */
function validateExactlyOneTarget(target) {
  if (!target) {
    throw new HttpsError('invalid-argument', 'target is required');
  }
  
  const count = [
    target.muscle_group,
    target.muscle,
    target.exercise_ids?.length > 0,
    target.exercise_name
  ].filter(Boolean).length;
  
  if (count === 0) {
    throw new HttpsError(
      'invalid-argument',
      'Exactly one target required: muscle_group, muscle, exercise_ids, or exercise_name'
    );
  }
  
  if (count > 1) {
    throw new HttpsError(
      'invalid-argument',
      'Targets are mutually exclusive: provide only one of muscle_group, muscle, exercise_ids, or exercise_name'
    );
  }
}

/**
 * Apply projection to a set_fact document
 * @param {Object} doc - Full set_fact document
 * @param {string[]} fields - Fields to include (empty = all allowed)
 * @returns {Object} - Projected document
 */
function applyProjection(doc, fields) {
  if (!fields || fields.length === 0) {
    // Default projection - include common fields only
    const defaultFields = [
      'set_id', 'workout_date', 'exercise_id', 'exercise_name', 'set_index',
      'reps', 'weight_kg', 'rir', 'volume', 'e1rm'
    ];
    return pickFields(doc, defaultFields);
  }
  return pickFields(doc, fields);
}

/**
 * Pick specific fields from object
 */
function pickFields(obj, fields) {
  const result = {};
  for (const field of fields) {
    if (obj[field] !== undefined) {
      result[field] = obj[field];
    }
  }
  return result;
}

/**
 * Build standard API response envelope with optional truncation
 * @param {any} data - Response data (array or object)
 * @param {Object} options - { limit, hasMore, cursorData }
 * @returns {Object} - Standard response envelope
 */
function buildResponse(data, options = {}) {
  const { limit = CAPS.DEFAULT_LIMIT, hasMore = false, cursorData = null } = options;
  
  let finalData = data;
  let truncated = hasMore;
  
  // Check response size and truncate if needed (for arrays)
  if (Array.isArray(data)) {
    const serialized = JSON.stringify(data);
    const responseBytes = Buffer.byteLength(serialized, 'utf8');
    
    if (responseBytes > CAPS.MAX_RESPONSE_BYTES) {
      // Binary search for safe length
      let lo = 1, hi = data.length;
      while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        const testSize = Buffer.byteLength(JSON.stringify(data.slice(0, mid)), 'utf8');
        if (testSize <= CAPS.MAX_RESPONSE_BYTES) {
          lo = mid;
        } else {
          hi = mid - 1;
        }
      }
      finalData = data.slice(0, lo);
      truncated = true;
    }
  }
  
  // Build cursor for next page if truncated
  let nextCursor = null;
  if (truncated && cursorData) {
    nextCursor = encodeCursor(cursorData);
  }
  
  const response = {
    success: true,
    data: finalData,
    next_cursor: nextCursor,
    truncated,
    meta: {
      returned: Array.isArray(finalData) ? finalData.length : 1,
      limit,
    },
  };
  
  // Add response_bytes for debugging in non-production
  if (process.env.FUNCTIONS_EMULATOR) {
    response.meta.response_bytes = Buffer.byteLength(JSON.stringify(finalData), 'utf8');
  }
  
  return response;
}

/**
 * Build error response
 * @param {string} code - Error code
 * @param {string} message - Error message
 * @param {Object} details - Additional details
 * @returns {Object} - Error response
 */
function buildErrorResponse(code, message, details = null) {
  return {
    success: false,
    data: null,
    next_cursor: null,
    truncated: false,
    error: {
      code,
      message,
      details,
    },
    meta: { returned: 0, limit: 0 },
  };
}

/**
 * Require auth and return userId
 * Supports both Firebase Auth context and userId from body (for agent access)
 * @param {Object} request - Firebase callable request
 * @returns {string} - User ID
 * @throws {HttpsError} - If not authenticated
 */
function requireAuth(request) {
  // First try Firebase Auth context
  if (request.auth?.uid) {
    return request.auth.uid;
  }
  
  // Fall back to userId from body (agent access via API key)
  const bodyUserId = request.data?.userId;
  if (bodyUserId) {
    return bodyUserId;
  }
  
  throw new HttpsError('unauthenticated', 'Authentication required');
}

/**
 * Get week start date (Monday) for a given date
 * @param {Date|Timestamp} date - Input date
 * @returns {string} - YYYY-MM-DD format week start
 */
function getWeekStart(date) {
  const d = date instanceof Date ? date : date.toDate();
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Adjust to Monday
  const monday = new Date(d.setDate(diff));
  return monday.toISOString().split('T')[0];
}

/**
 * Format date as YYYY-MM-DD
 * @param {Date|Timestamp} date - Input date
 * @returns {string} - YYYY-MM-DD format
 */
function formatDate(date) {
  const d = date instanceof Date ? date : date.toDate();
  return d.toISOString().split('T')[0];
}

/**
 * Get reps bucket key for a rep count
 * @param {number} reps - Rep count
 * @returns {string} - Bucket key ('1-5', '6-10', '11-15', '16-20')
 */
function getRepsBucket(reps) {
  if (reps <= 5) return '1-5';
  if (reps <= 10) return '6-10';
  if (reps <= 15) return '11-15';
  return '16-20';
}

/**
 * Compute avg_rir from stored sums/counts
 * @param {Object} point - Weekly point with rir_sum and rir_count
 * @returns {number|null} - Computed average or null
 */
function computeAvgRir(point) {
  if (!point.rir_count || point.rir_count === 0) return null;
  return Math.round((point.rir_sum / point.rir_count) * 10) / 10;
}

/**
 * Compute failure_rate from stored counts
 * @param {Object} point - Weekly point with failure_sets and set_count
 * @returns {number} - Failure rate 0-1
 */
function computeFailureRate(point) {
  if (!point.set_count || point.set_count === 0) return 0;
  return Math.round((point.failure_sets / point.set_count) * 100) / 100;
}

/**
 * Transform stored weekly point to API response format
 * Computes derived fields (avg_rir, failure_rate) from stored sums/counts
 * @param {Object} point - Raw stored weekly point
 * @returns {Object} - Transformed point for API response
 */
function transformWeeklyPoint(point) {
  return {
    week_start: point.week_start,
    sets: point.sets || 0,
    hard_sets: point.hard_sets || 0,
    volume: point.volume || 0,
    effective_volume: point.effective_volume,
    avg_rir: computeAvgRir(point),
    failure_rate: computeFailureRate(point),
    reps_bucket: point.reps_bucket || { '1-5': 0, '6-10': 0, '11-15': 0, '16-20': 0 },
    e1rm_max: point.e1rm_max,
  };
}

module.exports = {
  CAPS,
  ALLOWED_FIELDS,
  CURSOR_VERSION,
  encodeCursor,
  decodeCursor,
  enforceQueryCaps,
  validateExactlyOneTarget,
  applyProjection,
  pickFields,
  buildResponse,
  buildErrorResponse,
  requireAuth,
  getWeekStart,
  formatDate,
  getRepsBucket,
  computeAvgRir,
  computeFailureRate,
  transformWeeklyPoint,
};
