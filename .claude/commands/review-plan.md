---
description: Run adversarial critique on the current implementation plan using specialized sub-agents, then produce a revised, higher-quality plan.
---

You are an orchestrator. The conversation above contains an implementation plan that was just proposed. Your job is to stress-test that plan and produce an improved version.

## Step 1 — Extract and prepare

1. Identify the plan from the conversation. It may be in a plan file, a message, or the most recent assistant turn. Capture the full plan text.
2. Identify which layers the plan touches (iOS, Firebase Functions, Agent system, Firestore, docs). List the specific files and collections mentioned.
3. Read the architecture docs relevant to those layers — at minimum `docs/SYSTEM_ARCHITECTURE.md` and `docs/FIRESTORE_SCHEMA.md`, plus the layer-specific docs from `docs/`. Also read any `ARCHITECTURE.md` in directories the plan intends to modify. You need this context to evaluate the critics' feedback.

## Step 2 — Spawn critics

Launch **two** sub-agents in parallel using the Task tool (model: "sonnet", subagent_type: "general-purpose"). Each critic must receive:
- The full plan text (copy it into the prompt — they cannot see this conversation)
- Instructions on which architecture docs to read for context
- Their specific critique mandate (below)
- Instruction to be specific: cite file paths, field names, function names. No vague concerns.
- Instruction to return structured output with severity ratings.

### Critic A — "Architecture & Cross-Stack Integrity"

Prompt this critic to:

1. Read the plan provided, then read `docs/SYSTEM_ARCHITECTURE.md`, `docs/FIRESTORE_SCHEMA.md`, and the layer-specific architecture docs relevant to the plan.
2. Evaluate the plan against these concerns:

**Cross-stack completeness.** For every data shape change, check the 7-layer checklist:
- Firestore schema doc
- Firebase Function write path
- Firebase Function read path
- iOS Model (Codable with `decodeIfPresent` + defaults)
- iOS UI
- Agent skills (if applicable)
- Documentation (all three tiers)

Flag any layer the plan misses.

**Schema alignment.** Check that field names, types, and nesting match across layers. Flag snake_case/camelCase mismatches, type mismatches (e.g., string in Firestore but number in iOS model), or fields present in one layer but absent in another.

**Modularity and separation of concerns.** Does the plan put logic in the right place? Business logic in ViewModels not Views? Data access in repositories not view models? Transactions around read-then-write? Auth checks at the right boundary?

**Naming and conventions.** Do new files, functions, and fields follow the project's naming conventions? (`*Screen` vs `*View`, snake_case fields, `ok()`/`fail()` response helpers, `logger` not `console.log`, etc.)

**Backward compatibility.** Will existing clients (older app versions, existing Firestore documents) break? Are new fields optional with defaults? Does the iOS decoder use `decodeIfPresent`?

Return structured output:
```
## Architecture Critique

### Critical (must address before implementing)
- [issue]: [explanation with file paths and field names]

### Important (should address)
- [issue]: [explanation]

### Minor (consider)
- [issue]: [explanation]

### Looks sound
- [aspects of the plan that are well-designed]
```

### Critic B — "Robustness & Failure Modes"

Prompt this critic to:

1. Read the plan provided, then read the source files the plan intends to modify (or the most relevant ones if there are many).
2. Evaluate the plan against these concerns:

**Race conditions and concurrency.** Are there read-then-write sequences that should be in a Firestore transaction? Could two concurrent requests corrupt state? Are there Task lifecycle issues in Swift (fire-and-forget, missing cancellation)?

**Error handling and failure modes.** What happens when each external call fails? Is every async path covered with error handling? Does the iOS ViewModel expose `errorMessage` for async operations? Are Firebase Function errors returned with proper `fail()` codes?

**Edge cases and data integrity.** What happens with empty arrays, null fields, missing documents, zero-length strings? What if the user has no data yet? What about documents created before this change (migration)?

**Performance.** Are there N+1 query patterns? Unnecessary Firestore reads? Large payloads being sent when only a subset is needed? Unbounded list queries missing limits?

**Security.** Is userId derived correctly (from `req.auth.uid` in bearer-lane, never from request body)? Are there paths where a user could access another user's data? Any input that reaches Firestore unvalidated?

**Rollback safety.** If this deployment fails halfway, what state is the system in? Can the old and new code coexist during a rolling deploy?

Return structured output:
```
## Robustness Critique

### Critical (must address before implementing)
- [issue]: [explanation with specific scenario]

### Important (should address)
- [issue]: [explanation]

### Minor (consider)
- [issue]: [explanation]

### Looks sound
- [aspects of the plan that handle failure well]
```

## Step 3 — Synthesize

Once both critics return:

1. Read both critiques carefully.
2. For each critical/important issue raised, determine if it's valid by cross-referencing with the architecture docs you read in Step 1. Dismiss any that are based on incorrect assumptions about the codebase.
3. Group related feedback (both critics may flag the same underlying issue from different angles).

## Step 4 — Produce the revised plan

Output the improved plan in this format:

```
## Revised Plan

### What changed from critique
[Bulleted list of substantive changes made to the plan, with brief reasoning. Only list real changes, not "confirmed X was already fine."]

### Plan
[The full revised plan — not a diff, but the complete updated plan ready to implement. Same structure as the original but with improvements incorporated.]

### Dismissed feedback
[Any critic feedback that was considered but rejected, with reasoning. This keeps the process transparent.]
```

## Rules

- Do NOT add scope. If a critic suggests "you should also add feature X," ignore it unless X is necessary to prevent a bug or maintain consistency.
- Do NOT weaken the plan. If the original plan had a good approach, don't change it just because a critic offered an alternative.
- DO fix gaps. Missing layers, missing error handling, race conditions, schema mismatches — these are real improvements.
- Be concrete. The revised plan should be implementable as-is, with specific file paths, field names, and code patterns.
