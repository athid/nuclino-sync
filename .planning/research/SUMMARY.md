# Project Research Summary

**Project:** nuclino-sync
**Domain:** One-shot CLI migration tool — Apple Notes export to Nuclino via REST API
**Researched:** 2026-03-21
**Confidence:** MEDIUM overall (Apple Notes export findings are HIGH — verified against actual data at `~/Desktop/NotesExport/`; Nuclino API findings are MEDIUM — training data only, live verification required before coding)

---

## Executive Summary

nuclino-sync is a Python CLI script for a one-time migration: walk an Apple Notes export directory, parse each Markdown file, and recreate the note hierarchy in Nuclino using its v0 REST API. The correct approach is a single-file script (`sync.py`) with a local `state.json` for idempotency, per-item error collection so partial failures never abort the run, and explicit cleaning of Apple Notes' export quirks before any API call is made. This is not a library and should not be engineered like one — a flat file is the right size until the pain of a single file is real.

The dominant constraint is **permanent metadata loss**. Nuclino's REST API does not accept `createdAt`, `updatedAt`, tags, or custom fields — these are server-set or UI-only. Every piece of Apple Notes frontmatter that has no Nuclino equivalent must be serialized into the note body as a human-readable block before import, and the user must be told about this before the first API call. Once the import runs and the user deletes their local export, the original dates are gone.

The dominant implementation risk is **silent data corruption from the export format itself**. The Apple Notes export tool emits 3–4x more `.md` files than there are actual notes (versioned snapshots), dates in frontmatter use a non-ISO human-readable format (`Thursday, 12 September 2024 at 07:24:45`) that PyYAML will not auto-parse, and 81% of notes repeat the title as plain text on the first line of the body. All three of these must be caught and cleaned in the parsing layer before any data reaches Nuclino. These are not edge cases — they affect the majority of the export.

---

## Key Findings

### Recommended Stack

The stack is deliberately minimal. Python 3.9+ is required (httpx 0.27 constraint). All libraries are well-established with stable APIs.

**Core technologies:**

- `httpx>=0.27` — REST API calls — async-ready, structured timeout config, composable transport for connection-level retries; preferred over `requests` for 429/backoff handling
- `tenacity>=8.3` — retry decorator with exponential backoff — declarative policy in one block; wire `Retry-After` header inspection via a custom `wait` callable; always set `reraise=True` or `RetryError` wraps the original exception and confuses log output
- `python-frontmatter>=1.1` — YAML frontmatter parsing — canonical library for this pattern; handles missing frontmatter, edge-case delimiters, unicode; do NOT roll your own with raw PyYAML + string splitting
- `typer>=0.12` — CLI flags and env var integration — type-hint-driven, zero boilerplate for 4–6 flags; pin `>=0.12` for correct `Optional` handling
- `rich>=13` — progress bars and styled output — replaces both `tqdm` and a separate logging library for terminal output; do NOT add `tqdm` alongside it
- `python-dotenv>=1.0` — `.env` file loading — soft dependency; drop it if minimizing deps and document that users must export env vars manually

**Critical gotcha for this project:** `python-frontmatter` returns `created` as a `datetime` object when the value is a YAML timestamp spec. Apple Notes does NOT use YAML timestamp format — the date arrives as a plain string. Do not call `.isoformat()` on it. Parse it explicitly with `strptime('%A, %d %B %Y at %H:%M:%S')`.

See `.planning/research/STACK.md` for full rationale and alternatives.

### Nuclino API: What Is and Isn't Supported

The Nuclino v0 REST API supports creating workspace collections and items with title and Markdown body. Authentication is API key only (`Authorization: ApiKey <key>`). The hierarchy maps cleanly: Apple Notes accounts become top-level collections, folders become nested collections, notes become items.

**Preservation map:**

| Apple Notes property | Nuclino equivalent | Preserved? |
|---------------------|-------------------|------------|
| Note title | Item `title` | YES — direct |
| Note body (Markdown) | Item `content` | YES — direct |
| Folder hierarchy | Collection nesting | YES — create collection per folder |
| Attachments (images, PDFs) | `POST /v0/files` | PARTIAL — attempt upload; log per-file failures |
| Created/modified dates | None (server-set) | PARTIAL — serialize into body footer block |
| Tags | None (UI-only, not in API) | PARTIAL — serialize into body footer block |
| Note order within folder | None (creation order only) | NO |
| Pinned/starred/color | None | NO |

