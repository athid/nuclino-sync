# Phase 1: Foundation - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Parse the Apple Notes export directory fully offline into validated note objects, with no data loss and safe re-runs via atomic state tracking. No API calls in this phase. Delivers: canonical file filter, frontmatter parser, body cleaner, attachment discoverer, state manager, and a `--parse-only` entry point.

</domain>

<decisions>
## Implementation Decisions

### State file location
- **D-01:** State file lives in the export directory: `<export-dir>/nuclino-state.json`
- **D-02:** Filename is visible (not a dotfile) — easy to find and inspect

### Empty note handling
- **D-03:** Notes with empty bodies are skipped with a printed warning: `"skipped empty note: <title>"`
- **D-04:** Skipped empty notes are recorded in `state.json` with `"status": "skipped_empty"` — not re-attempted on re-run

### Phase 1 deliverable
- **D-05:** `python sync.py --parse-only` is the runnable entry point for Phase 1 verification — no API calls
- **D-06:** `--parse-only` output is summary-only: `"Found N canonical notes across A accounts, F folders. S skipped (empty). V versioned snapshots ignored."`

### Claude's Discretion
- Canonical file detection regex (versioned snapshot stems match `-\d+` before extension — implementation detail)
- Date parsing implementation (`strptime` format string for `Thursday, 12 September 2024 at 07:24:45`)
- State file JSON schema (keys, structure, version field if any)
- Test coverage approach (pytest assumed, structure up to planner)

</decisions>

<specifics>
## Specific Ideas

- The actual export at `~/Desktop/NotesExport/` has exactly 133 `.md` files for 39 canonical notes — use this as the ground truth test case
- `--parse-only` should be usable without any API key configured (purely offline operation)
- State file keyed on source path relative to export dir (e.g., `"iCloud/Notes/My Note.md"`)

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (Phase 1 scope)
- `.planning/REQUIREMENTS.md` §Export Parsing — PARSE-01 through PARSE-05 (canonical filter, title stripping, date parsing, frontmatter extraction, attachment discovery)
- `.planning/REQUIREMENTS.md` §State & Idempotency — STATE-01 through STATE-03 (state file, re-run safety, atomic writes)

### Research findings
- `.planning/research/PITFALLS.md` — 16 pitfalls; critical ones for Phase 1: versioned file pattern, title-as-first-line (81%), human-readable dates, encoding edge cases
- `.planning/research/STACK.md` — Library recommendations: `python-frontmatter` for parsing, `typer` for CLI, `rich` for output
- `.planning/research/ARCHITECTURE.md` — Flat single-file structure (`sync.py`), state file pattern, idempotency approach

### Project context
- `.planning/STATE.md` §Verified Facts — Ground truth data about the actual export (133 files, 39 canonical, date format, 2 empty notes, etc.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None yet — Phase 1 establishes the patterns

### Integration Points
- Phase 2 (Import Core) will import parse functions from `sync.py` and call them in the main import loop
- State file written in Phase 1 will be read/written by all subsequent phases

</code_context>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-21*
