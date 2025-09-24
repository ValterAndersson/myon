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

const LogSetSchema = z.object({
  workout_id: IdSchema,
  exercise_id: IdSchema,
  set_index: z.number().int().min(0),
  actual: z.object({ reps: z.number().int().min(0), rir: z.number().int().min(0).max(5), weight: z.number().optional(), tempo: z.string().optional(), notes: z.string().optional() })
});

const ScoreSetSchema = z.object({ actual: z.object({ reps: z.number(), rir: z.number(), weight: z.number().optional() }) });

module.exports = {
  IdSchema,
  PreferencesSchema,
  PlanSchema,
  PrescribeSchema,
  LogSetSchema,
  ScoreSetSchema,
};

// Template & Routine schemas (minimal)
const TemplateSetSchema = z.object({
  id: z.string().optional(),
  reps: z.number().int().min(0),
  rir: z.number().int().min(0).max(5),
  type: z.string().default('Working Set'),
  weight: z.number().nonnegative(),
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
  days: z.array(z.any()).optional(),
});

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


