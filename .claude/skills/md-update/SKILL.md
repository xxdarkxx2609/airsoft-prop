---
name: md-update
description: Update README.md and CLAUDE.md after significant code changes. Use after implementing features, refactoring, or changing architecture.
disable-model-invocation: true
allowed-tools: Read Edit Glob Grep
---

# Update README.md and CLAUDE.md

You have just completed significant changes to the Airsoft Prop project. Update both documentation files to reflect the current state of the codebase.

## Process

### 1. Understand what changed

Review recent changes to understand what needs documenting:

- Read the git diff or recent commits to identify what was added, changed, or removed
- If `$ARGUMENTS` is provided, use it as a description of what changed
- If no arguments, use `git diff --stat` and `git log --oneline -10` to determine the scope

### 2. Read both files

- Read `README.md` completely
- Read `CLAUDE.md` completely

### 3. Identify sections to update

For each file, determine which sections are affected by the changes. Common sections:

**README.md** — user-facing documentation:
- Feature list (top of file)
- Installation / Usage instructions
- Configuration section
- Web Interface table & API endpoints
- Mock mode features
- Project Structure tree
- Any relevant code examples

**CLAUDE.md** — architecture documentation for AI assistants:
- Technologie-Stack
- Architecture sections (HAL, Modes, State Machine, Screens, etc.)
- Hardware specs (if GPIO/wiring changed)
- UI-Konzept / Screen-Layouts
- Spielmodi-Spezifikationen
- Audio-System / Logging-System / Netzwerk-Konzept
- Web-Interface Architektur (Seiten & API)
- Repo-Struktur tree
- Mock-Modus section
- Code-Stil & Konventionen

### 4. Make targeted edits

- Only update sections that are actually affected by the changes
- Keep the existing style, tone, and formatting of each file
- README.md is in English, CLAUDE.md is in German
- Do NOT rewrite entire files — use the Edit tool for targeted changes
- Update the Repo-Struktur / Project Structure tree if files were added or removed
- Update API endpoint lists if routes were added or changed
- Update config examples if config/default.yaml changed

### 5. Verify consistency

After editing, verify:
- The Repo-Struktur in CLAUDE.md matches the actual file tree
- The Project Structure in README.md matches the actual file tree
- API endpoint lists match the actual routes in `src/web/server.py`
- Config examples match `config/default.yaml`
- No stale references to removed features or files

## Rules

- Do NOT add content about features that don't exist yet (planned/geplant is OK if already marked as such)
- Do NOT remove existing documentation for unchanged features
- Do NOT change the overall structure or ordering of sections
- Do NOT add emojis unless they already exist in the file
- Keep descriptions concise — match the existing level of detail
- If a new major system was added, add a dedicated section in CLAUDE.md (like the existing Logging-System, Audio-System sections)
