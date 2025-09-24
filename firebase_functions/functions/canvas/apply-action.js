const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');
const FirestoreHelper = require('../utils/firestore-helper');
const { validateApplyActionRequest } = require('./validators');
const { logSetCore } = require('../shared/active_workout/log_set_core');
const { swapExerciseCore } = require('../shared/active_workout/swap_core');
const { adjustLoadCore } = require('../shared/active_workout/adjust_load_core');
const { reorderSetsCore } = require('../shared/active_workout/reorder_sets_core');


const dbh = new FirestoreHelper();

async function applyAction(req, res) {
  try {
    const t0 = Date.now();
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const auth = req.user || req.auth;
    const uid = auth?.uid;
    if (!uid) return fail(res, 'UNAUTHORIZED', 'Missing user context', null, 401);

    const v = validateApplyActionRequest(req.body || {});
    if (!v.valid) {
      return fail(res, 'INVALID_ARGUMENT', 'Invalid request', v.errors, 400);
    }

    const { canvasId, expected_version, action } = v.data;
    const canvasPath = `users/${uid}/canvases/${canvasId}`;

      const result = await admin.firestore().runTransaction(async (tx) => {
      // Scoped idempotency under canvas
      const idemRef = admin.firestore().doc(`${canvasPath}/idempotency/${action.idempotency_key}`);
      const idemSnap = await tx.get(idemRef);
      if (idemSnap.exists) return { duplicate: true };

      const stateRef = admin.firestore().doc(`${canvasPath}`);
      const stateSnap = await tx.get(stateRef);
      const state = stateSnap.exists ? stateSnap.data().state || {} : { version: 0, phase: 'planning' };
      const mutState = { ...state };

      if (typeof expected_version === 'number' && state.version !== expected_version) {
        throw { http: 409, code: 'STALE_VERSION', message: `Expected ${expected_version}, got ${state.version}` };
      }

      // Minimal reducer Phase 1
      const changes = { cards: [], up_next_delta: [] };
      const { FieldValue } = require('firebase-admin/firestore');
      const now = FieldValue.serverTimestamp();

      // --- UNDO pre-reads (must happen before any writes) ---
      let createdInstructionId = null;
      let undoPlan = null;
      if (action.type === 'UNDO') {
        const evQuery = admin.firestore().collection(`${canvasPath}/events`).orderBy('created_at', 'desc').limit(20);
        const evSnap = await tx.get(evQuery);
        for (const ev of evSnap.docs) {
          const e = ev.data();
          const a = e?.payload?.action;
          if (a === 'ACCEPT_PROPOSAL' || a === 'REJECT_PROPOSAL') {
            const cid = e?.payload?.card_id;
            if (!cid) continue;
            const cRef = admin.firestore().doc(`${canvasPath}/cards/${cid}`);
            const cSnap = await tx.get(cRef);
            if (!cSnap.exists) continue;
            undoPlan = { kind: 'revert_card', ref: cRef };
            break;
          }
          if (a === 'ADD_NOTE') {
            const nid = e?.payload?.note_id;
            if (!nid) continue;
            const nRef = admin.firestore().doc(`${canvasPath}/cards/${nid}`);
            const nSnap = await tx.get(nRef);
            if (!nSnap.exists) continue;
            undoPlan = { kind: 'delete_note', ref: nRef };
            break;
          }
        }
        if (!undoPlan) throw { http: 409, code: 'UNDO_NOT_POSSIBLE', message: 'Nothing to undo' };
      }

      if (action.type === 'ADD_INSTRUCTION') {
        const cardRef = admin.firestore().collection(`${canvasPath}/cards`).doc();
        const text = String(action?.payload?.text || '');
        tx.set(cardRef, {
          type: 'instruction',
          status: 'active',
          lane: 'analysis',
          content: { text },
          by: 'user',
          created_at: now,
          updated_at: now,
        });
        changes.cards.push({ card_id: cardRef.id, status: 'active' });
        createdInstructionId = cardRef.id;
        const upRef = admin.firestore().collection(`${canvasPath}/up_next`).doc();
        tx.set(upRef, { card_id: cardRef.id, priority: 100, inserted_at: now });
        changes.up_next_delta.push({ op: 'add', card_id: cardRef.id });

        // Emit explicit instruction_added event for agent pickup
        const evtRefInst = admin.firestore().collection(`${canvasPath}/events`).doc();
        const preview = text.length > 256 ? (text.slice(0, 253) + '...') : text;
        tx.set(evtRefInst, { type: 'instruction_added', payload: { instruction_id: cardRef.id, text: preview }, created_at: now });
      }

      if (action.type === 'ACCEPT_PROPOSAL' || action.type === 'REJECT_PROPOSAL') {
        if (!action.card_id) throw { http: 400, code: 'INVALID_ARGUMENT', message: 'card_id is required' };
        const cRef = admin.firestore().doc(`${canvasPath}/cards/${action.card_id}`);
        const cSnap = await tx.get(cRef);
        if (!cSnap.exists) throw { http: 404, code: 'NOT_FOUND', message: 'Card not found' };
        const newStatus = action.type === 'ACCEPT_PROPOSAL' ? 'accepted' : 'rejected';

        // Precompute reads for replacements/collisions BEFORE any writes
        const card = cSnap.data();
        // Science/Safety guard for accepting session_plan targets
        if (newStatus === 'accepted' && card?.type === 'session_plan') {
          try {
            const blocks = Array.isArray(card?.content?.blocks) ? card.content.blocks : [];
            for (const b of blocks) {
              const sets = Array.isArray(b?.sets) ? b.sets : [];
              for (const s of sets) {
                const t = s?.target || {};
                const reps = t?.reps;
                const rir = t?.rir;
                if (typeof reps !== 'number' || reps < 1 || reps > 30) throw new Error('reps out of bounds');
                if (typeof rir !== 'number' || rir < 0 || rir > 5) throw new Error('rir out of bounds');
              }
            }
          } catch (e) {
            throw { http: 400, code: 'SCIENCE_VIOLATION', message: 'Invalid session_plan targets' };
          }
        }
        let siblingsSnap = null;
        let upNextSiblingDocs = [];
        if (newStatus === 'accepted' && card?.lane === 'analysis' && card?.refs?.topic_key) {
          const topicKey = card.refs.topic_key;
          const siblingsQuery = admin.firestore().collection(`${canvasPath}/cards`)
            .where('lane', '==', 'analysis')
            .where('refs.topic_key', '==', topicKey);
          siblingsSnap = await tx.get(siblingsQuery);
          // fetch up_next for each sibling
          for (const s of siblingsSnap.docs) {
            if (s.id === action.card_id) continue;
            const upQuery = admin.firestore().collection(`${canvasPath}/up_next`).where('card_id', '==', s.id);
            const upSnap = await tx.get(upQuery);
            upSnap.forEach(u => upNextSiblingDocs.push(u.ref));
          }
        }

        let stSnap = null;
        let upNextSTDocs = [];
        if (newStatus === 'accepted' && card?.lane === 'workout' && card?.type === 'set_target' && card?.refs?.exercise_id != null && card?.refs?.set_index != null) {
          const stQuery = admin.firestore().collection(`${canvasPath}/cards`).where('type', '==', 'set_target');
          stSnap = await tx.get(stQuery);
          for (const s of stSnap.docs) {
            if (s.id === action.card_id) continue;
            const upQuery2 = admin.firestore().collection(`${canvasPath}/up_next`).where('card_id', '==', s.id);
            const upSnap2 = await tx.get(upQuery2);
            upSnap2.forEach(u => upNextSTDocs.push(u.ref));
          }
        }

        // Now perform writes
        tx.update(cRef, { status: newStatus, updated_at: now });
        changes.cards.push({ card_id: action.card_id, status: newStatus });

        if (newStatus === 'accepted' && siblingsSnap) {
          for (const s of siblingsSnap.docs) {
            if (s.id === action.card_id) continue;
            tx.update(s.ref, { status: 'expired', updated_at: now });
            changes.cards.push({ card_id: s.id, status: 'expired' });
          }
          upNextSiblingDocs.forEach(ref => tx.delete(ref));
          upNextSiblingDocs.forEach(ref => changes.up_next_delta.push({ op: 'remove', card_id: ref.id }));
        }

        if (newStatus === 'accepted' && stSnap) {
          const exerciseId = card.refs.exercise_id;
          const setIndex = card.refs.set_index;
          for (const s of stSnap.docs) {
            if (s.id === action.card_id) continue;
            const sd = s.data();
            if (sd?.refs?.exercise_id === exerciseId && sd?.refs?.set_index === setIndex && (sd.status === 'active' || sd.status === 'accepted' || sd.status === 'proposed')) {
              tx.update(s.ref, { status: 'expired', updated_at: now });
              changes.cards.push({ card_id: s.id, status: 'expired' });
            }
          }
          upNextSTDocs.forEach(ref => tx.delete(ref));
          upNextSTDocs.forEach(ref => changes.up_next_delta.push({ op: 'remove', card_id: ref.id }));
        }
        // Auto-start session on accepting a session_plan
        if (newStatus === 'accepted' && card?.type === 'session_plan' && mutState.phase !== 'active') {
          mutState.phase = 'active';
          const evtRefStart = admin.firestore().collection(`${canvasPath}/events`).doc();
          tx.set(evtRefStart, { type: 'session_started', payload: { card_id: action.card_id }, created_at: now });
        }
      }

      if ((action.type === 'ACCEPT_ALL' || action.type === 'REJECT_ALL') && action?.payload?.group_id) {
        const groupId = action.payload.group_id;
        const targetStatus = action.type === 'ACCEPT_ALL' ? 'accepted' : 'rejected';
        const cardsQuery = admin.firestore().collection(`${canvasPath}/cards`).where('meta.groupId', '==', groupId);
        const cardsSnap = await tx.get(cardsQuery);
        const upNextRefs = [];
        for (const doc of cardsSnap.docs) {
          const d = doc.data();
          const id = doc.id;
          // Skip if already in desired terminal state
          if (d.status === targetStatus) continue;
          tx.update(doc.ref, { status: targetStatus, updated_at: now });
          changes.cards.push({ card_id: id, status: targetStatus });
          // remove from up_next when rejected
          if (targetStatus === 'rejected') {
            const upSnap = await tx.get(admin.firestore().collection(`${canvasPath}/up_next`).where('card_id', '==', id));
            upSnap.forEach(u => upNextRefs.push(u.ref));
          }
        }
        upNextRefs.forEach(ref => { tx.delete(ref); changes.up_next_delta.push({ op: 'remove', card_id: ref.id }); });
        const evtRefGroup = admin.firestore().collection(`${canvasPath}/events`).doc();
        tx.set(evtRefGroup, { type: 'group_action', payload: { action: action.type, group_id: groupId }, created_at: now });
      }

      if (action.type === 'ADD_NOTE') {
        const cardRef = admin.firestore().collection(`${canvasPath}/cards`).doc();
        tx.set(cardRef, {
          type: 'note',
          status: 'active',
          lane: 'workout',
          content: { text: action?.payload?.text || '' },
          by: 'user',
          created_at: now,
          updated_at: now,
        });
        changes.cards.push({ card_id: cardRef.id, status: 'active' });

        // Event carries note_id to support deterministic UNDO
        const evtRefNote = admin.firestore().collection(`${canvasPath}/events`).doc();
        tx.set(evtRefNote, { type: 'apply_action', payload: { action: 'ADD_NOTE', note_id: cardRef.id }, created_at: now });
      }

      if (action.type === 'LOG_SET' && action?.payload) {
        if (state.phase !== 'active') throw { http: 409, code: 'PHASE_GUARD', message: 'Workout not active' };
        const { actual, exercise_id, set_index } = action.payload;
        if (typeof actual?.reps !== 'number' || actual.reps < 0) throw { http: 400, code: 'SCIENCE_VIOLATION', message: 'Invalid reps' };
        if (typeof actual?.rir !== 'number' || actual.rir < 0 || actual.rir > 5) throw { http: 400, code: 'SCIENCE_VIOLATION', message: 'Invalid RIR' };
        // Pre-read set_target and up_next for deletion
        const stQuery2 = admin.firestore().collection(`${canvasPath}/cards`).where('type', '==', 'set_target');
        const stSnap = await tx.get(stQuery2);
        const upNextToDelete = [];
        for (const s of stSnap.docs) {
          const sd = s.data();
          if (sd?.refs?.exercise_id === exercise_id && sd?.refs?.set_index === set_index && (sd.status === 'active' || sd.status === 'accepted')) {
            const upQuery2 = admin.firestore().collection(`${canvasPath}/up_next`).where('card_id', '==', s.id);
            const upSnap2 = await tx.get(upQuery2);
            upSnap2.forEach(u => upNextToDelete.push(u.ref));
          }
        }
        // Writes
        await logSetCore(tx, { uid, ...action.payload });
        for (const s of stSnap.docs) {
          const sd = s.data();
          if (sd?.refs?.exercise_id === exercise_id && sd?.refs?.set_index === set_index && (sd.status === 'active' || sd.status === 'accepted')) {
            tx.update(s.ref, { status: 'completed', updated_at: now });
            changes.cards.push({ card_id: s.id, status: 'completed' });
          }
        }
        upNextToDelete.forEach(ref => tx.delete(ref));
        upNextToDelete.forEach(ref => changes.up_next_delta.push({ op: 'remove', card_id: ref.id }));

        const resultRef = admin.firestore().collection(`${canvasPath}/cards`).doc();
        tx.set(resultRef, {
          type: 'set_result',
          status: 'completed',
          lane: 'workout',
          content: { actual },
          refs: { exercise_id, set_index },
          by: 'user',
          created_at: now,
          updated_at: now,
        });
        changes.cards.push({ card_id: resultRef.id, status: 'completed' });
      }

      if (action.type === 'SWAP' && action?.payload) {
        if (mutState.phase !== 'active') throw { http: 409, code: 'PHASE_GUARD', message: 'Workout not active' };
        const { exercise_id, replacement_exercise_id, workout_id } = action.payload;
        if (!exercise_id || !replacement_exercise_id || !workout_id) throw { http: 400, code: 'INVALID_ARGUMENT', message: 'Missing swap parameters' };
        await swapExerciseCore(tx, { uid, ...action.payload });
      }

      if (action.type === 'ADJUST_LOAD' && action?.payload) {
        if (mutState.phase !== 'active') throw { http: 409, code: 'PHASE_GUARD', message: 'Workout not active' };
        const { delta_kg, workout_id } = action.payload;
        if (typeof delta_kg !== 'number') throw { http: 400, code: 'INVALID_ARGUMENT', message: 'delta_kg must be number' };
        if (!workout_id) throw { http: 400, code: 'INVALID_ARGUMENT', message: 'Missing workout_id' };
        await adjustLoadCore(tx, { uid, ...action.payload });
      }

      if (action.type === 'REORDER_SETS' && action?.payload) {
        if (mutState.phase !== 'active') throw { http: 409, code: 'PHASE_GUARD', message: 'Workout not active' };
        const { workout_id, exercise_id, order } = action.payload;
        if (!Array.isArray(order) || order.length === 0) throw { http: 400, code: 'INVALID_ARGUMENT', message: 'order must be non-empty array' };
        if (!workout_id || !exercise_id) throw { http: 400, code: 'INVALID_ARGUMENT', message: 'Missing workout_id or exercise_id' };
        await reorderSetsCore(tx, { uid, ...action.payload });
      }

      if (action.type === 'EDIT_SET' && action?.payload) {
        // MVP stub: schema-level validation exists; reducer handling can be added later.
        // For now, fail deterministically to avoid silent acceptance.
        throw { http: 400, code: 'UNIMPLEMENTED', message: 'EDIT_SET not yet implemented' };
      }

      if (action.type === 'PAUSE') {
        if (mutState.phase !== 'active') throw { http: 409, code: 'PHASE_GUARD', message: 'Can pause only from active' };
        mutState.phase = 'planning';
      }

      if (action.type === 'RESUME') {
        if (mutState.phase !== 'planning') throw { http: 409, code: 'PHASE_GUARD', message: 'Can resume only from planning' };
        mutState.phase = 'active';
      }

      if (action.type === 'COMPLETE') {
        if (mutState.phase !== 'active') throw { http: 409, code: 'PHASE_GUARD', message: 'Can complete only from active' };
        mutState.phase = 'analysis';
      }

      // increment version
      const nextVersion = (mutState.version || 0) + 1;
      const newState = { ...mutState, version: nextVersion };
      tx.set(stateRef, { state: newState }, { merge: true });

      // record idempotency after successful writes
      tx.set(idemRef, { key: action.idempotency_key, created_at: now });

      if (action.type === 'UNDO') {
        if (undoPlan.kind === 'revert_card') {
          tx.update(undoPlan.ref, { status: 'proposed', updated_at: now });
          changes.cards.push({ card_id: undoPlan.ref.id, status: 'proposed' });
        } else if (undoPlan.kind === 'delete_note') {
          tx.delete(undoPlan.ref);
          changes.cards.push({ card_id: undoPlan.ref.id, status: 'deleted' });
        }
      }

      // append compact event at end (after all reads)
      const evtRef = admin.firestore().collection(`${canvasPath}/events`).doc();
      const applyPayload = { action: action.type, card_id: action.card_id || null };
      if (action.type === 'ADD_INSTRUCTION' && createdInstructionId) {
        applyPayload.instruction_id = createdInstructionId;
        applyPayload.card_id = createdInstructionId;
      }
      if (action.type === 'ADD_NOTE' && changes?.cards?.length) {
        const last = changes.cards[changes.cards.length - 1];
        if (last && last.status === 'active') {
          applyPayload.note_id = last.card_id;
        }
      }
      const correlation_id = `${canvasId}:${(mutState.version || 0) + 1}`;
      const changedIds = changes.cards?.map(c => c.card_id) || [];
      tx.set(evtRef, { type: 'apply_action', payload: { ...applyPayload, changed_cards: changedIds }, created_at: now, correlation_id });

      // NOTE: Do not perform reads after writes inside the transaction to satisfy Firestore constraints.
      // up_next cap enforcement will be handled best-effort outside of the transaction below.

      return { state: newState, ...changes, version: nextVersion };
    });

    if (result?.duplicate) {
      console.log('[applyAction] duplicate key', { uid, canvasId, type: action.type, ms: Date.now() - t0 });
      return ok(res, { duplicate: true });
    }

    const payload = {
      state: result.state,
      changed_cards: result.cards,
      up_next_delta: result.up_next_delta,
      version: result.version,
    };

    // Best-effort up_next cap enforcement outside the transaction (reads after writes are not allowed inside txn)
    try {
      const upCol = admin.firestore().collection(`users/${uid}/canvases/${canvasId}/up_next`);
      const upSnap = await upCol.orderBy('priority', 'desc').orderBy('inserted_at', 'asc').get();
      const MAX = 20;
      if (upSnap.size > MAX) {
        const overflow = upSnap.docs.slice(MAX);
        const trimBatch = admin.firestore().batch();
        overflow.forEach(doc => trimBatch.delete(doc.ref));
        await trimBatch.commit();
      }
    } catch (e) {
      console.warn('[applyAction] up_next trim skipped', { canvasId, error: e?.message });
    }
    console.log('[applyAction] ok', { uid, canvasId, type: action.type, version: result.version, cards: result.cards?.length || 0, ms: Date.now() - t0 });
    return ok(res, payload);
  } catch (err) {
    const http = err?.http || 500;
    const code = err?.code || 'INTERNAL';
    const message = err?.message || 'Failed to apply action';
    const details = err?.details;
    console.error('applyAction error:', { code, message, http, details, stack: err?.stack });
    return fail(res, code, message, details, http);
  }
}

module.exports = { applyAction };


