# Manage Epics Workflow

## Purpose

Modify the epic structure in `docs/project-context.md` without running a full planning workflow. Team Lead operates directly — no team spawn needed.

## Entry Point

User selects "manage epics" from planner intake, or uses keywords: "insert", "remove", "reorder", "split", "merge".

## Operations

### 1. Insert Epic

**Trigger**: User says "insert epic" or "add epic after EP-{NNN}"

**Steps**:
1. Ask user:
   - Where to insert (e.g., "after EP-002", "before EP-003", "at position 3 in milestone 1")
   - Epic name and description
   - Definition of Done criteria
   - Success Criteria
   - Which Key Results this epic maps to
2. Confirm with user before modifying
3. Insert the new epic entry in `docs/project-context.md`
4. Renumber ALL subsequent epics:
   - Process in DESCENDING order (highest number first) to avoid collisions
   - Update epic IDs (EP-003 → EP-004, etc.)
   - Update any cross-references to renumbered epics
5. If planning artifacts exist for renumbered epics (`docs/phases/epic-{NNN}-{desc}/`):
   - Rename folders in DESCENDING order to avoid collisions
   - Update internal references within renamed artifacts
6. Update milestone epic counts
7. Present summary of changes to user

### 2. Remove Epic

**Trigger**: User says "remove epic EP-{NNN}" or "delete epic {NNN}"

**Steps**:
1. Show the epic to be removed with its details
2. Check if planning artifacts exist at `docs/phases/epic-{NNN}-{desc}/`
3. If artifacts exist, WARN user:
   ```
   WARNING: Epic EP-{NNN} has planning artifacts:
   - epic.md
   - {N} stories
   - {N} implementation plans
   - {N} critical analyses

   These will be DELETED. This cannot be undone.

   Proceed? (yes / no)
   ```
4. If user confirms:
   - Remove epic entry from `docs/project-context.md`
   - Delete `docs/phases/epic-{NNN}-{desc}/` directory if it exists
   - Renumber ALL subsequent epics (descending order)
   - Rename subsequent epic folders (descending order)
   - Update milestone epic counts
5. Present summary of changes

### 3. Reorder Epics

**Trigger**: User says "reorder epics" or "move EP-{NNN} to position {N}"

**Steps**:
1. Show current epic order within the target milestone
2. Ask user for new order (e.g., "move EP-003 to position 1" or "swap EP-002 and EP-004")
3. Validate: check for dependency violations
   - If epic B depends on epic A, B cannot come before A
   - If violation detected, warn user and suggest alternative
4. If valid:
   - Confirm with user
   - Renumber epics to reflect new order
   - Rename artifact folders (use temp names to avoid collisions):
     a. Rename all affected folders to temp names (e.g., `epic-003-desc` → `epic-tmp-003-desc`)
     b. Rename temp folders to final names (e.g., `epic-tmp-003-desc` → `epic-001-desc`)
   - Update cross-references
5. Present summary

### 4. Split Epic

**Trigger**: User says "split EP-{NNN}" or "split epic {NNN} into two"

**Steps**:
1. Show the epic's current scope (all KRs, success criteria, stories if planned)
2. Ask user how to split:
   - Which items go to epic A vs epic B
   - Names for both resulting epics
3. Check if planning artifacts exist:
   - If yes, WARN: "This epic has been planned. Splitting will require re-planning both halves."
   - Stories and plans are NOT automatically distributed — they must be re-planned
4. If user confirms:
   - Replace original epic with first half (same position)
   - Insert second half immediately after
   - Distribute KR mappings as specified by user
   - Renumber subsequent epics (descending order)
   - If artifacts existed, move them to a backup folder: `docs/phases/epic-{NNN}-{desc}-pre-split/`
5. Present summary with note about re-planning needs

### 5. Merge Epics

**Trigger**: User says "merge EP-{NNN} and EP-{MMM}" or "combine epics"

**Steps**:
1. Validate: epics must be adjacent (or user must confirm non-adjacent merge)
2. Show both epics' scope
3. Ask user:
   - Name for merged epic
   - Combined Definition of Done
   - Combined Success Criteria
4. Check if planning artifacts exist for either epic:
   - If yes, WARN: "One or both epics have been planned. Merging will require re-planning."
   - Stories and plans are NOT automatically merged — they must be re-planned
5. If user confirms:
   - Replace first epic with merged version
   - Remove second epic
   - Combine KR mappings
   - Renumber subsequent epics (descending order)
   - If artifacts existed, move to backup: `docs/phases/epic-{NNN}-{desc}-pre-merge/`
6. Present summary

## Key Rules

1. **Always confirm with user** before modifying `docs/project-context.md`
2. **Renumber in DESCENDING order** to avoid folder/ID collisions during rename
3. **No team spawn needed** — Team Lead operates directly via Read/Write/Edit tools
4. **Warn before deleting artifacts** — planning artifacts represent significant work
5. **Use temp names for reorder** — prevents collisions when swapping positions
6. **Track cross-references** — update any epic references in other epics' dependency lists
7. **Backup before destructive splits/merges** — preserve original artifacts for reference

## Post-Operation Checklist

After any epic management operation:
- [ ] `docs/project-context.md` updated with correct epic numbering
- [ ] All epic IDs are sequential within each milestone
- [ ] Milestone epic counts match actual epic count
- [ ] No orphaned artifact folders (all match current epic numbering)
- [ ] Cross-references between epics are valid
- [ ] User confirmed all changes
