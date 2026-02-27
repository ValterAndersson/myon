/**
 * Active Events Endpoint
 * Paginated workout events for agent context
 * 
 * This endpoint provides incremental event updates for active workouts,
 * allowing the agent to track changes without reading full state.
 * 
 * @module training/active-events
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 3.12
 * 
 * ## Usage Example:
 * ```javascript
 * // Get initial events
 * const result = await getActiveEvents({ limit: 20 });
 * 
 * // Get events after a specific version
 * const updates = await getActiveEvents({ 
 *   after_version: 5,
 *   limit: 20 
 * });
 * ```
 * 
 * ## Response Structure:
 * ```json
 * {
 *   "success": true,
 *   "data": [
 *     {
 *       "type": "set_logged",
 *       "version": 6,
 *       "payload": { "exercise_id": "...", "set_index": 0, ... },
 *       "created_at": "2024-01-15T10:30:00Z"
 *     }
 *   ],
 *   "next_cursor": "...",
 *   "truncated": false,
 *   "meta": { "returned": 5, "limit": 20 }
 * }
 * ```
 * 
 * ## Error Recovery:
 * - Returns empty array if no active workout exists
 * - Invalid cursor returns from start with warning
 * - All errors include actionable error messages
 */

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const {
  CAPS,
  buildResponse,
  requireAuth,
  decodeCursor,
  encodeCursor,
} = require('../utils/caps');

/**
 * Event type definitions for documentation
 * 
 * | Type | Description | Payload |
 * |------|-------------|---------|
 * | `set_logged` | Set completed | `{ exercise_id, set_index, reps, weight_kg, rir? }` |
 * | `exercise_added` | Exercise added | `{ exercise_id, name, position }` |
 * | `exercise_swapped` | Exercise replaced | `{ old_id, new_id, name }` |
 * | `exercise_removed` | Exercise removed | `{ exercise_id, position }` |
 * | `set_modified` | Set data changed | `{ exercise_id, set_index, changes }` |
 * | `workout_started` | Session began | `{ template_id?, source }` |
 * | `workout_completed` | Session finished | `{ duration_seconds, totals }` |
 */
const EVENT_TYPES = [
  'set_logged',
  'exercise_added', 
  'exercise_swapped',
  'exercise_removed',
  'set_modified',
  'workout_started',
  'workout_completed',
];

/**
 * Caps specific to active events
 */
const EVENTS_CAPS = {
  DEFAULT_LIMIT: 20,
  MAX_LIMIT: 50,
};

/**
 * active.events.list
 * Get paginated workout events for an active workout
 * 
 * @param {object} request.data - Request parameters
 * @param {string} [request.data.workout_id] - Optional workout ID (defaults to current active)
 * @param {number} [request.data.after_version] - Get events after this version number
 * @param {string} [request.data.after_timestamp] - Get events after this ISO timestamp
 * @param {number} [request.data.limit=20] - Number of events to return (max 50)
 * @param {string} [request.data.cursor] - Pagination cursor from previous response
 * 
 * @returns {object} Standard API response with events array
 * 
 * @example
 * // Initial fetch
 * getActiveEvents({ limit: 20 })
 * 
 * @example
 * // Incremental update using version
 * getActiveEvents({ after_version: 10, limit: 20 })
 * 
 * @example
 * // Using cursor from previous response
 * getActiveEvents({ cursor: "eyJ...", limit: 20 })
 */
exports.getActiveEvents = onCall(async (request) => {
  try {
    const userId = requireAuth(request);
    const data = request.data || {};
    
    const { workout_id, after_version, after_timestamp, cursor, limit: requestLimit } = data;
    
    // Apply caps
    const limit = Math.min(
      Math.max(1, requestLimit || EVENTS_CAPS.DEFAULT_LIMIT),
      EVENTS_CAPS.MAX_LIMIT
    );
    
    // Determine workout ID
    let targetWorkoutId = workout_id;
    if (!targetWorkoutId) {
      // Get current active workout
      const activeRef = db.collection('users').doc(userId)
        .collection('active_workouts').doc('current');
      const activeDoc = await activeRef.get();
      
      if (!activeDoc.exists) {
        return buildResponse([], {
          limit,
          hasMore: false,
          message: 'No active workout found',
        });
      }
      
      const activeData = activeDoc.data();
      targetWorkoutId = activeData.workout_id || 'current';
    }
    
    // Get events collection
    const eventsRef = db.collection('users').doc(userId)
      .collection('active_workouts').doc(targetWorkoutId)
      .collection('events');
    
    // Build query
    let query = eventsRef.orderBy('version', 'asc');
    
    // Apply version filter
    if (after_version !== undefined) {
      query = query.where('version', '>', after_version);
    } else if (after_timestamp) {
      const afterDate = new Date(after_timestamp);
      query = query.where('created_at', '>', admin.firestore.Timestamp.fromDate(afterDate));
    } else if (cursor) {
      // Decode cursor
      const cursorData = decodeCursor(cursor, 'version_asc');
      if (cursorData?.last_version) {
        query = query.where('version', '>', cursorData.last_version);
      }
    }
    
    // Limit +1 to detect more
    query = query.limit(limit + 1);
    
    // Execute
    const snapshot = await query.get();
    
    let events = snapshot.docs.map(doc => {
      const event = doc.data();
      return {
        type: event.type,
        version: event.version,
        payload: event.payload || {},
        created_at: event.created_at?.toDate?.()?.toISOString() || event.created_at,
      };
    });
    
    // Check hasMore
    const hasMore = events.length > limit;
    if (hasMore) {
      events = events.slice(0, limit);
    }
    
    // Build next cursor
    let nextCursorData = null;
    if (hasMore && events.length > 0) {
      const lastEvent = events[events.length - 1];
      nextCursorData = {
        sort: 'version_asc',
        last_version: lastEvent.version,
      };
    }
    
    return buildResponse(events, {
      limit,
      hasMore,
      cursorData: nextCursorData,
    });
    
  } catch (error) {
    if (error instanceof HttpsError) throw error;
    console.error('Error in getActiveEvents:', error);
    throw new HttpsError('internal', 'Failed to get events');
  }
});
