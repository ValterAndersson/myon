const Ajv = require('ajv/dist/2020');

const ajv = new Ajv({ allErrors: true, removeAdditional: 'failing', useDefaults: true, coerceTypes: true });
const sessionPlanSchema = require('./schemas/card_types/session_plan.schema.json');
const coachProposalSchema = require('./schemas/card_types/coach_proposal.schema.json');
const visualizationSchema = require('./schemas/card_types/visualization.schema.json');
const setTargetSchema = require('./schemas/card_types/set_target.schema.json');
const agentStreamSchema = require('./schemas/card_types/agent_stream.schema.json');
const clarifyQuestionsSchema = require('./schemas/card_types/clarify_questions.schema.json');
const listSchema = require('./schemas/card_types/list.schema.json');
const inlineInfoSchema = require('./schemas/card_types/inline_info.schema.json');
const proposalGroupSchema = require('./schemas/card_types/proposal_group.schema.json');
const routineOverviewSchema = require('./schemas/card_types/routine_overview.schema.json');
const routineSummarySchema = require('./schemas/card_types/routine_summary.schema.json');
const analysisSummarySchema = require('./schemas/card_types/analysis_summary.schema.json');
ajv.addSchema(sessionPlanSchema);
ajv.addSchema(coachProposalSchema);
ajv.addSchema(visualizationSchema);
ajv.addSchema(setTargetSchema);
ajv.addSchema(agentStreamSchema);
ajv.addSchema(clarifyQuestionsSchema);
ajv.addSchema(listSchema);
ajv.addSchema(inlineInfoSchema);
ajv.addSchema(proposalGroupSchema);
ajv.addSchema(routineOverviewSchema);
ajv.addSchema(routineSummarySchema);
ajv.addSchema(analysisSummarySchema);

// --- Action schema (Phase 1 supported types) ---
const actionSchema = {
  $id: 'https://myon.dev/schemas/canvas/action.json',
  type: 'object',
  additionalProperties: false,
  required: ['type', 'idempotency_key'],
  properties: {
    type: {
      type: 'string',
      enum: [
        'ADD_INSTRUCTION', 'ACCEPT_PROPOSAL', 'REJECT_PROPOSAL', 'ACCEPT_ALL', 'REJECT_ALL',
        'ADD_NOTE', 'LOG_SET', 'EDIT_SET', 'SWAP', 'ADJUST_LOAD', 'REORDER_SETS',
        'PAUSE', 'RESUME', 'COMPLETE', 'UNDO',
        // Routine draft actions
        'SAVE_ROUTINE', 'PIN_DRAFT', 'DISMISS_DRAFT'
      ],
    },
    card_id: { type: 'string' },
    payload: { type: ['object', 'null'] },
    by: { type: 'string', enum: ['user', 'agent'], default: 'user' },
    idempotency_key: { type: 'string', minLength: 1 },
  },
  allOf: [
    {
      if: { properties: { type: { const: 'ACCEPT_PROPOSAL' } } },
      then: { required: ['card_id'] },
    },
    {
      if: { properties: { type: { const: 'EDIT_SET' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['workout_id', 'exercise_id', 'set_index', 'target'],
            properties: {
              workout_id: { type: 'string', minLength: 1 },
              exercise_id: { type: 'string', minLength: 1 },
              set_index: { type: 'integer', minimum: 0 },
              target: {
                type: 'object',
                additionalProperties: true,
                required: ['reps', 'rir'],
                properties: {
                  reps: { type: 'integer', minimum: 1, maximum: 30 },
                  rir: { type: 'integer', minimum: 0, maximum: 5 },
                  weight: { type: 'number' },
                  tempo: { type: 'string' },
                  notes: { type: 'string' }
                }
              }
            }
          }
        }
      }
    },
    {
      if: { properties: { type: { const: 'ACCEPT_ALL' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['group_id'],
            properties: {
              group_id: { type: 'string', minLength: 1 }
            }
          }
        }
      }
    },
    {
      if: { properties: { type: { const: 'REJECT_ALL' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['group_id'],
            properties: {
              group_id: { type: 'string', minLength: 1 }
            }
          }
        }
      }
    },
    {
      if: { properties: { type: { const: 'REJECT_PROPOSAL' } } },
      then: { required: ['card_id'] },
    },
    {
      if: { properties: { type: { const: 'SWAP' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['workout_id', 'exercise_id', 'replacement_exercise_id'],
            properties: {
              workout_id: { type: 'string', minLength: 1 },
              exercise_id: { type: 'string', minLength: 1 },
              replacement_exercise_id: { type: 'string', minLength: 1 }
            }
          }
        }
      }
    },
    {
      if: { properties: { type: { const: 'ADJUST_LOAD' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['workout_id', 'exercise_id', 'set_index', 'delta_kg'],
            properties: {
              workout_id: { type: 'string', minLength: 1 },
              exercise_id: { type: 'string', minLength: 1 },
              set_index: { type: 'integer', minimum: 0 },
              delta_kg: { type: 'number' }
            }
          }
        }
      }
    },
    {
      if: { properties: { type: { const: 'REORDER_SETS' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['workout_id', 'exercise_id', 'order'],
            properties: {
              workout_id: { type: 'string', minLength: 1 },
              exercise_id: { type: 'string', minLength: 1 },
              order: { type: 'array', minItems: 1, items: { type: 'integer', minimum: 0 } }
            }
          }
        }
      }
    },
    {
      if: { properties: { type: { const: 'LOG_SET' } } },
      then: {
        required: ['payload'],
        properties: {
          payload: {
            type: 'object',
            additionalProperties: false,
            required: ['workout_id', 'exercise_id', 'set_index', 'actual'],
            properties: {
              workout_id: { type: 'string', minLength: 1 },
              exercise_id: { type: 'string', minLength: 1 },
              set_index: { type: 'integer', minimum: 0 },
              actual: {
                type: 'object',
                additionalProperties: true,
                required: ['reps', 'rir'],
                properties: {
                  reps: { type: 'integer', minimum: 0 },
                  rir: { type: 'integer', minimum: 0, maximum: 5 },
                  weight: { type: 'number' },
                  tempo: { type: 'string' },
                  notes: { type: 'string' },
                },
              },
            },
          },
        },
      },
    },
    // Routine draft actions - require card_id pointing to routine_summary
    {
      if: { properties: { type: { const: 'SAVE_ROUTINE' } } },
      then: { required: ['card_id'] },
    },
    {
      if: { properties: { type: { const: 'PIN_DRAFT' } } },
      then: { required: ['card_id'] },
    },
    {
      if: { properties: { type: { const: 'DISMISS_DRAFT' } } },
      then: { required: ['card_id'] },
    },
  ],
};

