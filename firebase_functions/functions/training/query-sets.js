/**
 * Query Sets Endpoint
 * Token-safe paginated query for set_facts with filters
 *
 * Uses onRequest (not onCall) for compatibility with HTTP clients.
 * Bearer auth (iOS + agent)
 *
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 6.1
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const {
  CAPS,
  buildResponse,
  enforceQueryCaps,
  validateExactlyOneTarget,
  applyProjection,
  decodeCursor,
  encodeCursor,
} = require('../utils/caps');
const { validateMuscleGroupWithRecovery, validateMuscleWithRecovery } = require('../utils/muscle-taxonomy');

/**
 * Valid sort options
 */
const SORT_OPTIONS = ['date_desc', 'date_asc', 'e1rm_desc', 'volume_desc'];

/**
 * training.sets.query
 * Query set_facts with filters, pagination, and projection
 */
exports.querySets = onRequest(requireFlexibleAuth(async (req, res) => {
  try {
    const userId = req.auth?.uid || req.body?.userId;
    if (!userId) {
      return fail(res, 'MISSING_USER_ID', 'userId is required', null, 400);
    }
    const data = req.body || {};

    const { target, classification, effort, performance, sort, cursor, start, end, limit, fields } = data;

    // Validate exactly one target
    validateExactlyOneTarget(target);

    // Enforce caps
    const caps = enforceQueryCaps({ limit, fields, target });
    const actualLimit = caps.limit;
    const projectedFields = caps.fields;

    // Validate sort
    const sortMode = sort || 'date_desc';
    if (!SORT_OPTIONS.includes(sortMode)) {
      return fail(res, 'INVALID_ARGUMENT', `Invalid sort: ${sortMode}. Valid: ${SORT_OPTIONS.join(', ')}`, null, 400);
    }

    // Decode cursor if present
    const cursorData = decodeCursor(cursor, sortMode);

    // Build query
    let query = db.collection('users').doc(userId).collection('set_facts');

    // Target filter (exactly one) with self-healing validation
    if (target.muscle_group) {
      const validation = validateMuscleGroupWithRecovery(target.muscle_group);
      if (!validation.valid) {
        return fail(res, 'INVALID_ARGUMENT', validation.message, {
          validOptions: validation.validOptions,
          hint: 'Use one of the validOptions values for muscle_group',
        }, 400);
      }
      query = query.where('muscle_group_keys', 'array-contains', target.muscle_group);
    } else if (target.muscle) {
      const validation = validateMuscleWithRecovery(target.muscle);
      if (!validation.valid) {
        return fail(res, 'INVALID_ARGUMENT', validation.message, {
          validOptions: validation.validOptions,
          suggestions: validation.suggestions,
          hint: 'Use one of the suggestions or validOptions values for muscle',
        }, 400);
      }
      query = query.where('muscle_keys', 'array-contains', target.muscle);
    } else if (target.exercise_name) {
      // Fuzzy search by exercise name - find matching exercise_ids from user's set_facts
      const nameQuery = target.exercise_name.toLowerCase().trim();
      const exerciseScan = await db.collection('users').doc(userId).collection('set_facts')
        .where('is_warmup', '==', false)
        .orderBy('workout_end_time', 'desc')
        .limit(500)
        .get();

      // Find distinct exercise_ids where name matches
      const matchingIds = new Set();
      for (const doc of exerciseScan.docs) {
        const sf = doc.data();
        const exerciseName = (sf.exercise_name || '').toLowerCase();
        if (exerciseName.includes(nameQuery) || nameQuery.includes(exerciseName.split(' ')[0])) {
          matchingIds.add(sf.exercise_id);
          if (matchingIds.size >= CAPS.MAX_EXERCISE_IDS_FILTER) break;
        }
      }

      if (matchingIds.size === 0) {
        // Return empty result with helpful message
        return ok(res, buildResponse([], {
          limit: actualLimit,
          hasMore: false,
          message: `No exercises found matching "${target.exercise_name}" in your training history`,
        }));
      }

      query = query.where('exercise_id', 'in', Array.from(matchingIds));
    } else if (target.exercise_ids?.length > 0) {
      // exercise_ids uses 'in' query
      query = query.where('exercise_id', 'in', target.exercise_ids.slice(0, CAPS.MAX_EXERCISE_IDS_FILTER));
    }

    // Date range filters
    if (start) {
      query = query.where('workout_date', '>=', start);
    }
    if (end) {
      query = query.where('workout_date', '<=', end);
    }

    // Classification filters
    if (classification) {
      if (classification.equipment) {
        query = query.where('equipment', '==', classification.equipment);
      }
      if (classification.movement_pattern) {
        query = query.where('movement_pattern', '==', classification.movement_pattern);
      }
      if (classification.is_isolation !== undefined) {
        query = query.where('is_isolation', '==', classification.is_isolation);
      }
    }

    // Effort filters
    const includeWarmups = effort?.include_warmups || false;
    if (!includeWarmups) {
      query = query.where('is_warmup', '==', false);
    }
    if (effort?.is_failure !== undefined) {
      query = query.where('is_failure', '==', effort.is_failure);
    }

    // Apply sort and pagination
    // When date range filters (start/end) are present, Firestore requires
    // the first orderBy to be on the inequality field (workout_date).
    const hasDateRange = !!(start || end);
    let firestoreSort = hasDateRange ? 'workout_date' : 'workout_end_time';
    let firestoreDirection = 'desc';

    if (sortMode === 'date_asc') {
      firestoreDirection = 'asc';
    }

    query = query.orderBy(firestoreSort, firestoreDirection);

    // Apply cursor
    if (cursorData?.last_value) {
      // When sorting by workout_date (string), use string cursor; otherwise Date
      const cursorValue = hasDateRange ? cursorData.last_value : new Date(cursorData.last_value);
      query = query.startAfter(cursorValue);
    }

    // Limit +1 to detect hasMore
    query = query.limit(actualLimit + 1);

    // Execute query
    const snapshot = await query.get();
    let results = snapshot.docs.map(doc => ({ ...doc.data(), set_id: doc.id }));

    // Post-query filters (for fields not supported in Firestore query)
    if (effort?.rir_min !== undefined) {
      results = results.filter(r => r.rir !== null && r.rir >= effort.rir_min);
    }
    if (effort?.rir_max !== undefined) {
      results = results.filter(r => r.rir !== null && r.rir <= effort.rir_max);
    }
    if (effort?.rpe_min !== undefined) {
      results = results.filter(r => r.rpe !== null && r.rpe >= effort.rpe_min);
    }
    if (effort?.rpe_max !== undefined) {
      results = results.filter(r => r.rpe !== null && r.rpe <= effort.rpe_max);
    }

    if (performance?.reps_min !== undefined) {
      results = results.filter(r => r.reps >= performance.reps_min);
    }
    if (performance?.reps_max !== undefined) {
      results = results.filter(r => r.reps <= performance.reps_max);
    }
    if (performance?.weight_min !== undefined) {
      results = results.filter(r => r.weight_kg >= performance.weight_min);
    }
    if (performance?.weight_max !== undefined) {
      results = results.filter(r => r.weight_kg <= performance.weight_max);
    }
    if (performance?.e1rm_min !== undefined) {
      results = results.filter(r => r.e1rm !== null && r.e1rm >= performance.e1rm_min);
    }
    if (performance?.e1rm_max !== undefined) {
      results = results.filter(r => r.e1rm !== null && r.e1rm <= performance.e1rm_max);
    }

    // Handle special sorts that require post-query sorting
    if (sortMode === 'e1rm_desc') {
      results.sort((a, b) => (b.e1rm || 0) - (a.e1rm || 0));
    } else if (sortMode === 'volume_desc') {
      results.sort((a, b) => (b.volume || 0) - (a.volume || 0));
    }

    // Check hasMore
    const hasMore = results.length > actualLimit;
    if (hasMore) {
      results = results.slice(0, actualLimit);
    }

    // Build next cursor
    let nextCursorData = null;
    if (hasMore && results.length > 0) {
      const lastResult = results[results.length - 1];
      const endTime = lastResult.workout_end_time;
      nextCursorData = {
        sort: sortMode,
        last_value: endTime?.toDate ? endTime.toDate().toISOString() : endTime,
      };
    }

    // Apply projection
    const projectedResults = results.map(r => applyProjection(r, projectedFields));

    return ok(res, buildResponse(projectedResults, {
      limit: actualLimit,
      hasMore,
      cursorData: nextCursorData,
    }));

  } catch (error) {
    console.error('Error in querySets:', error);
    return fail(res, 'INTERNAL', error.message, null, 500);
  }
}));

