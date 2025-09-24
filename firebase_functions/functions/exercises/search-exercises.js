const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Search Exercises
 */
async function searchExercisesHandler(req, res) {
  const {
    query,
    category,
    movementType,
    split,
    equipment,
    muscleGroup,
    primaryMuscle,
    secondaryMuscle,
    difficulty, // maps to metadata.level
    planeOfMotion,
    unilateral,
    stimulusTag,
    programmingUseCase,
    limit,
    includeMerged,
    canonicalOnly
  } = req.query || {};

  try {
    const where = [];
    if (muscleGroup) {
      // Field path per model: muscles.category: string[]
      where.push({ field: 'muscles.category', operator: 'array-contains', value: muscleGroup });
    }
    if (equipment) {
      const equipArr = String(equipment).split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);
      if (equipArr.length > 1) {
        where.push({ field: 'equipment', operator: 'array-contains-any', value: equipArr });
      } else if (equipArr.length === 1) {
        where.push({ field: 'equipment', operator: 'array-contains', value: equipArr[0] });
      }
    }
    if (difficulty) {
      // Per model: metadata.level
      where.push({ field: 'metadata.level', operator: '==', value: difficulty });
    }
    if (category) {
      where.push({ field: 'category', operator: '==', value: String(category) });
    }
    if (movementType) {
      where.push({ field: 'movement.type', operator: '==', value: String(movementType) });
    }
    if (split) {
      where.push({ field: 'movement.split', operator: '==', value: String(split) });
    }
    if (planeOfMotion) {
      where.push({ field: 'metadata.plane_of_motion', operator: '==', value: String(planeOfMotion) });
    }
    if (unilateral !== undefined) {
      const parsedBool = String(unilateral).toLowerCase();
      if (parsedBool === 'true' || parsedBool === 'false') {
        where.push({ field: 'metadata.unilateral', operator: '==', value: parsedBool === 'true' });
      }
    }
    if (primaryMuscle) {
      const arr = String(primaryMuscle).split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);
      if (arr.length > 1) {
        where.push({ field: 'muscles.primary', operator: 'array-contains-any', value: arr });
      } else if (arr.length === 1) {
        where.push({ field: 'muscles.primary', operator: 'array-contains', value: arr[0] });
      }
    }
    if (secondaryMuscle) {
      const arr = String(secondaryMuscle).split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);
      if (arr.length > 1) {
        where.push({ field: 'muscles.secondary', operator: 'array-contains-any', value: arr });
      } else if (arr.length === 1) {
        where.push({ field: 'muscles.secondary', operator: 'array-contains', value: arr[0] });
      }
    }
    if (stimulusTag) {
      const arr = String(stimulusTag).split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);
      if (arr.length > 1) {
        where.push({ field: 'stimulus_tags', operator: 'array-contains-any', value: arr });
      } else if (arr.length === 1) {
        where.push({ field: 'stimulus_tags', operator: 'array-contains', value: arr[0] });
      }
    }
    if (programmingUseCase) {
      const arr = String(programmingUseCase).split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);
      if (arr.length > 1) {
        where.push({ field: 'programming_use_cases', operator: 'array-contains-any', value: arr });
      } else if (arr.length === 1) {
        where.push({ field: 'programming_use_cases', operator: 'array-contains', value: arr[0] });
      }
    }
    const parsedLimit = parseInt(limit) || 50;
    const mergedFlag = String(includeMerged || '').toLowerCase() === 'true';
    const canonicalFlag = mergedFlag ? false : (String(canonicalOnly || 'true').toLowerCase() !== 'false');
    const queryParams = {};
    if (where.length) queryParams.where = where;
    queryParams.limit = parsedLimit;

    let exercises;
    if (query && !where.length) {
      try {
        // Prefix search on name using range query for efficiency when no other filters
        const ts = db.createTextSearch('name', String(query));
        const tsParams = { where: ts.where, orderBy: { field: 'name', direction: 'asc' }, limit: parsedLimit };
        exercises = await db.getDocuments('exercises', tsParams);
      } catch (e) {
        console.warn('Prefix text search failed, falling back to scan:', e.message || e);
        exercises = await db.getDocuments('exercises', { orderBy: { field: 'name', direction: 'asc' }, limit: parsedLimit });
      }
    } else {
      exercises = await db.getDocuments('exercises', queryParams);
    }

    // Text search if query provided
    if (query) {
      const searchTerm = query.toLowerCase();
      exercises = exercises.filter(ex => {
        const name = (ex.name || '').toLowerCase();
        const category = (ex.category || '').toLowerCase();
        const movementType = (ex.movement?.type || '').toLowerCase();
        const equipmentText = Array.isArray(ex.equipment) ? ex.equipment.join(' ').toLowerCase() : '';
        const primary = Array.isArray(ex.muscles?.primary) ? ex.muscles.primary.map(m=>m.toLowerCase()) : [];
        const secondary = Array.isArray(ex.muscles?.secondary) ? ex.muscles.secondary.map(m=>m.toLowerCase()) : [];
        const groups = Array.isArray(ex.muscles?.category) ? ex.muscles.category.map(g=>g.toLowerCase()) : [];
        const notes = Array.isArray(ex.execution_notes) ? ex.execution_notes.join(' ').toLowerCase() : '';
        const mistakes = Array.isArray(ex.common_mistakes) ? ex.common_mistakes.join(' ').toLowerCase() : '';
        const programming = Array.isArray(ex.programming_use_cases) ? ex.programming_use_cases.join(' ').toLowerCase() : '';
        const tags = Array.isArray(ex.stimulus_tags) ? ex.stimulus_tags.map(t=>t.toLowerCase()) : [];
        return (
          name.includes(searchTerm) ||
          category.includes(searchTerm) ||
          movementType.includes(searchTerm) ||
          equipmentText.includes(searchTerm) ||
          primary.some(m => m.includes(searchTerm)) ||
          secondary.some(m => m.includes(searchTerm)) ||
          groups.some(g => g.includes(searchTerm)) ||
          notes.includes(searchTerm) ||
          mistakes.includes(searchTerm) ||
          programming.includes(searchTerm) ||
          tags.some(t => t.includes(searchTerm))
        );
      });
    }

    // Filter out merged/source docs unless explicitly included
    if (canonicalFlag) {
      exercises = exercises.filter(ex => !ex?.merged_into && (ex?.status || '').toLowerCase() !== 'merged');
    }

    return ok(res, { items: exercises, count: exercises.length, filters: {
      query: query || null,
      category: category || null,
      muscleGroup: muscleGroup || null,
      primaryMuscle: primaryMuscle || null,
      secondaryMuscle: secondaryMuscle || null,
      equipment: equipment || null,
      difficulty: difficulty || null,
      planeOfMotion: planeOfMotion || null,
      unilateral: unilateral ?? null,
      movementType: movementType || null,
      split: split || null,
      stimulusTag: stimulusTag || null,
      programmingUseCase: programmingUseCase || null,
      limit: parsedLimit,
      canonicalOnly: canonicalFlag,
      includeMerged: mergedFlag
    } });

  } catch (error) {
    console.error('search-exercises function error:', error);
    return fail(res, 'INTERNAL', 'Failed to search exercises', { message: error.message }, 500);
  }
}

exports.searchExercises = onRequest(requireFlexibleAuth(searchExercisesHandler)); 