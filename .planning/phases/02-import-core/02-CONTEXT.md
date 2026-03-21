# Phase 2: Import Core - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Add Nuclino API integration to `sync.py`: authenticate, resolve workspace, create collections (idempotent), create items with cleaned body and metadata footer, handle rate limits with exponential backoff. Phase 1's parse functions are already complete — this phase wires them to the API and delivers a working import run.

</domain>

<decisions>
## Implementation Decisions

### Metadata footer format
- **D-01:** Metadata is appended as an HTML comment block — invisible in Nuclino's rendered view
- **D-02:** Format:
  ```
  <!-- nuclino-sync
  created: 2024-09-12T07:24:45
  modified: 2024-09-12T09:00:00
  -->
  ```
- **D-03:** Block is only appended when data exists — omitted entirely if both `created` and `modified` are `None`
- **D-04:** ISO 8601 format for timestamps (already available from Phase 1's `datetime` objects via `.isoformat()`)

### Import progress output
- **D-05:** Display a `rich` progress bar during import — shows N/total notes processed
- **D-06:** Progress bar replaces per-note line output — no per-note stdout during import
- **D-07:** After import completes, print summary counts only: `"Imported N notes. F failed. See nuclino-state.json for details."`
- **D-08:** Failures are recorded in `state.json` with `"status": "failed"` and error message — not printed to stdout during the run

### Workspace resolution
- **D-09:** `--workspace` flag (or `NUCLINO_WORKSPACE_ID` env var) is **required** — hard error if omitted: `"Error: --workspace is required. Set NUCLINO_WORKSPACE_ID or pass --workspace."`
- **D-10:** If the provided name/ID doesn't match any workspace, list available workspaces and prompt interactively: `"No workspace 'X' found. Available:\n  1. Name\n  2. Name\nWhich one? (Ctrl+C to cancel)"`
- **D-11:** Workspace can be specified by name (case-insensitive match) or by ID (exact match)

### Claude's Discretion
- httpx vs requests for HTTP client (research recommendation: httpx)
- Exact retry/backoff implementation (tenacity or manual loop — per STACK.md recommendation)
- Collection creation endpoint details (to be verified against live API)
- Item creation request body structure (to be verified against live API)
- Whether to store workspace ID vs name in state.json

</decisions>

<specifics>
## Specific Ideas

- The HTML comment approach keeps notes visually clean — metadata is preserved for future use without cluttering the rendered view
- Interactive workspace selection matches the UX of tools like `heroku`, `fly`, `gh` — familiar pattern
- The `rich` progress bar is already a dependency from Phase 1 (`pyproject.toml`) — use `rich.progress.track()` for simplicity

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing implementation (Phase 1)
- `sync.py` — ALL existing functions: `NoteFile`, `ParsedNote`, `is_canonical`, `discover_notes`, `parse_note`, `clean_body`, `load_state`, `save_state`, `run_parse_only`, CLI structure. Phase 2 EXTENDS this file — do not rewrite existing functions.

### Requirements (Phase 2 scope)
- `.planning/REQUIREMENTS.md` §Nuclino API Client — API-01 through API-06

### Research findings
- `.planning/research/FEATURES.md` — Nuclino API endpoints, what's supported, metadata loss constraints, rate limits
- `.planning/research/STACK.md` — httpx, tenacity recommendations; rate-limit pattern
- `.planning/research/SUMMARY.md` — Phased roadmap implications, open questions needing live API verification
- `.planning/research/PITFALLS.md` — API-specific pitfalls: collection name collision across accounts, state atomicity timing

### Project state
- `.planning/STATE.md` §Decisions Pending — bare URL handling (still unresolved, defer to Phase 4)
- `.planning/STATE.md` §Todos — live API verification session required before Phase 2 execution

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `discover_notes(export_dir)` → `(list[NoteFile], int)` — ready to call
- `parse_note(note_file)` → `ParsedNote` — returns title, body, created, modified, attachment_dir
- `clean_body(body, title)` → `str` — strips duplicate title line
- `load_state(state_path)` → `dict` — `{"version": 1, "items": {}}` schema
- `save_state(state, state_path)` — atomic write via tmp+rename
- `app = typer.Typer()` with `sync()` command already wired — add new params to this command

### Established Patterns
- State keyed on `str(note_file.md_path.relative_to(export_dir))` — must use same key in Phase 2
- State item schema: `{"status": "parsed"|"skipped_empty"|"failed", "title": ..., ...}` — Phase 2 adds `"nuclino_item_id"`, `"nuclino_collection_id"` to existing entries
- `typer.echo()` for output — use `rich` progress bar for import loop
- `state_path = export_dir / "nuclino-state.json"` — location established in Phase 1

### Integration Points
- Phase 2 adds a `run_import()` function called from the `sync()` CLI command when `--parse-only` is not set
- State written IMMEDIATELY after `POST /items` succeeds, BEFORE attachment uploads (critical — see STATE.md)
- Phase 3 (Attachments & CLI) will read `nuclino_item_id` from state entries written in Phase 2

</code_context>

<deferred>
## Deferred Ideas

- Bare URL wrapping (`<https://...>`) — pending live API verification of auto-linking behavior (STATE.md §Decisions Pending)
- `--dry-run` flag — Phase 3 (CFG-03)
- Per-note verbose output (`--verbose`) — Phase 4 polish

</deferred>

---

*Phase: 02-import-core*
*Context gathered: 2026-03-21*
