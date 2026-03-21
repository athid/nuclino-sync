# Phase 4: Hardening - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the script safe to hand to someone who did not write it. Four concrete deliverables: (1) enhanced `--dry-run` pre-flight summary, (2) empty-body notes imported with a placeholder instead of skipped, (3) special characters in collection names handled without crashing, (4) README with a minimal working example. No new v1 requirements — this phase validates and hardens Phases 1–3.

</domain>

<decisions>
## Implementation Decisions

### Dry-run pre-flight summary
- **D-01:** Enhance `run_dry_run` to print a metadata summary block before the per-note list. Format:
  ```
  Pre-flight summary:
    Notes to import:    N
    Notes to skip:      M (already imported or empty)
    Attachments:        K notes have attachments
    Metadata footer:    created, modified will be appended as HTML comment
    Lost fields:        tags (not in this export's frontmatter — no loss expected)
                        any other frontmatter fields not mapped above
  ```
- **D-02:** "Lost fields" means frontmatter keys that are NOT `title`, `created`, or `modified` — these are not serialized into the footer. For this export, no such fields exist, but the summary should enumerate them if found by scanning all notes' frontmatter.
- **D-03:** The summary prints BEFORE the per-note lines and BEFORE any API calls (dry-run already makes none).

### Empty note handling change
- **D-04:** Change `run_import` to import empty-body notes with content `*(empty note)*` instead of skipping them. The placeholder replaces the empty body; the metadata footer (if dates exist) is still appended after.
- **D-05:** State entry for placeholder notes uses `"status": "imported"` (same as regular notes) — they should not be re-imported on re-run.
- **D-06:** `run_dry_run` should also change: instead of `"skip (empty)"`, show `"import (empty → placeholder): <title>"`.
- **D-07:** The old `"status": "skipped_empty"` state entries from prior runs are left as-is — they will be retried on the next real import run since they don't match `"status": "imported"`. This is correct behavior (users can now import them).

### Special character handling in collection names
- **D-08:** Strip or replace characters that cause issues in collection titles. Replace `/` with ` - ` (space-dash-space). Strip `&` → `and`. Any other non-printable or control characters stripped entirely.
- **D-09:** Apply sanitization in `ensure_collection` to both `account` and `folder` strings before using as `title` in the API request. The state key still uses the original unsanitized strings (for idempotency against the source data).
- **D-10:** Log a one-time warning if any collection name was sanitized: `"Warning: collection name sanitized: 'A/B' → 'A - B'"`.

### README content
- **D-11:** README covers exactly: prerequisites (Python 3.11+, pip), install (`pip install -e .`), required env vars (`NUCLINO_API_KEY`, `NUCLINO_WORKSPACE_ID`), minimal run command (`python sync.py`), dry-run example, and what the state file is.
- **D-12:** No troubleshooting section — keep it minimal. Link to Nuclino API docs for rate limits.
- **D-13:** README is `README.md` in the project root. If it already exists, overwrite (it's likely empty or a stub).

### Claude's Discretion
- Exact wording of README sections (follow D-11 content scope)
- Whether to use a `rich` panel or plain `typer.echo` for the pre-flight summary block (plain is fine — matches `--parse-only` style)
- Test coverage approach for special char sanitization and placeholder import

</decisions>

<specifics>
## Specific Ideas

- The actual export has 2 empty notes (per STATE.md) — placeholder import will affect those 2 specifically
- The actual export has zero special-character collection names — but the feature must exist for correctness
- `--dry-run` should be runnable as a first step before any real import, giving a trustworthy pre-flight report
- "Safe to hand to someone who did not write it" is the guiding test — the README and dry-run output are the user-facing artifacts that must meet this bar

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing implementation (read before touching)
- `sync.py` lines 360–420 — `run_import` empty note block (lines 372–385 specifically — this is what changes for D-04/D-05)
- `sync.py` lines 520–562 — `run_dry_run` (needs pre-flight summary added at top, empty note line changed)
- `sync.py` lines 216–253 — `ensure_collection` (add sanitization per D-08/D-09/D-10)

### Prior context (carry-forward decisions)
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-03: `"skipped_empty"` status pattern (this phase changes behavior but not the key name for legacy entries)
- `.planning/phases/02-import-core/02-CONTEXT.md` — D-07: summary output format (post-import summary line already set)
- `.planning/STATE.md` §Verified Facts — 2 empty notes exist in actual export

### Requirements (Phase 4 scope)
- `.planning/REQUIREMENTS.md` — Phase 4 has no new v1 requirements; hardening validates existing ones
- `ROADMAP.md` §Phase 4 success criteria — the 4 observable truths this phase must make true

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_metadata_footer(created, modified)` — already handles None inputs, returns `""` — reuse as-is for placeholder notes
- `typer.echo()` — used throughout for all stdout output; use for pre-flight summary
- `save_state(state, state_path)` — atomic write, already used; no changes needed

### Established Patterns
- All stdout output via `typer.echo()` — no `print()` calls anywhere
- State key pattern: `rel_path` (relative to export dir) — must not change for idempotency
- Warning output: `typer.echo(f"Warning: ...")` — follow this for D-10 sanitization warning

### Integration Points
- Empty note change: `run_import` lines 372–385 — replace the `continue` block with placeholder import
- Dry-run change: `run_dry_run` — add pre-flight block before `for note_file in notes:` loop; change empty note line
- Special char: `ensure_collection` — sanitize before `"title":` in both API calls (lines 229 and 242)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-hardening*
*Context gathered: 2026-03-21*