// --- applyAction request schema ---
const applyActionRequestSchema = {
  $id: 'https://myon.dev/schemas/canvas/apply_action_request.json',
  type: 'object',
  additionalProperties: false,
  required: ['canvasId', 'action'],
  properties: {
    canvasId: { type: 'string', minLength: 1 },
    expected_version: { type: 'integer', minimum: 0 },
    action: actionSchema,
  },
};

// --- Card input schema for proposeCards ---
const cardInputSchema = {
  $id: 'https://myon.dev/schemas/canvas/card_input.json',
  type: 'object',
  additionalProperties: false,
  required: ['type', 'content'],
  properties: {
    type: { type: 'string', minLength: 1 },
    lane: { type: 'string', enum: ['workout', 'analysis', 'system'] },
    content: { type: 'object' },
    priority: { type: 'integer' },
    layout: { type: 'object' },
    actions: { type: 'array', items: { type: 'object' } },
    menuItems: { type: 'array', items: { type: 'object' } },
    meta: { type: 'object' },
    ttl: {
      type: 'object',
      additionalProperties: false,
      required: ['minutes'],
      properties: { minutes: { type: 'integer', minimum: 1 } },
    },
    refs: { type: 'object' },
  },
  allOf: [
    {
      if: { properties: { type: { const: 'session_plan' } } },
      then: { properties: { content: { $ref: sessionPlanSchema.$id } } }
    },
    {
      if: { properties: { type: { const: 'coach_proposal' } } },
      then: { properties: { content: { $ref: coachProposalSchema.$id } } }
    },
    {
      if: { properties: { type: { const: 'visualization' } } },
      then: { properties: { content: { $ref: visualizationSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'set_target' } } },
      then: { properties: { content: { $ref: setTargetSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'agent_stream' } } },
      then: { properties: { content: { $ref: agentStreamSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'clarify-questions' } } },
      then: { properties: { content: { $ref: clarifyQuestionsSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'list' } } },
      then: { properties: { content: { $ref: listSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'inline-info' } } },
      then: { properties: { content: { $ref: inlineInfoSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'proposal-group' } } },
      then: { properties: { content: { $ref: proposalGroupSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'routine-overview' } } },
      then: { properties: { content: { $ref: routineOverviewSchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'routine_summary' } } },
      then: { properties: { content: { $ref: routineSummarySchema.$id } } }
    }
    ,
    {
      if: { properties: { type: { const: 'analysis_summary' } } },
      then: { properties: { content: { $ref: analysisSummarySchema.$id } } }
    }
  ]
};

// --- proposeCards request schema ---
const proposeCardsRequestSchema = {
  $id: 'https://myon.dev/schemas/canvas/propose_cards_request.json',
  type: 'object',
  additionalProperties: false,
  required: ['canvasId', 'cards'],
  properties: {
    canvasId: { type: 'string', minLength: 1 },
    cards: { type: 'array', minItems: 1, items: cardInputSchema },
  },
};

// Compile validators once per process
const validateApplyActionRequest = ajv.compile(applyActionRequestSchema);
const validateProposeCardsRequest = ajv.compile(proposeCardsRequestSchema);

function validateOrErrors(validator, data) {
  const payload = typeof data === 'object' && data !== null ? JSON.parse(JSON.stringify(data)) : {};
  const valid = validator(payload);
  return { valid, data: payload, errors: valid ? null : validator.errors };
}

module.exports = {
  validateApplyActionRequest: (data) => validateOrErrors(validateApplyActionRequest, data),
  validateProposeCardsRequest: (data) => validateOrErrors(validateProposeCardsRequest, data),
};