**Hard constraints that cannot be worked around:**
- `createdAt` and `updatedAt` are read-only — set by the server at creation time; cannot be back-dated
- Tags exist in the Nuclino UI but are absent from the v0 REST API entirely
- `workspaceId` and `parentId` cannot be changed after item creation — no move operation via API
- Raw HTML in Markdown content will be stripped or displayed as plain text

**Rate limits:** Approximately 5 requests/second (MEDIUM confidence). The `Retry-After` header on 429 responses may or may not be present — training data is contradictory. Always use `.get('Retry-After', fallback)` and implement exponential backoff regardless.

**File upload:** `POST /v0/files` is the least-documented part of the API (LOW-MEDIUM confidence). Max file size is plan-dependent and not confirmed in training data. Log every upload failure per-attachment and never propagate it to the note level.

See `.planning/research/FEATURES.md` for full endpoint reference, response shapes, and markdown dialect support.

### Recommended Architecture

A single `sync.py` script with five functional boundaries: discover (walk directory tree, filter canonical files), parse (frontmatter extraction + body cleaning), ensure-collection (idempotent collection creation keyed on account+folder), create-item (POST with metadata footer, write state before attachments), upload-attachment (isolated per-file error handling). State lives in `state.json`, written atomically after every successful item creation using write-then-rename (`os.replace()`).

**Major components and responsibilities:**

1. `discover_notes(export_dir)` — walks the tree, returns only canonical `.md` files (filters versioned snapshots via stem regex), identifies attachment sibling directories; excludes accounts/folders with zero canonical files
2. `parse_note(path)` — loads frontmatter, applies Apple date parsing, strips duplicate title first line, applies NFC normalization, builds metadata footer for all unmapped fields; returns a `Note` dataclass
3. `ensure_collection(client, workspace_id, account, folder, state)` — creates Nuclino collection if `account/folder` key not in state; keyed on account+folder to prevent name collision across accounts with same-named folders
4. `create_item(client, collection_id, note)` — POSTs item with content including metadata footer; writes item ID to `state.json` IMMEDIATELY, before any attachment uploads
5. `upload_attachment(client, item_id, file_path)` — isolated `try/except`; attachment failure is a warning, never a note-level failure; checks file size before upload
6. `load_state` / `save_state` — atomic JSON read/write (`os.replace(tmp, path)`); returns empty state if file missing; `errors` list persisted alongside `collections` and `items` maps

**Data flow:**
```
CLI entry
  -> load_state
  -> discover_notes     (filter: canonical files only; skip empty account dirs)
  -> pre-flight summary (fields being serialized, note count, attachment count)
  -> for each note:
       parse_note            (clean body; build metadata footer)
       ensure_collection     (account/folder key -> collection_id)
       create_item           (-> item_id; write state BEFORE attachments)
       for each attachment:
           upload_attachment (isolated try/except; log warning on failure)
       save_state            (after each note, not at end)
  -> print summary: N imported, N skipped, N failed; point to state.json
```

See `.planning/research/ARCHITECTURE.md` for full component signatures and dataclass definitions.

### Top Pitfalls (verified against actual export)

All findings below are verified against the actual 133-file export at `~/Desktop/NotesExport/`. These are not speculative.

1. **Versioned snapshot files inflate note count 3–4x** — The export contains `Note.md` (canonical) plus `Note-1.md` through `Note-11.md` (snapshots). A naive `**/*.md` glob imports 133 files instead of 39. Filter: exclude any file whose stem ends in `-\d+`. This is the single most critical filter in the script — without it the import is silently 3–4x polluted.

2. **Title repeated as plain-text first line of body (81% of notes)** — Apple Notes writes the note title as the literal first line of the Markdown body, with no heading markup. Strip the first line when `lines[0].strip() == title`. Do not strip unconditionally — 19% of notes start with different content.

