# AGENT UPDATE INSTRUCTIONS: StartD8 Project Documentation

**Purpose:** Instructions for AI agents updating StartD8 documentation with persOS index integration

---

## FILES TO UPDATE

| File | Location |
|------|----------|
| PROJECT_STATUS_STARTD8_SDK_v1.md | `/Users/neilyashinsky/Documents/Startd8/comms/internal-comms/reports/` |
| NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md | `/Users/neilyashinsky/Documents/Startd8/comms/internal-comms/reports/` |
| document index.md | `/Users/neilyashinsky/Documents/pers/persOS/index/` |
| project_index.yaml | `/Users/neilyashinsky/Documents/pers/persOS/index/` |
| tracker.yaml | `/Users/neilyashinsky/Documents/pers/persOS/index/` |

---

## CRITICAL RULES

1. **ALWAYS** read files before updating
2. **NEVER** modify existing YAML array entries - only append to END
3. **ALWAYS** use 2 spaces in YAML (NO TABS)
4. **ALWAYS** increment versions and update timestamps
5. **ALWAYS** update all 3 index files when changing project files
6. **ALWAYS** add CHANGE_LOG entries

---

## STANDARDS

### Dates & Versions
- Report dates: `YYYY-MM-DD` (e.g., `2025-12-10`)
- Timestamps: `YYYY-MM-DDTHH:MM:SS` (e.g., `2025-12-10T16:30:00`)
- Versions: `MAJOR.MINOR.PATCH` (e.g., `1.2.0`)

### Status Values
- Health: `🟢 GREEN` / `🟡 YELLOW` / `🔴 RED`
- Status: `ACTIVE_DEVELOPMENT`, `PENDING`, `COMPLETE`, `✅ DONE`, `BLOCKED`
- Priority: `P0` (critical), `P1` (high), `P2` (medium), `P3` (low)

---

## UPDATE WORKFLOW

### 1. Pre-Update
- Read all files to update
- Parse current versions, dates, status

### 2. Update Project Files
#### PROJECT_STATUS_STARTD8_SDK_v1.md
- Update metadata comment: `version`, `report_date`
- Update `REPORT_HEADER`: `report_date`, `health`
- Update `EXECUTIVE_SUMMARY`: `completion_percentage`, `known_issues`
- Update `COMPLETION_STATUS`: mark phases `✅ COMPLETE`, update test counts
- Add/update `KNOWN_ISSUES`: new ISSUE_XXX sections
- Update `TIMELINE`: move completed to "Completed Milestones"
- Update `NEXT_ACTIONS`: remove done, add new
- Add `CHANGE_LOG` entry
- Increment version

#### NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md
- Update `PREREQUISITE_CHECKLIST`: mark items `✅ COMPLETE`
- Update `TRACK_A/B/C`: add `✅` to completed tasks
- Update `RECOMMENDED_ASSIGNMENT_PLAN`: adjust weekly assignments
- Add `CHANGE_LOG` entry
- Increment version

### 3. Update Index Files (REQUIRED)
#### document index.md
- Add new docs under appropriate section:
  ```markdown
  - **DOC_NAME.md** - Description (Last updated: YYYY-MM-DD)
  ```
- Update footer: `Last updated: YYYY-MM-DD at HH:MM:SS (summary)`

#### project_index.yaml
- Increment `version`, update `last_modified`, update `notes`
- Add to arrays (APPEND ONLY to END):
  ```yaml
  startd8:
    recent_activity:
      # existing...
      - date: "YYYY-MM-DD"
        activity: "Description"
  ```

#### tracker.yaml
- Increment `version`, update `last_updated`, update `notes`
- Add to arrays (APPEND ONLY to END):
  ```yaml
  local:
    files:
      # existing...
      - path: "/absolute/path"
        name: "Name"
        description: "Description"
        tags: [tag1, tag2]
        added: YYYY-MM-DD
        added_by: "cursor_agent"
  
  activity_log:
    # existing...
    - timestamp: YYYY-MM-DDTHH:MM:SS
      action: "action_type"
      target: "what_changed"
      agent: "cursor_agent"
      details: "Description"
  ```

### 4. Validation
- [ ] All versions incremented
- [ ] All timestamps current
- [ ] Tables aligned
- [ ] YAML valid (no tabs)
- [ ] CHANGE_LOG entries added
- [ ] All 3 index files updated

---

## EXAMPLES

### Phase Completion
1. **PROJECT_STATUS**: Change phase to `✅ COMPLETE`, update %, add to TIMELINE, add CHANGE_LOG
2. **NEXT_WORK_ASSIGNMENTS**: Update prerequisites, adjust assignments, add CHANGE_LOG
3. **project_index.yaml**: Append to `recent_activity`
4. **tracker.yaml**: Append to `activity_log`
5. **document index.md**: Update footer

### New Issue
1. **PROJECT_STATUS**: Add `ISSUE_XXX` section, increment count, update health, add CHANGE_LOG
2. **NEXT_WORK_ASSIGNMENTS**: Add to prerequisites/tracks, add CHANGE_LOG
3. **Index files**: Update activity logs

### New Document
1. **document index.md**: Add entry, update footer
2. **project_index.yaml**: Append to `key_docs`, update metadata
3. **tracker.yaml**: Append to `files` and `activity_log`, update metadata

---

## YAML SAFETY

**CRITICAL - APPEND ONLY:**
```yaml
# ✅ CORRECT
array:
  - existing_item
  - new_item  # Added at END

# ❌ WRONG - Never insert/modify
array:
  - new_item  # Inserted - breaks system
  - existing_item
```

**Common action types for activity_log:**
- `added_files`, `added_project`, `index_update`, `project_complete`, `status_report_update`, `work_assignment_update`

---

## COMMON MISTAKES

❌ Reformatting entire files  
❌ Modifying existing YAML entries  
❌ Using tabs in YAML  
❌ Forgetting version/timestamp updates  
❌ Skipping index file updates  
❌ Inserting into middle of arrays  
❌ Breaking table alignment

---

## WHEN TO ASK

**Ask user if:**
- Version strategy unclear (major vs minor)
- Strategic decisions needed
- File structure unexpected
- Conflicting information

**Don't ask - just do:**
- Fixing formatting
- Updating timestamps
- Adding CHANGE_LOG entries
- Standardizing status values

---

**Version:** 2.0.0 (Streamlined)  
**Last Updated:** 2025-12-10