/**
 * training.sets.aggregate
 * Compute rollups from set_facts for custom grouping
 */
exports.aggregateSets = onRequest(requireFlexibleAuth(async (req, res) => {
  try {
    const userId = req.auth?.uid || req.body?.userId;
    if (!userId) {
      return fail(res, 'MISSING_USER_ID', 'userId is required', null, 400);
    }
    const data = req.body || {};

    const { target, group_by, metrics, start, end } = data;

    // Validate target
    validateExactlyOneTarget(target);

    // Validate group_by
    const validGroupBy = ['day', 'week', 'exercise', 'muscle_group', 'muscle'];
    const groupBy = group_by || 'week';
    if (!validGroupBy.includes(groupBy)) {
      return fail(res, 'INVALID_ARGUMENT', `Invalid group_by: ${groupBy}. Valid: ${validGroupBy.join(', ')}`, null, 400);
    }

    // Validate metrics
    const validMetrics = ['sets', 'hard_sets', 'volume', 'effective_volume', 'avg_rir', 'failure_rate', 'e1rm_max'];
    const requestedMetrics = metrics || ['sets', 'volume'];
    for (const m of requestedMetrics) {
      if (!validMetrics.includes(m)) {
        return fail(res, 'INVALID_ARGUMENT', `Invalid metric: ${m}`, null, 400);
      }
    }

    // Build query
    let query = db.collection('users').doc(userId).collection('set_facts')
      .where('is_warmup', '==', false);

    // Target filter
    if (target.muscle_group) {
      query = query.where('muscle_group_keys', 'array-contains', target.muscle_group);
    } else if (target.muscle) {
      query = query.where('muscle_keys', 'array-contains', target.muscle);
    } else if (target.exercise_ids?.length > 0) {
      query = query.where('exercise_id', 'in', target.exercise_ids.slice(0, CAPS.MAX_EXERCISE_IDS_FILTER));
    }

    // Date range
    if (start) {
      query = query.where('workout_date', '>=', start);
    }
    if (end) {
      query = query.where('workout_date', '<=', end);
    }

    // Limit to prevent overfetch
    query = query.limit(CAPS.MAX_LIMIT * 10); // 2000 max for aggregation

    const snapshot = await query.get();
    const results = snapshot.docs.map(doc => doc.data());

    // Group results
    const groups = new Map();

    for (const sf of results) {
      let groupKey;

      switch (groupBy) {
        case 'day':
          groupKey = sf.workout_date;
          break;
        case 'week':
          // Get week start from workout_date
          const d = new Date(sf.workout_date);
          const day = d.getDay();
          const diff = d.getDate() - day + (day === 0 ? -6 : 1);
          const monday = new Date(d.setDate(diff));
          groupKey = monday.toISOString().split('T')[0];
          break;
        case 'exercise':
          groupKey = sf.exercise_id;
          break;
        case 'muscle_group':
          // Aggregate to each group this set contributes to
          for (const group of sf.muscle_group_keys || []) {
            aggregateToGroup(groups, group, sf, target.muscle_group === group ? 1 : (sf.muscle_group_contrib?.[group] || 0.5));
          }
          continue; // Skip main aggregation
        case 'muscle':
          // Aggregate to each muscle this set contributes to
          for (const muscle of sf.muscle_keys || []) {
            aggregateToGroup(groups, muscle, sf, target.muscle === muscle ? 1 : (sf.muscle_contrib?.[muscle] || 0.5));
          }
          continue; // Skip main aggregation
        default:
          groupKey = 'all';
      }

      aggregateToGroup(groups, groupKey, sf, 1);
    }

    // Format output
    const output = [];
    for (const [key, agg] of groups) {
      const point = { group_key: key };

      for (const metric of requestedMetrics) {
        switch (metric) {
          case 'sets':
            point.sets = agg.sets;
            break;
          case 'hard_sets':
            point.hard_sets = Math.round(agg.hard_sets * 10) / 10;
            break;
          case 'volume':
            point.volume = Math.round(agg.volume * 10) / 10;
            break;
          case 'effective_volume':
            point.effective_volume = Math.round(agg.effective_volume * 10) / 10;
            break;
          case 'avg_rir':
            point.avg_rir = agg.rir_count > 0 ? Math.round((agg.rir_sum / agg.rir_count) * 10) / 10 : null;
            break;
          case 'failure_rate':
            point.failure_rate = agg.sets > 0 ? Math.round((agg.failure_sets / agg.sets) * 100) / 100 : 0;
            break;
          case 'e1rm_max':
            point.e1rm_max = agg.e1rm_max;
            break;
        }
      }

      output.push(point);
    }

    // Sort by group_key
    output.sort((a, b) => a.group_key.localeCompare(b.group_key));

    return ok(res, buildResponse(output, { limit: output.length }));

  } catch (error) {
    console.error('Error in aggregateSets:', error);
    return fail(res, 'INTERNAL', error.message, null, 500);
  }
}));

/**
 * Helper to aggregate a set_fact into a group
 */
function aggregateToGroup(groups, key, sf, weight) {
  if (!groups.has(key)) {
    groups.set(key, {
      sets: 0,
      hard_sets: 0,
      volume: 0,
      effective_volume: 0,
      rir_sum: 0,
      rir_count: 0,
      failure_sets: 0,
      e1rm_max: null,
    });
  }

  const agg = groups.get(key);
  agg.sets += 1;
  agg.hard_sets += (sf.hard_set_credit || 0) * weight;
  agg.volume += (sf.volume || 0) * weight;
  agg.effective_volume += (sf.volume || 0) * weight;

  if (sf.rir !== null && sf.rir !== undefined) {
    agg.rir_sum += sf.rir;
    agg.rir_count += 1;
  }

  if (sf.is_failure) {
    agg.failure_sets += 1;
  }

  if (sf.e1rm !== null && (agg.e1rm_max === null || sf.e1rm > agg.e1rm_max)) {
    agg.e1rm_max = sf.e1rm;
  }
}