3. **Dates in frontmatter are not ISO 8601** — `created` and `modified` use format `Thursday, 12 September 2024 at 07:24:45`. PyYAML will NOT auto-parse this as a datetime (it becomes a plain string). `datetime.fromisoformat()` raises `ValueError`. Parse with `strptime('%A, %d %B %Y at %H:%M:%S')`, then serialize into the note body footer — the Nuclino API accepts no timestamp fields.

4. **Metadata loss is silent without explicit pre-flight communication** — `createdAt`, `modifiedAt`, and tags have no Nuclino API field. If not serialized into the note body, they are permanently lost. The script must: (a) prepend a metadata footer block to every note, (b) print a pre-flight summary before any API calls listing what will be serialized vs. lost, (c) log per-note when serialization occurs.

5. **Attachment failure must not create duplicate notes** — Write the item ID to `state.json` IMMEDIATELY after `POST /items` succeeds, before any attachment uploads. Give each attachment its own isolated `try/except`. If the outer loop catches a failure and re-runs, the note must not be re-created — only attachments retried.

6. **State file corruption on crash** — Writing `state.json` directly risks truncation on `Ctrl-C` or power loss. Use `os.replace(tmp, path)` — atomic on POSIX/macOS. A corrupt state file forces a full re-import.

**Additional pitfalls to handle:**
- Collection name collision across accounts — key state on `account/folder`, not `folder` alone; create a top-level collection per account
- Empty account directories — skip collection creation if zero canonical files exist in the folder
- Unicode NFC normalization — apply `unicodedata.normalize("NFC", title)` to all titles and collection names derived from the filesystem
- Empty-body notes (2 confirmed in export) — import with `*(empty note)*` placeholder; do not skip silently
- Do not consult `export-errors.log` as a skip list — notes listed as "User cancelled" ARE in the export; canonical `.md` file presence is the only truth

See `.planning/research/PITFALLS.md` for the full 15-pitfall list with code examples and phase-by-phase warning table.

---

## Implications for Roadmap

### Phase 1: Export Parsing and Validation (no API calls)

**Rationale:** The highest-impact bugs in this project come from the export format, not the API. The parsing layer must be correct before any data enters Nuclino — bad data that is imported cannot be easily bulk-undone. Building parsing first also enables a complete dry-run mode for user verification.

**Delivers:** A validated in-memory list of `Note` and `NoteFile` objects ready to import. A dry-run `--dry-run` report showing note count, what metadata will be serialized into bodies, what will be skipped, and attachment inventory.

**Implements:**
- `discover_notes()` with canonical-file filter (stem `-\d+` exclusion regex)
- `is_canonical()` filter function
- `parse_note()`: frontmatter loading, Apple date parsing (`strptime`), title-first-line strip, metadata footer construction, NFC normalization
- Empty-body detection with `*(empty note)*` placeholder
- Pre-flight summary output before first API call

**Must avoid:** Pitfalls 1 (versioned files), 2 (title repeat), 3 (date format), 4 (date parsing), 6 (silent metadata loss)

**Research flag:** No additional research needed. All findings verified against actual export data — HIGH confidence.

---

### Phase 2: State Management and Idempotency

**Rationale:** Before making any API calls, the state system must be in place. An import that cannot be safely resumed creates duplicates or orphans data on any interruption. State is the foundation every subsequent phase builds on.

**Delivers:** `load_state()` and `save_state()` with atomic write, `State` dataclass with `collections`, `items`, and `errors` maps, `account/folder` collection key scheme.

**Implements:**
- `State` dataclass (`collections: dict`, `items: dict`, `errors: list`)
- `load_state()` — empty state if file missing; `JSONDecodeError` handled gracefully with informative message
- `save_state()` — atomic write via `os.replace(tmp, path)`
- Collection key normalization to `account/folder` string

**Must avoid:** Pitfalls 8 (state corruption), 10 (collection name collision)

**Research flag:** Standard patterns — no additional research needed.

---

### Phase 3: Nuclino API Client and Collection Creation

**Rationale:** Establish the API client with retry/backoff before writing any content. Workspace and collection creation must succeed and be idempotent before items can be placed inside them.

