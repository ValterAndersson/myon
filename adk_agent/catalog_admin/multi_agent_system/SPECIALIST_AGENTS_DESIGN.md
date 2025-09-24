# Specialist Agents Architecture

## Exercise Data Model

Based on the Firebase schema, an exercise contains:

### Core Fields
- `id`: Unique identifier
- `name`: Exercise name
- `family_slug`: Normalized family name
- `variant_key`: Variant identifier (e.g., "equipment:barbell")
- `category`: compound | isolation | cardio | flexibility | balance
- `status`: draft | approved
- `version`: Version number

### Movement & Biomechanics
- `movement.type`: push | pull | squat | hinge | lunge | carry | rotation | anti-rotation
- `movement.split`: upper | lower | full
- `metadata.plane_of_motion`: sagittal | frontal | transverse
- `metadata.unilateral`: boolean
- `metadata.level`: beginner | intermediate | advanced

### Anatomy
- `muscles.primary`: Array of primary muscles (e.g., ["medial deltoid"])
- `muscles.secondary`: Array of secondary muscles (e.g., ["anterior deltoid", "trapezius"])
- `muscles.category`: Array of muscle groups (e.g., ["shoulders"])
- `muscles.contribution`: Map of muscle to percentage (e.g., {"medial deltoid": 0.75, "anterior deltoid": 0.15, "trapezius": 0.1})

### Equipment & Setup
- `equipment`: Array of required equipment

### Content & Instructions
- `description`: Exercise description
- `execution_notes`: Array of step-by-step instructions
- `common_mistakes`: Array of common errors to avoid
- `programming_use_cases`: Array of when/how to use
- `suitability_notes`: Array of who it's suitable for
- `stimulus_tags`: Array of training stimulus tags

### Search & Discovery
- `aliases`: Array of alternative names

## Specialist Agents Design

### 1. **Creator Agent** 🏗️
**Purpose**: Creates new exercises from Scout-identified gaps
**Responsibilities**:
- Takes gap patterns from Scout
- Generates complete exercise definitions
- Ensures proper family/variant structure
- Creates initial draft with all required fields

**Triggers**: Scout identifies missing exercises
**Output**: New draft exercises

---

### 2. **Biomechanics Specialist** ⚙️
**Purpose**: Ensures movement patterns and equipment are correctly categorized
**Responsibilities**:
- Validates and corrects `movement.type` and `movement.split`
- Sets proper `metadata.plane_of_motion`
- Determines `metadata.unilateral` status
- Validates equipment requirements
- Ensures category (compound/isolation) matches movement pattern
- Sets appropriate difficulty level

**Fields Owned**:
- `movement.*`
- `metadata.plane_of_motion`
- `metadata.unilateral`
- `metadata.level`
- `category` (validation)
- `equipment` (validation)

---

### 3. **Anatomy Specialist** 💪
**Purpose**: Accurately maps muscle involvement and contribution
**Responsibilities**:
- Identifies primary and secondary muscles
- Calculates contribution profiles (percentages)
- Validates muscle groups against movement type
- Ensures anatomical accuracy
- Adds muscle category tags

**Fields Owned**:
- `muscles.primary`
- `muscles.secondary`
- `muscles.category`
- `muscles.contribution`

**Special Logic**:
- Compound movements: 2+ primary muscles
- Isolation movements: 1-2 primary muscles
- Contribution percentages must sum to 100%

---

### 4. **Content Specialist** 📝
**Purpose**: Creates high-quality instructional content
**Responsibilities**:
- Writes clear, concise descriptions
- Creates step-by-step execution notes
- Documents common mistakes
- Ensures content quality and consistency
- Maintains professional tone

**Fields Owned**:
- `description`
- `execution_notes`
- `common_mistakes`

**Quality Standards**:
- Description: 50+ characters
- Execution notes: 3+ steps
- Common mistakes: 2+ items
- Clear, actionable language

---

### 5. **Programming Specialist** 🎯
**Purpose**: Provides training context and programming guidance
**Responsibilities**:
- Defines programming use cases
- Creates suitability notes for different populations
- Assigns stimulus tags (hypertrophy, strength, power, endurance)
- Recommends rep ranges and intensity
- Identifies exercise progressions/regressions

**Fields Owned**:
- `programming_use_cases`
- `suitability_notes`
- `stimulus_tags`

**Expertise Areas**:
- Training adaptations
- Population-specific recommendations
- Periodization considerations
- Exercise selection criteria

---

### 6. **Janitor Agent** 🧹
**Purpose**: Cleans up duplicates and maintains data hygiene
**Responsibilities**:
- Identifies duplicate exercises within families
- Merges redundant entries
- Standardizes naming conventions
- Removes orphaned aliases
- Consolidates similar variants

**Operations**:
- Deduplication within families
- Alias cleanup
- Version management
- Status transitions

---

### 7. **Approval Agent** ✅
**Purpose**: Auto-approves high-quality exercises
**Responsibilities**:
- Reviews quality scores from Analyst
- Checks completeness of all required fields
- Validates specialist agent outputs
- Approves exercises meeting quality threshold
- Flags exercises needing manual review

**Approval Criteria**:
- Quality score > 0.85
- All required fields present
- No critical issues
- Specialist validations passed

---

### 8. **Auditor Agent** 🔍
**Purpose**: Final quality assurance and reporting
**Responsibilities**:
- Periodic catalog-wide audits
- Cross-exercise consistency checks
- Generates quality reports
- Tracks improvement over time
- Identifies systemic issues

**Audit Areas**:
- Naming consistency
- Family organization
- Field completeness
- Content quality
- Data relationships

---

## Execution Strategy

### Phase 1: Gap Filling
1. **Scout** identifies gaps → **Creator** generates drafts

### Phase 2: Field Enrichment (Parallel)
2a. **Biomechanics Specialist** → movement & equipment
2b. **Anatomy Specialist** → muscle mapping
2c. **Content Specialist** → descriptions & instructions
2d. **Programming Specialist** → use cases & suitability

### Phase 3: Quality & Cleanup
3. **Janitor** → deduplication
4. **Analyst** → quality scoring
5. **Approval Agent** → auto-approval
6. **Auditor** → final review

## Implementation Priority

1. **Creator Agent** - Essential for filling gaps
2. **Biomechanics Specialist** - Core categorization
3. **Anatomy Specialist** - Muscle accuracy
4. **Content Specialist** - User-facing content
5. **Programming Specialist** - Training context
6. **Janitor Agent** - Data cleanup
7. **Approval Agent** - Automation
8. **Auditor Agent** - Quality assurance

## Quality Metrics

Each specialist tracks:
- Fields updated per exercise
- Accuracy rate (validated by Auditor)
- Processing time
- Error rate
- Improvement delta (before/after scores)

## Integration Points

All specialists:
- Read from Firebase via `getExercise`
- Write via `upsertExercise` (include `id` when updating; otherwise it upserts by `name_slug`/aliases)
- Alias rules: aliased names are registered under `exercise_aliases/{alias_slug}`; conflicts return 409; use `upsertAlias` for explicit aliasing.
- Idempotency: Active workout tools accept `idempotency_key` to prevent duplicate event writes.
- Upsert semantics: Server performs `set(..., { merge: true })` and sets timestamps; omits undefined.
- Log actions to orchestrator; report metrics to Analyst; can be triggered individually or in pipeline.
