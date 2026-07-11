# File-Based Input Feature - Quick Start

**Quick reference for using the new file-based input feature in startd8 TUI**

---

## What Is This?

A new feature that lets you **load task descriptions and other inputs from files** instead of typing them every time.

---

## How to Use It

### 1. Launch the TUI

```bash
startd8 tui
```

### 2. Select a Workflow

Choose "🔄 Iterative Dev Workflow (Dev → Review → Fix)"

### 3. When Prompted for Task Description

You'll now see:
```
Choose input method:
> ✏️  Enter text directly
  📁 Load from file
  ← Cancel
```

### 4a. Option 1: Enter Text Directly

Select "✏️ Enter text directly" and type as usual.

### 4b. Option 2: Load from File

1. Select "📁 Load from file"
2. Enter the path to your file (e.g., `./my_task.txt`)
3. Preview the content
4. Confirm: "Use this content?" → Yes

---

## Example Task File

Create a file called `my_task.txt`:

```text
Implement a user authentication system with:

1. Email/password registration and login
2. Password hashing with bcrypt
3. JWT token generation for sessions
4. Password reset via email
5. Rate limiting for security
6. Comprehensive unit and integration tests

Use Flask as the web framework and PostgreSQL for the database.
Follow best practices for security and code quality.
```

Then load it in the TUI:
1. Choose "📁 Load from file"
2. Enter: `./my_task.txt`
3. Review the preview
4. Confirm to use

---

## Benefits

✅ **Reusable** - Write once, use many times  
✅ **Version Control** - Keep task files in Git  
✅ **Shareable** - Send task files to teammates  
✅ **Complex Tasks** - Handle large, detailed requirements easily  
✅ **Templates** - Create templates for common tasks  
✅ **Flexible** - Still can type directly for quick tasks

---

## Where It Works

Currently available in:
- ✅ **Iterative Dev Workflow** - Task descriptions

Coming soon to:
- Document Enhancement Chain
- Prompt Builder
- Design Pipeline
- Job Queue

---

## File Format

- **Supported**: Any plain text file (UTF-8 encoding)
  - `.txt` files
  - `.md` Markdown files
  - `.py`, `.js` source code files (as text)
  - Any text-based format

- **Not Supported**: Binary files (images, PDFs, etc.)

---

## Tips

1. **Keep templates** - Create a `templates/` folder for common tasks
2. **Use Git** - Version control your task files
3. **Share with team** - Task files are portable
4. **Iterate** - Edit and reload files to refine tasks
5. **Name clearly** - Use descriptive filenames like `auth-system-task.txt`

---

## Documentation

For more details, see:

| Document | Purpose |
|----------|---------|
| `FILE_INPUT_FEATURE.md` | Complete feature documentation |
| `DEVELOPER_GUIDE_FILE_INPUT.md` | Integration guide for developers |
| `FEATURE_SUMMARY.md` | Executive summary |
| `test_task_example.txt` | Example task file |

---

## Need Help?

If you encounter any issues:

1. Check the file path is correct
2. Ensure the file is UTF-8 text (not binary)
3. Verify the file exists and is readable
4. See error messages for specific guidance

---

## Quick Example Session

```bash
$ startd8 tui

# Select: 🔄 Iterative Dev Workflow

# At "Task Description" prompt:
# Choose: 📁 Load from file
# Enter: ./my_task.txt
# Review preview showing first 300 chars
# Confirm: Yes

# Continue with workflow as normal...
```

---

**Feature Version**: 1.0  
**Status**: ✅ Production Ready  
**Date**: December 9, 2025

Enjoy using file-based inputs! 🚀