**Delivers:** Working `httpx` client with `tenacity` retry decorator (respecting `Retry-After` when present), `ensure_collection()` that creates collections idempotently using state, workspace resolution by name to ID.

**Implements:**
- `httpx.Client` with `Authorization: ApiKey` header and structured timeout
- `tenacity` retry decorator for 429/500/503 with `Retry-After` fallback to exponential backoff
- `GET /v0/workspaces` to resolve workspace name to ID
- `ensure_collection()` with `account/folder` state key; skips folder if zero canonical files
- Base inter-request delay (~0.25s) to stay below documented rate limit

**Must avoid:** Pitfalls 9 (rate limiting), 10 (collection name collision), 11 (empty directories)

**Research flag:** Needs live API verification — confirm `Retry-After` header presence on a real 429 response; confirm `POST /v0/collections` required request fields; confirm whether `parentId` is mutable after creation.

---

### Phase 4: Item Creation with Metadata Serialization

**Rationale:** Core import logic. Items must carry the metadata footer, item IDs must be persisted to state before attachment uploads begin, and every creation response must be validated.

**Delivers:** `create_item()` that builds the full content string (metadata footer + cleaned body), POSTs to Nuclino, persists item ID to state immediately on success, validates API response.

**Implements:**
- `create_item()` — constructs content with metadata footer block, calls API, writes state before returning
- Per-note outer `try/except` loop that appends failures to `state.errors` and continues (never fail-fast)
- End-of-run summary: N imported, N skipped, N failed; reference `state.json` for details

**Must avoid:** Pitfalls 5 (metadata loss), 6 (silent loss without communication), 7 (attachment failure duplicating notes)

**Research flag:** Verify `POST /v0/items` required fields against live API. Test bare URL auto-linking in Nuclino content rendering before bulk import (Pitfall 15 — 48 bare URLs present in this export).

---

### Phase 5: Attachment Upload

**Rationale:** Attachment upload is the riskiest phase (least documented API surface, plan-dependent limits). It must be isolated from item creation so attachment failures cannot contaminate the core import.

**Delivers:** `upload_attachment()` with per-attachment `try/except`, attachment failure logged as warning, failed attachments recorded in state for retry, file-size pre-check with informative error message.

**Implements:**
- `upload_attachment()` — `multipart/form-data` POST to `POST /v0/files`, append returned URL to item content as `[filename](url)`
- Per-attachment isolated `try/except` — completely separate from note-level error handler
- File-size guard before upload (informative log message, not a generic HTTP 413 traceback)
- State tracking of failed attachments by item ID + filename for re-run retry

**Must avoid:** Pitfall 7 (attachment failure cascading to note level)

**Research flag:** Needs live API verification — file size limit per plan, which file types are accepted, whether returned file URL is stable/permanent. This is LOW-MEDIUM confidence; verify before implementing.

---

### Phase 6: Polish — Dry Run, Force Re-import, Edge Cases

**Rationale:** The core import works after Phase 5. This phase makes it safe for a non-technical user and handles verified edge cases from the actual export.

**Delivers:** `--dry-run` flag (full parse + pre-flight report, no API calls), `--force` flag (ignore state, re-import everything), `--verbose` flag (DEBUG log to stderr), `.env.example`, bare URL wrapping if Nuclino does not autolink.

**Implements:**
- Dry-run mode propagated through all phases
- `--force` flag that ignores existing state entries
- Mojibake defense (`fix_mojibake()`) as secondary guard for any versioned-file titles that pass the canonical filter
- `"!"` title edge case — always validate `POST /items` response body; log 4xx with source filename and title
- Bare URL wrapping as `<https://...>` if Phase 4 testing confirms Nuclino does not autolink
- `export-errors.log` intentionally NOT consulted — filesystem presence is the only truth

**Research flag:** Standard CLI polish patterns. No additional research needed.

---

### Phase Ordering Rationale

- Phases 1–2 have no API dependency and can be built and tested entirely offline against the actual export — low-risk, high-confidence starting point
- Phase 3 must come before Phases 4–5 because item creation requires a `parentId` (collection ID) that must already exist in state
- Phase 4 must write item IDs to state before Phase 5 runs — this is a correctness constraint, not a preference (Pitfall 7: attachment failure without prior state write creates duplicates on re-run)
- Phase 5 (attachments) is isolated last because it touches the least-documented API surface; its failures must not block the core import
- Phase 6 wraps all prior phases as polish; defer it until the core path is verified working

