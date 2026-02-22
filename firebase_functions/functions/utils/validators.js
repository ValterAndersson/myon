const { z } = require('zod');

// Shared schemas
const IdSchema = z.string().min(1);

const PreferencesSchema = z.object({
  timezone: z.string().optional(),
  weight_format: z.enum(['kilograms','pounds']).optional(),
  height_format: z.enum(['centimeter','feet']).optional(),
  week_starts_on_monday: z.boolean().optional(),
  locale: z.string().optional(),
});

const PlanSchema = z.object({
  blocks: z.array(z.object({
    exercise_id: IdSchema,
    sets: z.array(z.object({
      target: z.object({ reps: z.number().int().min(1), rir: z.number().int().min(0).max(5), weight: z.number().nullable().optional(), tempo: z.string().optional(), rest_sec: z.number().int().optional() })
    })),
    alts: z.array(z.object({ exercise_id: IdSchema, reason: z.string().optional() })).optional()
  }))
});

const PrescribeSchema = z.object({
  workout_id: IdSchema,
  exercise_id: IdSchema,
  set_index: z.number().int().min(0),
  context: z.any().optional()
});

// Legacy LogSetSchema - deprecated, use LogSetSchemaV2
const LogSetSchema = z.object({
  workout_id: IdSchema,
  exercise_id: IdSchema,
  set_index: z.number().int().min(0),
  actual: z.object({ reps: z.number().int().min(0), rir: z.number().int().min(0).max(5), weight: z.number().optional(), tempo: z.string().optional(), notes: z.string().optional() })
});

/**
 * LogSetSchemaV2 - Per FOCUS_MODE_WORKOUT_EXECUTION.md spec
 * Uses stable IDs (exercise_instance_id + set_id) instead of position-based (exercise_id + set_index)
 * 
 * Validation rules:
 * - reps: 0-30 (0 requires is_failure=true)
 * - rir: 0-5
 * - weight: >= 0 or null (null for bodyweight)
 */
const LogSetSchemaV2 = z.object({
  workout_id: IdSchema,
  exercise_instance_id: IdSchema,           // Workout-local stable ID (UUID)
  set_id: IdSchema,                          // Stable set ID (UUID)
  values: z.object({
    weight: z.number().nonnegative().nullable(), // kg, null for bodyweight
    reps: z.number().int().min(0).max(30),       // 0-30 (0 requires is_failure)
    rir: z.number().int().min(0).max(5),         // Reps In Reserve
  }),
  is_failure: z.boolean().optional(),            // Required if reps=0
  idempotency_key: IdSchema,                     // Required for idempotency
  client_timestamp: z.string().optional(),       // ISO 8601 timestamp
}).refine(
  (data) => {
    // If reps is 0, is_failure must be true
    if (data.values.reps === 0 && data.is_failure !== true) {
      return false;
    }
    return true;
  },
  { message: 'reps=0 requires is_failure=true' }
);

const ScoreSetSchema = z.object({ actual: z.object({ reps: z.number(), rir: z.number(), weight: z.number().optional() }) });

/**
 * PatchActiveWorkoutSchema - Per FOCUS_MODE_WORKOUT_EXECUTION.md spec
 * 
 * Supports:
 * - set_field: Update a single field on a set
 * - add_set: Add a new set to an exercise
 * - remove_set: Remove a set from an exercise
 * 
 * Homogeneous constraint: 
 * - Only one op type per request
 * - set_field ops must target same set
 */
const PatchOpSchema = z.discriminatedUnion('op', [
  // Field update on a set
  z.object({
    op: z.literal('set_field'),
    target: z.object({
      exercise_instance_id: IdSchema,
      set_id: IdSchema,
    }),
    field: z.enum(['weight', 'reps', 'rir', 'status', 'set_type', 'tags.is_failure']),
    value: z.any(),
  }),
  // Field update on the workout itself (name, start_time, notes)
  z.object({
    op: z.literal('set_workout_field'),
    field: z.enum(['name', 'start_time', 'notes']),
    value: z.string().max(500),
  }),
  // Field update on an exercise instance (notes, etc.)
  z.object({
    op: z.literal('set_exercise_field'),
    target: z.object({ exercise_instance_id: IdSchema }),
    field: z.enum(['notes']),
    value: z.string().max(500),
  }),
  // Add set
  z.object({
    op: z.literal('add_set'),
    target: z.object({
      exercise_instance_id: IdSchema,
    }),
    value: z.object({
      id: IdSchema,                                      // Client-generated UUID (required)
      set_type: z.enum(['warmup', 'working', 'dropset']),
      reps: z.number().int().min(1).max(30),             // 1-30 for planned sets
      rir: z.number().int().min(0).max(5),
      weight: z.number().nonnegative().nullable().optional(),  // Optional, defaults to null
      status: z.literal('planned'),                       // Must be 'planned'
      tags: z.object({}).optional(),
    }),
  }),
  // Remove set
  z.object({
    op: z.literal('remove_set'),
    target: z.object({
      exercise_instance_id: IdSchema,
      set_id: IdSchema,
    }),
  }),
  // Reorder exercises
  z.object({
    op: z.literal('reorder_exercises'),
    value: z.object({
      order: z.array(IdSchema).min(1),  // Array of exercise instance IDs in new order
    }),
  }),
]);

