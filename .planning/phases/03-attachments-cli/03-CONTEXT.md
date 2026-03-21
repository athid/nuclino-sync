# Phase 3: Attachments & CLI - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Upload attachment files to Nuclino and link them to their parent items; add `--dry-run` mode; ensure every failure (note or attachment) is isolated and logged without aborting the run. CLI flags `--workspace` and `--export-dir` are already implemented from Phase 2 — this phase adds `--dry-run` only.

</domain>

<decisions>
## Implementation Decisions

### Already implemented (carry forward, do not re-implement)
- **D-01:** `--workspace` + `NUCLINO_WORKSPACE_ID` env var — fully implemented in Phase 2
- **D-02:** `--export-dir` + `NOTES_EXPORT_DIR` env var — already a `typer.Option` with envvar in `sync()`
- **D-03:** Per-note failure recording in `state.json` with `"status": "failed"` and `"error"` field — already implemented in `run_import`
- **D-04:** Note-level error isolation via `except Exception` block in `run_import` — already in place

### Claude's Discretion
All open implementation choices below are delegated to Claude:

- **Attachment linking format:** Use Nuclino's file attachment API endpoint (`POST /v0/files` or equivalent); after upload, append a reference block below the note body (outside the HTML comment footer) using whatever link format the API returns. If Nuclino's API returns a file URL or `![]()` embed syntax, use that. If the API only returns an item ID, append a plain-text reference: `Attachments: filename (id: <id>)`.

- **Attachment failure handling:** Each attachment failure is caught individually — the parent note import proceeds as `"status": "imported"` regardless. Attachment failures are stored in `state.json` under the note's key as `"attachment_failures": [{"file": "name.jpg", "error": "..."}]` so they're recoverable.

- **Dry-run output format:** `--dry-run` should print a per-note plan: note title, folder, and whether attachments exist, without making any API calls. End with a summary count. Format should match the existing `--parse-only` style (plain text, no rich progress bar).

- **Failed item summary at run end:** After the rich progress bar completes, if any notes failed, print their paths and errors to stdout after the summary line: `"Failed notes:\n  - <path>: <error>\n"` — this surfaces failures immediately without requiring the user to open state.json.

</decisions>

<specifics>
## Specific Ideas

- `attachment_dir` is already populated on `NoteFile` (Phase 1 code) — no discovery work needed, just iterate `attachment_dir.iterdir()` when it exists
- The Nuclino attachment endpoint is unverified — researcher must check the live API docs before planning
- Dry-run should be safe to run without `NUCLINO_API_KEY` set (purely offline, like `--parse-only`)

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (Phase 3 scope)
- `.planning/REQUIREMENTS.md` §Attachments — ATT-01, ATT-02
- `.planning/REQUIREMENTS.md` §Configuration & UX — CFG-01 through CFG-04 (note: CFG-01 and CFG-02 already implemented)

### Existing implementation (read before touching)
- `sync.py` — Full current implementation; `run_import`, `NoteFile`, `ensure_collection`, `sync()` CLI function all relevant
- `sync.py` lines 277–365 — `run_import` function (attachment upload slots in here, after item creation)
- `sync.py` lines 428–465 — `sync()` CLI definition (add `--dry-run` flag here)

### Prior context (carry-forward decisions)
- `.planning/phases/02-import-core/02-CONTEXT.md` — Phase 2 decisions D-01 through D-11 (all locked)
- `.planning/phases/02-import-core/02-RESEARCH.md` — API corrections (auth header, rate limit, response envelope)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NoteFile.attachment_dir: Path | None` — already populated by `discover_notes`; Phase 3 just needs to iterate it
- `api_request(client, method, path, **kwargs)` — throttled+retried HTTP function; attachment upload uses this
- `save_state(state, state_path)` — atomic write already implemented; reuse for attachment failure recording
- `run_import` exception block — already isolates per-note failures; attachment failures slot inside this try/except

### Established Patterns
- All state mutations go through `save_state` (atomic tmp+rename) — attachment failures must follow this
- Error recording pattern: `state["items"][rel_path] = {"status": "failed", "error": str(e)}` — extend, don't replace
- Typer option pattern: `typer.Option(default, "--flag", envvar="ENV_VAR", help="...")` — follow for `--dry-run`

### Integration Points
- Attachment upload goes immediately after `api_request POST /v0/items` succeeds (line ~333 in sync.py)
- `--dry-run` flag added to `sync()` function signature; passed through to `run_import` as a parameter
- Dry-run path skips `make_nuclino_client` and `resolve_workspace` calls entirely

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-attachments-cli*
*Context gathered: 2026-03-21*
