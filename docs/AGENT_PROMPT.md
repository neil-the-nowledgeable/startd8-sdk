# Agent Prompt: Updating StartD8 Project Documentation

**Copy this prompt to provide agents with context for updating StartD8 documentation**

---

## Context

I'm working on the **StartD8 SDK** project, which has a comprehensive documentation and communications system. All project files need to be updated programmatically while maintaining consistency with the persOS index system.

## Your Task

Update StartD8 project documentation files following the established standards and guidelines.

## Required Reading

Before making any updates, you MUST read:

1. **Primary Guide (REQUIRED):**
   - `/Users/neilyashinsky/Documents/Startd8/comms/AGENT_UPDATE_INSTRUCTIONS.md`
   - This is your comprehensive guide with all rules, workflows, and examples

2. **Current State (REQUIRED):**
   - Read the files you'll be updating to understand current state
   - Parse version numbers, dates, status values

3. **Quick Reference (OPTIONAL):**
   - `/Users/neilyashinsky/Documents/Startd8/comms/QUICK_REFERENCE.md`
   - Fast lookup for common patterns and rules

## Files You May Update

### Project Status Reports
- **Location:** `/Users/neilyashinsky/Documents/Startd8/comms/internal-comms/reports/`
- **Files:**
  - `PROJECT_STATUS_STARTD8_SDK_v1.md` - Weekly status report
  - `NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md` - Work assignments

### persOS Index Files (MUST UPDATE WITH PROJECT FILES)
- **Location:** `/Users/neilyashinsky/Documents/pers/persOS/index/`
- **Files:**
  - `document index.md` - Human-readable document index
  - `project_index.yaml` - YAML project/resource index
  - `tracker.yaml` - Append-only activity log

## Update Workflow

### Phase 1: Pre-Update
```
✅ Read AGENT_UPDATE_INSTRUCTIONS.md (full guide)
✅ Read current state of files to update
✅ Parse current versions, dates, status values
✅ Identify what needs to change
```

### Phase 2: Update Project Files
```
✅ Update PROJECT_STATUS (if applicable)
   - Update relevant sections
   - Increment version in REPORT_HEADER
   - Add CHANGE_LOG entry
   - Update metadata comment at top

✅ Update NEXT_WORK_ASSIGNMENTS (if applicable)
   - Update prerequisite checklist
   - Update track tables
   - Increment version in ASSIGNMENT_HEADER
   - Add CHANGE_LOG entry
```

### Phase 3: Update Index Files (CRITICAL - DON'T SKIP)
```
✅ Update document index.md
   - Add/update document entries
   - Update "Last updated" footer

✅ Update project_index.yaml
   - Increment version in metadata
   - Add to recent_activity (APPEND ONLY)
   - Update notes

✅ Update tracker.yaml
   - Increment version in metadata
   - Add new files if any (APPEND ONLY)
   - Add activity_log entry (APPEND ONLY)
```

### Phase 4: Validation
```
✅ Verify all versions incremented
✅ Verify all timestamps updated
✅ Verify table alignment maintained
✅ Verify YAML syntax (no tabs, 2 spaces)
✅ Verify all CHANGE_LOG entries added
```

## Critical Rules

### YAML Arrays (MOST IMPORTANT)
```yaml
# ✅ CORRECT - Append to END
recent_activity:
  - date: "2025-12-01"    # Existing
    activity: "Old"
  - date: "2025-12-10"    # NEW - Added at END
    activity: "New"

# ❌ WRONG - Never modify/insert in middle
recent_activity:
  - date: "2025-12-10"    # Inserted
    activity: "New"
  - date: "2025-12-01"    # This breaks everything
    activity: "Old"
```

### Version Control
- Increment version: `1.0.0` → `1.1.0` (minor for features) or `1.0.1` (patch for fixes)
- Update timestamp: `2025-12-10T16:30:00` (ISO 8601 format)
- Add CHANGE_LOG entry with summary of changes

### Index Synchronization
- **ALWAYS** update all 3 index files when making changes
- Keep descriptions consistent across files
- Maintain cross-references

## Date/Time Standards