const PatchActiveWorkoutSchema = z.object({
  workout_id: IdSchema,
  ops: z.array(PatchOpSchema).min(1),
  cause: z.enum(['user_edit', 'user_ai_action']),
  ui_source: z.string(),
  idempotency_key: IdSchema,
  client_timestamp: z.string().optional(),
  ai_scope: z.object({
    exercise_instance_id: IdSchema,
  }).optional(), // Required when cause is 'user_ai_action'
}).refine(
  (data) => {
    // If cause is 'user_ai_action', ai_scope is required
    if (data.cause === 'user_ai_action' && !data.ai_scope) {
      return false;
    }
    return true;
  },
  { message: 'ai_scope is required when cause is user_ai_action' }
);

/**
 * AutofillExerciseSchema - Per FOCUS_MODE_WORKOUT_EXECUTION.md spec
 * AI bulk prescription for a single exercise
 */
const AutofillExerciseSchema = z.object({
  workout_id: IdSchema,
  exercise_instance_id: IdSchema,
  updates: z.array(z.object({
    set_id: IdSchema,
    weight: z.number().nonnegative().nullable().optional(),
    reps: z.number().int().min(1).max(30).optional(),
    rir: z.number().int().min(0).max(5).optional(),
  })).optional(),
  additions: z.array(z.object({
    id: IdSchema,
    set_type: z.enum(['working', 'dropset']),
    reps: z.number().int().min(1).max(30),
    rir: z.number().int().min(0).max(5),
    weight: z.number().nonnegative().nullable(),
  })).optional(),
  idempotency_key: IdSchema,
  client_timestamp: z.string().optional(),
});

module.exports = {
  IdSchema,
  PreferencesSchema,
  PlanSchema,
  PrescribeSchema,
  LogSetSchema,
  LogSetSchemaV2,
  ScoreSetSchema,
  PatchOpSchema,
  PatchActiveWorkoutSchema,
  AutofillExerciseSchema,
};

// Template & Routine schemas (minimal)
// Note: weight is nullable to support bodyweight exercises and unset values
// Analytics treats null weight as non-load-bearing (zero volume contribution)
const TemplateSetSchema = z.object({
  id: z.string().optional(),
  reps: z.number().int().min(0),
  rir: z.number().int().min(0).max(5),
  type: z.string().default('Working Set'),
  weight: z.number().nonnegative().nullable(),
  duration: z.number().int().optional(),
});

const TemplateExerciseSchema = z.object({
  id: z.string().optional(),
  exercise_id: IdSchema.optional(), // server uses exerciseId sometimes; keep minimal
  exerciseId: IdSchema.optional(),   // backward compat
  position: z.number().int().nonnegative().optional(),
  sets: z.array(TemplateSetSchema).min(0),
  rest_between_sets: z.number().int().optional(),
});

const TemplateSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  exercises: z.array(TemplateExerciseSchema).min(1),
});

const RoutineSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  // Support both snake_case and camelCase for backward compat
  template_ids: z.array(z.string().min(1)).optional(),
  templateIds: z.array(z.string().min(1)).optional(),
  frequency: z.number().int().min(1).max(7).optional(),
  days: z.array(z.any()).optional(),  // Legacy field
}).refine(
  (data) => {
    // At least one of template_ids or templateIds should have content if provided
    const tids = data.template_ids || data.templateIds || [];
    // Empty is allowed (creating empty routine), but if provided must be strings
    return true;
  },
  { message: 'template_ids must be an array of non-empty strings' }
);

module.exports.TemplateSchema = TemplateSchema;
module.exports.RoutineSchema = RoutineSchema;

// Exercises
const ExerciseUpsertSchema = z.object({
  id: z.string().optional(),
  name: z.string().min(1),
  family_slug: z.string().optional(),
  variant_key: z.string().optional(),
  category: z.string().optional(),
  description: z.string().optional(),
  metadata: z.object({
    level: z.string().optional(),
    plane_of_motion: z.string().optional(),
    unilateral: z.boolean().optional(),
  }).optional(),
  movement: z.object({
    split: z.string().optional(),
    type: z.string().optional(),
  }).optional(),
  equipment: z.array(z.string()).optional(),
  muscles: z.object({
    primary: z.array(z.string()).optional(),
    secondary: z.array(z.string()).optional(),
    category: z.array(z.string()).optional(),
    contribution: z.record(z.string(), z.number()).optional(),
  }).optional(),
  execution_notes: z.array(z.string()).optional(),
  common_mistakes: z.array(z.string()).optional(),
  programming_use_cases: z.array(z.string()).optional(),
  stimulus_tags: z.array(z.string()).optional(),
  suitability_notes: z.array(z.string()).optional(),
  coaching_cues: z.array(z.string()).optional(),
  status: z.enum(['draft','approved']).optional(),
  version: z.number().int().optional(),
  aliases: z.array(z.string()).optional(),
});

module.exports.ExerciseUpsertSchema = ExerciseUpsertSchema;
