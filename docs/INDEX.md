# StartD8 Communications System - Document Index

**Central index of all documentation in the comms system**

---

## 🎯 For AI Agents

Start here when updating StartD8 project files:

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **[AGENT_PROMPT.md](./AGENT_PROMPT.md)** | Copy-paste prompt for agents | Give this prompt to new agents |
| **[AGENT_UPDATE_INSTRUCTIONS.md](./AGENT_UPDATE_INSTRUCTIONS.md)** | Comprehensive guide (580+ lines) | **READ THIS FIRST** - Complete rules & workflows |
| **[QUICK_REFERENCE.md](./QUICK_REFERENCE.md)** | Fast lookup reference | Quick checks while working |

---

## 📊 Active Project Reports

Current status and planning documents:

| Document | Location | Version | Last Updated | Purpose |
|----------|----------|---------|--------------|---------|
| **[PROJECT_STATUS_STARTD8_SDK_v1.md](./internal-comms/reports/PROJECT_STATUS_STARTD8_SDK_v1.md)** | `reports/` | 1.0.0 | 2025-12-10 | Weekly status report |
| **[NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md](./internal-comms/reports/NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md)** | `reports/` | 1.1.0 | 2025-12-10 | Work planning |

---

## 📚 System Documentation

Overview and reference docs:

| Document | Purpose | Audience |
|----------|---------|----------|
| **[README.md](./README.md)** | System overview | Humans & agents |
| **[SUMMARY.md](./SUMMARY.md)** | High-level summary | Quick overview |
| **[INDEX.md](./INDEX.md)** | This file | Navigation |

---

## 🔧 Templates & Examples

| Document | Location | Purpose |
|----------|----------|---------|
| **[SKILL.md](./internal-comms/SKILL.md)** | `internal-comms/` | project-comms skill definition |
| **[3p-updates.md](./internal-comms/examples/3p-updates.md)** | `examples/` | Third-party update template |
| **[company-newsletter.md](./internal-comms/examples/company-newsletter.md)** | `examples/` | Newsletter template |
| **[faq-answers.md](./internal-comms/examples/faq-answers.md)** | `examples/` | FAQ template |
| **[general-comms.md](./internal-comms/examples/general-comms.md)** | `examples/` | General comms template |

---

## 🔗 Related Systems

### persOS Index Files

**Location:** `/Users/neilyashinsky/Documents/pers/persOS/index/`

These files MUST be updated when making changes to StartD8 docs:

| File | Purpose | Update Rule |
|------|---------|-------------|
| **document index.md** | Human-readable document index | Add entries, update footer |
| **project_index.yaml** | YAML project/resource index | Append to arrays, update metadata |
| **tracker.yaml** | Activity log (append-only) | Add activity_log entries |

### StartD8 SDK Documentation

**Location:** `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/`

| Document | Purpose |
|----------|---------|
| README.md | SDK overview |
| docs/SDK_ARCHITECTURE_v1.md | Architecture documentation |
| docs/API_REFERENCE_v1.md | API reference |
| SECURITY_IMPLEMENTATION_PLAN.md | Security roadmap (8 weeks, 160 hours) |
| ENTERPRISE_CODE_REVIEW_WEEK2.md | Enterprise architecture review |

### StartD8 MCP Integration

**Location:** `/Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder/`