```
Report dates:  YYYY-MM-DD              # 2025-12-10
Timestamps:    YYYY-MM-DDTHH:MM:SS     # 2025-12-10T16:30:00
Versions:      MAJOR.MINOR.PATCH       # 1.2.0
```

## Status Values

Use these exact values (case-sensitive):

```markdown
Health:     🟢 GREEN / 🟡 YELLOW / 🔴 RED
Status:     ACTIVE_DEVELOPMENT, PENDING, COMPLETE, ✅ DONE
Priority:   P0, P1, P2, P3 or CRITICAL, HIGH, MEDIUM, LOW
```

## Common Mistakes to Avoid

1. ❌ Writing files without reading first
2. ❌ Modifying existing YAML array entries
3. ❌ Forgetting to update version numbers
4. ❌ Using tabs in YAML (use 2 spaces)
5. ❌ Forgetting to update index files
6. ❌ Changing table column alignment
7. ❌ Inserting into middle of arrays

## Example Scenario

**Scenario:** Phase 4 of Cost Tracking is complete

**Actions Required:**

1. **Update PROJECT_STATUS_STARTD8_SDK_v1.md:**
   ```markdown
   ## COMPLETION_STATUS
   | Phase | Status |
   |-------|--------|
   | 4 | ✅ COMPLETE |  ← Update this
   
   ## EXECUTIVE_SUMMARY
   | completion_percentage | 90% | 100% | 🟢 NEAR_COMPLETE |
                             ↑ Update from 85%
   
   ## CHANGE_LOG
   | Version | Date | Author | Changes |
   |---------|------|--------|---------|
   | 1.1.0 | 2025-12-10 | cursor_agent | Phase 4 complete - tag normalization |
   ```

2. **Update project_index.yaml:**
   ```yaml
   startd8:
     recent_activity:
       # ... existing entries (DO NOT MODIFY)
       - date: "2025-12-10"  # Add at END
         activity: "Phase 4: Tag Normalization - Complete (10/10 tests)"
   ```

3. **Update tracker.yaml:**
   ```yaml
   activity_log:
     # ... existing entries (DO NOT MODIFY)
     - timestamp: 2025-12-10T16:30:00  # Add at END
       action: "project_complete"
       target: "startd8_phase_4"
       agent: "cursor_agent"
       details: "Phase 4 complete. 10/10 tests passing."
   ```

4. **Update document index.md:**
   ```markdown
   Last updated: 2025-12-10 at 16:30:00 (Phase 4 complete - tag normalization)
   ```

## Questions to Ask User

**ASK IF:**
- Version increment strategy unclear
- Strategic decisions needed (priorities, directions)
- Multiple valid interpretations exist
- File structure doesn't match expected format

**DON'T ASK IF:**
- Standard formatting needs fixing
- Version increment is obvious
- Timestamps need updating
- Status values need standardizing
- Adding changelog entries

## Resources

- **Full Guide:** `/Users/neilyashinsky/Documents/Startd8/comms/AGENT_UPDATE_INSTRUCTIONS.md`
- **Quick Ref:** `/Users/neilyashinsky/Documents/Startd8/comms/QUICK_REFERENCE.md`
- **Overview:** `/Users/neilyashinsky/Documents/Startd8/comms/README.md`
- **Summary:** `/Users/neilyashinsky/Documents/Startd8/comms/SUMMARY.md`

## Your Response Format

After completing updates, provide:

1. **Summary of Changes:**
   - What files were updated
   - What changed in each file
   - Version increments applied

2. **Index Synchronization:**
   - Confirm all 3 index files updated
   - List activity log entries added

3. **Validation:**
   - Confirm all checklists passed
   - Note any issues encountered

## Ready to Start?

1. ✅ Read AGENT_UPDATE_INSTRUCTIONS.md
2. ✅ Read current file states
3. ✅ Make updates following workflow
4. ✅ Update index files
5. ✅ Validate all changes
6. ✅ Report summary

**Remember:** Consistency, accuracy, and continuity are the goals. When in doubt, preserve existing structure and ask for clarification.

---

**Prompt Version:** 1.0.0  
**Created:** 2025-12-10  
**Full Documentation:** See AGENT_UPDATE_INSTRUCTIONS.md

