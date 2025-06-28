const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Search Exercises
 */
async function searchExercisesHandler(req, res) {
  const { query, muscleGroup, equipment, difficulty } = req.query;

  try {
    let queryParams = {};
    let filters = [];

    if (muscleGroup) {
      filters.push({
        field: 'muscleCategories',
        operator: 'array-contains',
        value: muscleGroup
      });
    }

    if (equipment) {
      filters.push({
        field: 'equipment',
        operator: 'array-contains',
        value: equipment
      });
    }

    if (filters.length > 0) {
      queryParams.where = filters;
    }

    let exercises = await db.getDocuments('exercises', queryParams);

    // Text search if query provided
    if (query) {
      const searchTerm = query.toLowerCase();
      exercises = exercises.filter(exercise => 
        exercise.name.toLowerCase().includes(searchTerm) ||
        exercise.primaryMuscles?.some(muscle => muscle.toLowerCase().includes(searchTerm)) ||
        exercise.muscleCategories?.some(category => category.toLowerCase().includes(searchTerm))
      );
    }

    return res.status(200).json({
      success: true,
      data: exercises,
      count: exercises.length,
      filters: {
        query: query || null,
        muscleGroup: muscleGroup || null,
        equipment: equipment || null,
        difficulty: difficulty || null
      },
      metadata: {
        function: 'search-exercises',
        requestedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('search-exercises function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to search exercises',
      details: error.message
    });
  }
}

exports.searchExercises = onRequest(requireFlexibleAuth(searchExercisesHandler)); 