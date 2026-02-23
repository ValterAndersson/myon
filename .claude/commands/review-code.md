---
description: Adversarial code review of recently completed work using specialized sub-agents. Run after implementation is done, before committing.
---

You are an orchestrator. The agent just finished implementing changes. Your job is to review the actual code that was written, catch real issues, and either fix them or flag them.

## Step 1 — Gather the changes

1. Run `git diff --stat` and `git diff` to see all uncommitted changes (staged + unstaged).
2. If the diff is empty, try `git diff HEAD~1` (the last commit may contain the work).
3. List every changed file. Read each changed file in full — diffs alone miss context.
4. Determine which layers were touched (iOS, Firebase Functions, Agent system, Firestore, docs).
5. Read the architecture docs relevant to those layers — at minimum `docs/SYSTEM_ARCHITECTURE.md` and `docs/FIRESTORE_SCHEMA.md`, plus layer-specific docs. Also read `ARCHITECTURE.md` in each modified directory.

## Step 2 — Spawn reviewers

Launch **two** sub-agents in parallel using the Task tool (model: "sonnet", subagent_type: "general-purpose"). Each reviewer must receive:
- The full git diff (copy it into the prompt — they cannot see this conversation)
- The list of changed files and which layers are affected
- Instructions on which architecture docs and source files to read for context
- Their specific review mandate (below)
- Instruction to cite exact file paths and line numbers for every finding

### Reviewer A — "Cross-Stack & Convention Compliance"

Prompt this reviewer to:

1. Read the diff provided, then read the full contents of every changed file. Read `docs/SYSTEM_ARCHITECTURE.md`, `docs/FIRESTORE_SCHEMA.md`, and the layer-specific architecture docs for affected layers.
2. Check:

**Cross-stack completeness.** If a data shape was added or changed, verify all 7 layers were updated:
- Firestore schema doc — field documented?
- Firebase write path — field written?
- Firebase read path — field returned?
- iOS Model — property added with `decodeIfPresent` + default?
- iOS UI — field used where needed?
- Agent skills — updated if agent reads/writes this data?
- Docs — all three tiers updated?

**Schema alignment across layers.** Compare field names, types, and structure between what the Firebase Function writes, what the iOS model decodes, and what the schema doc says. Flag any mismatch.

**Convention violations.** Check against project rules:
- Firebase: `ok()`/`fail()` not raw `res.status().json()`. `logger` not `console.log`. `req.auth.uid` in bearer-lane not `req.body.userId`. `serverTimestamp()` for Firestore writes. `runTransaction` for read-then-write. Input validation before logic.
- Python: `logging.getLogger(__name__)` not print. No bare `except:`. Type hints on public functions. `from __future__ import annotations`. `ContextVar` for request state.
- Swift: Logic in ViewModels not Views. `Task` stored/cancelled or `.task {}` modifier. `errorMessage` on async ViewModels. `@ObservedObject` for `.shared`. Design tokens not hardcoded values. Listeners cleaned up.

**Naming.** Files, functions, fields follow conventions (`*Screen`/`*View`/`*Service`/`*Manager`/`*Repository`, snake_case Firestore fields, etc.).

Return:
```
## Cross-Stack & Convention Review

### Must fix
- [file:line] [issue with explanation]

### Should fix
- [file:line] [issue with explanation]

### Clean
- [aspects that follow conventions correctly]
```

### Reviewer B — "Bugs, Races & Edge Cases"

Prompt this reviewer to:

1. Read the diff provided, then read the full contents of every changed file plus any files they call into or are called by (check imports and references).
2. Check:

**Bugs.** Logic errors, off-by-one, wrong variable, incorrect comparisons, typos in field names that would cause silent data loss, missing return statements, uncalled functions.

**Race conditions.** Firestore read-then-write outside transactions. Concurrent requests corrupting shared state. Swift Tasks that capture stale state. Listeners that fire after view disappears.

**Error handling.** Unhandled promise rejections. Missing try/catch on async calls. Firebase Functions that don't return `fail()` on error paths. Swift async calls without error surfacing.

**Edge cases.** Empty arrays, null/undefined fields, missing Firestore documents, first-time users with no data, zero values, very long strings, documents created before this change.

**Performance.** N+1 queries (reading documents in a loop). Fetching full documents when only one field is needed. Missing query limits. Unnecessary re-renders in SwiftUI.

Return:
```
## Bugs & Robustness Review

### Must fix
- [file:line] [bug/issue with specific scenario that triggers it]

### Should fix
- [file:line] [issue with explanation]

### Clean
- [aspects that handle edge cases well]
```

## Step 3 — Act on findings

Once both reviewers return:

1. Cross-reference their findings against the architecture docs you read. Dismiss anything based on incorrect assumptions.
2. Separate findings into:
   - **Fix now** — real bugs, missing cross-stack layers, broken conventions that will cause issues
   - **Recommend** — improvements that are valid but not blocking
   - **Dismissed** — reviewer feedback that was wrong or not applicable

3. For "fix now" items: make the fixes directly in the code. Show what you changed.
4. For "recommend" items: list them for the user to decide.
5. For "dismissed" items: briefly note why.

## Output

```
## Code Review Complete

### Fixed
- [file:line] [what was wrong → what was fixed]

### Recommendations (your call)
- [file:line] [suggestion and reasoning]

### Dismissed
- [feedback that was considered but not applicable, with brief reason]

### Summary
[1-2 sentences: overall assessment of the implementation quality]
```

## Rules

- Only fix real issues. Do not refactor, add comments, improve naming, or "clean up" code that works.
- Do not add scope. If a reviewer says "you should also handle X," only act on it if X is a genuine bug or missing error path, not a new feature.
- Be concrete. Every finding must have a file path, line number, and specific explanation.
