# Quick Reference: Agent Update Guide

**🚀 Fast reference for updating StartD8 project files**

---

## 📋 Update Checklist

```
✅ Read current file state
✅ Update project files (status/assignments)
✅ Update persOS index files (document index, project_index, tracker)
✅ Validate (versions, timestamps, formatting)
```

---

## 📁 Key Files

| File | Location | Purpose |
|------|----------|---------|
| **PROJECT_STATUS** | `comms/internal-comms/reports/` | Weekly status report |
| **NEXT_WORK_ASSIGNMENTS** | `comms/internal-comms/reports/` | Work planning |
| **document index.md** | `pers/persOS/index/` | Human-readable index |
| **project_index.yaml** | `pers/persOS/index/` | YAML project index |
| **tracker.yaml** | `pers/persOS/index/` | Activity log |

---

## 📅 Date Formats

```yaml
Report dates:    YYYY-MM-DD           # 2025-12-10
Timestamps:      YYYY-MM-DDTHH:MM:SS  # 2025-12-10T16:30:00
Versions:        MAJOR.MINOR.PATCH    # 1.2.0
```

---

## 🎯 Status Values

### Health
- 🟢 GREEN / PASSING / EXCELLENT / EXCEEDS
- 🟡 YELLOW / NEAR_COMPLETE / BLOCKING
- 🔴 RED / FAILING / CRITICAL

### Status
- `ACTIVE_DEVELOPMENT` / `PENDING` / `IN_PROGRESS`
- `COMPLETE` / `✅ COMPLETE` / `✅ DONE`
- `BLOCKED` / `DEFERRED` / `CANCELLED`

### Priority
- `P0` CRITICAL | `P1` HIGH | `P2` MEDIUM | `P3` LOW
- `CRITICAL` | `HIGH` | `MEDIUM` | `LOW` | `DEFERRED`

---

## 🔄 Version Control

```markdown
## CHANGE_LOG
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.X.0   | YYYY-MM-DD | cursor_agent | Brief summary |
```

**When to increment:**
- MAJOR: Breaking changes
- MINOR: New features, sections, significant updates
- PATCH: Bug fixes, typos, small corrections

---

## 📝 Common Updates

### Mark Issue Complete

```markdown
### ISSUE_XXX
| Field | Value |
|-------|-------|
| status | ✅ RESOLVED |  ← Change from OPEN
| resolution_date | YYYY-MM-DD |  ← Add
| resolution | Description of how fixed |  ← Add
```

### Mark Milestone Complete

```markdown
| Milestone | Date | Status |
|-----------|------|--------|
| phase_X_complete | YYYY-MM-DD | ✅ DONE |  ← Add to Completed section
```

### Update Completion %

```markdown
| completion_percentage | XX% | 100% | 🟡 NEAR_COMPLETE |
                          ↑ Update this
```

### Mark Task Complete

```markdown
| Task ID | Task | Effort | Priority |
|---------|------|--------|----------|
| P1.1 | ✅ Secure API Key Manager | 12h | CRITICAL |
         ↑ Add checkmark
```

---

## 📊 YAML Updates

### Metadata

```yaml
metadata:
  version: "1.X.X"  # Increment
  last_modified: "YYYY-MM-DDTHH:MM:SS"  # Update
  modified_by: "cursor_agent"
  notes: "Brief description"  # Update
```

### Add Recent Activity (APPEND ONLY)

```yaml
startd8:
  recent_activity:
    # ... existing (NEVER MODIFY)
    - date: "YYYY-MM-DD"  # Add at END
      activity: "Description"
```

### Add Activity Log (APPEND ONLY)

```yaml
activity_log:
  # ... existing (NEVER MODIFY)
  - timestamp: YYYY-MM-DDTHH:MM:SS  # Add at END
    action: "action_type"
    target: "what_changed"
    agent: "cursor_agent"
    details: "Detailed description"
```

### Add File (APPEND ONLY)

```yaml
local:
  files:
    # ... existing (NEVER MODIFY)
    - path: "/absolute/path/to/file.md"  # Add at END
      name: "Human Name"
      description: "What it contains"
      tags: [tag1, tag2]
      added: YYYY-MM-DD
      added_by: "cursor_agent"
```

---

## ⚠️ Critical Rules

### YAML Safety
- ✅ **ALWAYS APPEND** to arrays (never insert/modify)
- ✅ Use **2 spaces** for indentation (NO TABS)
- ✅ Validate YAML syntax before saving

### Version Control
- ✅ **INCREMENT VERSION** on every update
- ✅ **UPDATE TIMESTAMP** to current date/time
- ✅ **ADD CHANGE_LOG** entry

### Index Sync
- ✅ Update **ALL 3 INDEX FILES** when making changes
- ✅ Keep descriptions **consistent** across files
- ✅ Maintain **cross-references**

---

## 🔧 Tool Usage

```
1. Read   → Get current state
2. Update → StrReplace for targeted changes
3. Verify → Read again if uncertain
```

**❌ NEVER:**
- Write entire files without reading first
- Modify existing YAML array entries
- Change table formatting
- Forget version/timestamp updates

---

## 📂 Section Markers

### PROJECT_STATUS file
- `REPORT_HEADER` - Metadata table
- `EXECUTIVE_SUMMARY` - High-level status
- `COMPLETION_STATUS` - Phase tracking
- `KNOWN_ISSUES` - Issue details (ISSUE_XXX subsections)
- `TIMELINE` - Milestones
- `NEXT_ACTIONS` - Action items
- `CHANGE_LOG` - Document history

### NEXT_WORK_ASSIGNMENTS file
- `ASSIGNMENT_HEADER` - Metadata
- `PREREQUISITE_CHECKLIST` - Blocking items
- `TRACK_A/B/C` - Work tracks
- `RECOMMENDED_ASSIGNMENT_PLAN` - Weekly assignments
- `STRATEGIC_DECISIONS` - Leadership decisions
- `CHANGE_LOG` - Document history

---

## 🎬 Quick Start Examples

### Update Phase Status

1. Read PROJECT_STATUS file
2. Find COMPLETION_STATUS section
3. Update phase status to ✅ COMPLETE
4. Update tests count (e.g., 18/18)
5. Increment version, add changelog
6. Update index files with activity

### Add New Issue

1. Read PROJECT_STATUS file
2. Add ISSUE_XXX section under KNOWN_ISSUES
3. Increment known_issues count in EXECUTIVE_SUMMARY
4. Change health if critical
5. Increment version, add changelog
6. Update index files with activity

### Mark Task Complete

1. Read NEXT_WORK_ASSIGNMENTS file
2. Find task in track table
3. Add ✅ to task description
4. Update prerequisite if needed
5. Increment version, add changelog
6. Update index files with activity

---

## 📖 Full Documentation

For complete details, see:
- **AGENT_UPDATE_INSTRUCTIONS.md** (580+ lines, comprehensive guide)
- **README.md** (System overview and integration)
- **SUMMARY.md** (High-level summary)

---

## 🆘 When to Ask

**ASK if:**
- Version strategy unclear (major vs minor)
- Strategic decisions needed
- Multiple valid interpretations
- File structure unexpected
- Conflicting information

**DON'T ASK if:**
- Standard formatting fixes needed
- Version increment obvious
- Timestamps need updating
- Status values need standardizing
- Adding changelog/activity log entries

---

**Quick Ref Version:** 1.0.0  
**Last Updated:** 2025-12-10  
**Full Guide:** AGENT_UPDATE_INSTRUCTIONS.md