### Research Flags Summary

**Needs live API verification before coding:**
- Phase 3: `Retry-After` header presence on real 429; `POST /v0/collections` exact request shape; `parentId` mutability
- Phase 4: `POST /v0/items` required fields; bare URL auto-linking in content
- Phase 5: file upload size limit per plan; accepted MIME types; stability of returned file URL

**Standard patterns (skip additional research):**
- Phase 1: Verified against actual export data — HIGH confidence
- Phase 2: Atomic file writes and JSON state are well-documented stdlib patterns
- Phase 6: CLI polish with typer/rich follows documented patterns

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Libraries well-established; versions from training data — run `pip index versions <pkg>` before pinning |
| Nuclino API core CRUD | MEDIUM | Core endpoints consistent across training data; live verification still needed |
| Nuclino file upload | LOW-MEDIUM | Least documented endpoint; plan limits unknown; treat all upload behavior as unconfirmed |
| Apple Notes export format | HIGH | Verified against actual 133-file export; 39 canonical notes; all critical pitfalls confirmed |
| Architecture patterns | HIGH | Standard migration script patterns; idempotency via state file is well-established |
| Pitfalls 1–8 (export/parsing/state) | HIGH | Verified against actual data on 2026-03-21 |
| Pitfalls 9–15 (API/edge cases) | MEDIUM | Nuclino-specific behavior from training data only |

**Overall confidence:** MEDIUM — export-side work is solid; API-side needs one live verification session before bulk Phase 3+ implementation.

### Open Questions Requiring Live API Verification

Before coding Phases 3–5, make authenticated calls and inspect actual responses:

1. Does the 429 response include a `Retry-After` header? (Conflicting training data — inspect real response headers)
2. What is the exact request body for `POST /v0/collections`? (Confirm field names and required vs. optional)
3. Is `parentId` mutable after collection/item creation? (Affects whether notes can be moved between collections on re-run)
4. What is the file upload size limit per plan tier? (`POST /v0/files`)
5. Which MIME types are accepted by `POST /v0/files`? (PDF, HEIC, and arbitrary binaries are unconfirmed)
6. Is the URL returned by `POST /v0/files` stable and publicly accessible? (Needed for inline `![](url)` in Markdown)
7. Does Nuclino auto-link bare `https://` URLs in item content? (48 bare URLs in this export — Pitfall 15)
8. Does `POST /v0/items` accept an item with an empty string `content`? (2 empty-body notes in export)

**Mandatory pre-implementation URL:** https://help.nuclino.com/d3a29686-api

---

## Sources

### Primary (HIGH confidence)
- Direct inspection of `~/Desktop/NotesExport/` — 133 `.md` files, 2 accounts (`iCloud`, `anders@thib.se`), Python analysis scripts run 2026-03-21 — all Apple Notes export format findings
- Python 3.12 official docs (`pathlib.Path.walk()`) — fetched 2026-03-21
- tqdm README (pypi.org/project/tqdm) — fetched 2026-03-21
- POSIX spec (`os.replace()` atomicity guarantee)

### Secondary (MEDIUM confidence)
- Nuclino API v0 — training knowledge through August 2025; consistent across sources for core CRUD endpoints and authentication
- httpx 0.27, tenacity 8.3, python-frontmatter 1.1, typer 0.12, rich 13, python-dotenv 1.0 — training knowledge; verify current versions before pinning with `pip index versions <pkg>`
- Nuclino rate limits (5 req/s) — training knowledge; verify against https://help.nuclino.com/d3a29686-api

### Tertiary (LOW confidence — must verify before implementation)
- Nuclino file upload endpoint behavior (size limits, accepted types, URL stability) — not confirmed in training data
- `Retry-After` header on 429 responses — conflicting training data sources; inspect a real 429 response before relying on it

---

*Research completed: 2026-03-21*
*Ready for roadmap: yes*
