# nuclino-sync

## What This Is

A Python script that imports Apple Notes exports into Nuclino via the Nuclino API. Given an export directory (`~/Desktop/NotesExport/`) structured as `<Account>/<Folder>/<Note Title>.md`, it maps each Notes folder to a Nuclino collection inside an existing workspace, uploads note content, and attaches any associated files (photos, PDFs).

## Core Value

Every note and its attachments land in the right Nuclino collection without manual copy-paste, preserving as much metadata as possible.

## Requirements

### Validated

- ✓ Read Apple Notes export directory recursively, filtering versioned snapshots to canonical notes only — Phase 1
- ✓ Parse YAML frontmatter (`title`, `created`, `modified`) and clean note body (strip duplicate title line) — Phase 1
- ✓ Atomic state file (`nuclino-state.json`) enabling safe re-runs without duplicate imports — Phase 1

### Active

- [ ] Read Apple Notes export directory recursively across all Account subdirectories
- [ ] Map each Notes folder to a Nuclino collection inside a specified existing workspace
- [ ] Upload note markdown body to Nuclino as a new item
- [ ] Map YAML frontmatter fields (e.g. created, tags) to Nuclino item properties where the API supports it
- [ ] Upload attachments from the note's companion directory and attach to the Nuclino item
- [ ] Accept workspace target via name or ID (config or CLI flag)
- [ ] Skip items that fail gracefully with a log entry, not a hard crash

### Out of Scope

- Ongoing sync / incremental updates — one-time migration only
- Creating a new Nuclino workspace — target workspace must already exist
- Filtering by account — all accounts in the export are imported

## Context

- Export format: `~/Desktop/NotesExport/<Account>/<Folder>/<Note Title>.md` with optional `<Note Title>/` sibling directory for attachments
- Each `.md` file has YAML frontmatter (created date, tags, etc.) followed by the note body
- Nuclino API: REST API at api.nuclino.com, requires API key
- Nuclino structure: Workspace → Teams/Collections → Items (pages)

## Constraints

- **Tech stack**: Python — good YAML/markdown/REST support
- **Auth**: Nuclino API key, provided via env var or config file (not hardcoded)
- **API limits**: Nuclino API has rate limits — script should handle 429 responses with backoff

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Folder → Collection mapping | User confirmed this structure | — Pending |
| Map frontmatter to Nuclino fields | Preserves metadata rather than discarding it | — Pending |
| All accounts imported | No filtering needed for user's use case | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-21 after Phase 3 (Attachments & CLI) — attachment upload with 404 degradation, --dry-run flag, post-run failure summary, 63 tests passing*