| Document | Purpose |
|----------|---------|
| README_SERVER.md | MCP server documentation |
| startd8_use_skill_refactor_plan.md | JSON refactor plan |
| context/*.md | Context docs for various LLMs |

---

## 📋 Update Workflows

### Quick Workflow

```
1. Read AGENT_UPDATE_INSTRUCTIONS.md
2. Read current file states
3. Update project files (status/assignments)
4. Update index files (document index, project_index, tracker)
5. Validate (versions, timestamps, YAML)
```

### Detailed Workflow

See **[AGENT_UPDATE_INSTRUCTIONS.md](./AGENT_UPDATE_INSTRUCTIONS.md)** Section: "UPDATE WORKFLOW CHECKLIST"

---

## 📐 Standards Reference

### Version Control
- Format: `MAJOR.MINOR.PATCH` (e.g., `1.2.0`)
- Increment: Minor for features, Patch for fixes
- Document: Add CHANGE_LOG entry with every update

### Date/Time Formats
```
Report dates:  YYYY-MM-DD              # 2025-12-10
Timestamps:    YYYY-MM-DDTHH:MM:SS     # 2025-12-10T16:30:00
```

### Status Values
```
Health:     🟢 GREEN / 🟡 YELLOW / 🔴 RED
Status:     ACTIVE, PENDING, COMPLETE, ✅ DONE
Priority:   P0 (critical), P1 (high), P2 (medium), P3 (low)
```

### YAML Rules
- Use **2 spaces** for indentation (NO TABS)
- **APPEND ONLY** to arrays (never insert/modify)
- Validate syntax before saving

---

## 🎓 Learning Path

### For New Agents

1. **Start:** [AGENT_PROMPT.md](./AGENT_PROMPT.md) - Copy this prompt
2. **Read:** [AGENT_UPDATE_INSTRUCTIONS.md](./AGENT_UPDATE_INSTRUCTIONS.md) - Full guide
3. **Reference:** [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - While working
4. **Context:** [README.md](./README.md) - System overview
5. **Practice:** Update a test section following workflows

### For Experienced Agents

1. **Check:** [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - Fast lookups
2. **Verify:** [AGENT_UPDATE_INSTRUCTIONS.md](./AGENT_UPDATE_INSTRUCTIONS.md) - Specific rules
3. **Update:** Make changes following established patterns

---

## 📊 Current Project Status

**As of 2025-12-10:**

### StartD8 SDK
- **Completion:** 96% (Cost Tracking System v1.0.0)
- **Tests:** 341/341 passing (100%)
- **Quality:** 9.2/10 (Excellent)
- **Blocking Issues:** 3 (Response ID, Gemini, Budget Coupling)

### Next Steps
- **Track A:** Security & Robustness (160h, 8 weeks) - CRITICAL
- **Track B:** MCP JSON Refactor (16-24h, 1-2 weeks) - HIGH  
- **Track C:** Cost Tracking Phases (selective) - MEDIUM

See **[PROJECT_STATUS_STARTD8_SDK_v1.md](./internal-comms/reports/PROJECT_STATUS_STARTD8_SDK_v1.md)** for full details.

---

## 🔍 Finding Information

### By Task

| Task | Document |
|------|----------|
| Update project status | PROJECT_STATUS_STARTD8_SDK_v1.md |
| Update work assignments | NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md |
| Learn update process | AGENT_UPDATE_INSTRUCTIONS.md |
| Quick reference | QUICK_REFERENCE.md |
| Get prompt for agent | AGENT_PROMPT.md |
| Understand system | README.md |

### By Question

| Question | Document | Section |
|----------|----------|---------|
| How do I update a status report? | AGENT_UPDATE_INSTRUCTIONS | "PROJECT_STATUS_STARTD8_SDK_v1.md" |
| What date format do I use? | QUICK_REFERENCE | "Date Formats" |
| How do I add to YAML arrays? | AGENT_UPDATE_INSTRUCTIONS | "tracker.yaml" |
| What are valid status values? | QUICK_REFERENCE | "Status Values" |
| How do I version documents? | AGENT_UPDATE_INSTRUCTIONS | "Version Control" |

---

## 🛠️ Tools & Best Practices

### Required Tools
1. **Read** - Get current state (ALWAYS FIRST)
2. **StrReplace** - Targeted updates
3. **Write** - Only for new files

### Best Practices
- ✅ Read before writing
- ✅ Preserve structure
- ✅ Increment versions
- ✅ Update timestamps
- ✅ Add changelog entries
- ✅ Update all 3 index files
- ✅ Validate YAML (no tabs)
- ✅ Maintain consistency

### Common Errors
- ❌ Modifying YAML arrays in middle
- ❌ Using tabs in YAML
- ❌ Forgetting version increments
- ❌ Skipping index file updates
- ❌ Breaking table alignment

---

## 📞 Support

### Issues or Questions?

1. **Check documentation:** Most answers in AGENT_UPDATE_INSTRUCTIONS.md
2. **Review examples:** See "EXAMPLE UPDATE SCENARIOS" section
3. **Verify standards:** Use QUICK_REFERENCE.md
4. **Ask user:** If strategic decisions needed

### Reporting Problems

If you encounter issues with this system:
- Document the problem clearly
- Note which file and section
- Include current vs. expected state
- Suggest improvements

---

## 📝 Document Metadata

| Field | Value |
|-------|-------|
| Index Version | 1.0.0 |
| Created | 2025-12-10 |
| Last Updated | 2025-12-10T16:45:00 |
| Maintainer | cursor_agent |
| Status | Active |

---

## 🗺️ Directory Structure

```
comms/
├── INDEX.md                           ← You are here
├── AGENT_PROMPT.md                    ← Give to new agents
├── AGENT_UPDATE_INSTRUCTIONS.md       ← Comprehensive guide (READ FIRST)
├── QUICK_REFERENCE.md                 ← Fast lookup
├── README.md                          ← System overview
├── SUMMARY.md                         ← High-level summary
│
└── internal-comms/
    ├── SKILL.md                       ← project-comms skill
    ├── LICENSE.txt                    ← MIT License
    │
    ├── examples/                      ← Templates
    │   ├── 3p-updates.md
    │   ├── company-newsletter.md
    │   ├── faq-answers.md
    │   └── general-comms.md
    │
    └── reports/                       ← Active reports
        ├── PROJECT_STATUS_STARTD8_SDK_v1.md
        └── NEXT_WORK_ASSIGNMENTS_STARTD8_v1.md
```

---

**Navigation:** [Top](#startd8-communications-system---document-index) | [For Agents](#-for-ai-agents) | [Reports](#-active-project-reports) | [Standards](#-standards-reference)

