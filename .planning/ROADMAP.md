# Roadmap: nuclino-sync

**Milestone:** v1.0 — Working Import
**Granularity:** Coarse
**Coverage:** 20/20 v1 requirements mapped
**Created:** 2026-03-21

---

## Phases

- [ ] **Phase 1: Foundation** — Parse Apple Notes export into validated in-memory notes; state management for idempotency
- [x] **Phase 2: Import Core** — Nuclino API client with backoff; workspace/collection resolution; note item creation with metadata footer (completed 2026-03-21)
- [ ] **Phase 3: Attachments & CLI** — File upload to Nuclino; CLI flags and env var config; per-item error isolation
- [ ] **Phase 4: Hardening** — Dry-run output polish; edge case handling; README with usage examples

---

## Phase Details

### Phase 1: Foundation

**Goal**: The export directory can be fully parsed offline into validated notes with no data loss, and re-runs are safe via atomic state tracking.

**Depends on**: Nothing

**Requirements**: PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05, STATE-01, STATE-02, STATE-03

**Success Criteria** (what must be TRUE):
1. Running the script against the 133-file export discovers exactly 39 canonical notes and zero versioned snapshots
2. Every note's `created` and `modified` dates are available as Python `datetime` objects, not raw strings
3. Notes where the body first line matches the title have that line stripped; all other notes are unchanged
4. Interrupting the script mid-run and re-running it skips already-imported items without creating duplicates
5. A crash or `Ctrl-C` during a state write leaves the previous valid `state.json` intact (no truncation)

**Plans:** 2 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold + sync.py with all parsing, state, and CLI functions
- [x] 01-02-PLAN.md — Pytest test suite for parsing and state management

---

### Phase 2: Import Core

**Goal**: Notes reach Nuclino — in the correct collection, with full content and a metadata footer preserving dates and tags — and the API is handled safely under rate limits.

**Depends on**: Phase 1

**Requirements**: API-01, API-02, API-03, API-04, API-05, API-06

**Success Criteria** (what must be TRUE):
1. Script authenticates via `NUCLINO_API_KEY` env var and creates items without a 401 error
2. Each Notes folder appears as a Nuclino collection inside the target workspace; running the script twice does not create duplicate collections
3. Each note appears as a Nuclino item inside its folder's collection, with the cleaned Markdown body
4. Every item body includes a metadata footer block containing `created`, `modified`, and any tags — no frontmatter field is silently discarded
5. When the API returns 429, the script backs off and retries rather than crashing or skipping the note

**Plans**: TBD

---

### Phase 3: Attachments & CLI

**Goal**: Attachments are uploaded and linked to their parent items; all configuration is expressible via CLI flags or env vars; a single attachment or note failure never aborts the run.

**Depends on**: Phase 2

**Requirements**: ATT-01, ATT-02, CFG-01, CFG-02, CFG-03, CFG-04

**Success Criteria** (what must be TRUE):
1. Attachment files from sibling directories are uploaded to Nuclino and linked in the parent item's content
2. When an attachment upload fails, the note import is marked successful and the failure is logged as a warning — the script continues
3. `--workspace`, `--export-dir`, and `--dry-run` flags are accepted; each has a corresponding env var fallback
4. Every failed note is logged with its source path and error message; the script processes all remaining notes after any single failure

**Plans**: TBD

---

### Phase 4: Hardening

**Goal**: The script is safe to hand to someone who did not write it — dry-run output is informative, known edge cases from the actual export are handled, and the README explains exactly how to run an import.

**Depends on**: Phase 3

**Requirements**: *(no new v1 requirements — this phase validates and hardens Phases 1–3)*

**Success Criteria** (what must be TRUE):
1. `--dry-run` prints a pre-flight summary: note count, attachment count, what metadata will be serialized into bodies, and what will be lost — before making any API calls
2. Notes with empty bodies are imported with a `*(empty note)*` placeholder rather than being skipped or crashing
3. Collection names containing special characters (e.g. `/`, `&`) are handled without a crash or a malformed API request
4. The README contains a minimal working example: install, set env vars, run, verify output

**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/2 | Planned | - |
| 2. Import Core | 0/? | Complete    | 2026-03-21 |
| 3. Attachments & CLI | 0/? | Not started | - |
| 4. Hardening | 0/? | Not started | - |

---

## Coverage Map

| Requirement | Phase | Description |
|-------------|-------|-------------|
| PARSE-01 | 1 | Filter versioned snapshots; process only canonical notes |
| PARSE-02 | 1 | Strip duplicate title line from body when it matches frontmatter title |
| PARSE-03 | 1 | Parse Apple date format into datetime object |
| PARSE-04 | 1 | Extract all frontmatter fields and note body |
| PARSE-05 | 1 | Discover attachments from sibling directory |
| STATE-01 | 1 | Write state file tracking created collections and items |
| STATE-02 | 1 | Skip already-imported items on re-run |
| STATE-03 | 1 | Atomic state file writes (tmp + rename) |
| API-01 | 2 | Authenticate via Authorization: ApiKey header from env var |
| API-02 | 2 | Self-throttle to ≤4 req/s with exponential backoff on 429 |
| API-03 | 2 | Resolve target workspace by name or ID |
| API-04 | 2 | Idempotent collection creation keyed on account/folder path |
| API-05 | 2 | Create Nuclino item per note with cleaned Markdown body |
| API-06 | 2 | Serialize unmappable frontmatter into metadata footer block |
| ATT-01 | 3 | Upload each attachment and link to parent item |
| ATT-02 | 3 | Attachment failures logged as warnings; do not fail parent note |
| CFG-01 | 3 | --workspace flag and NUCLINO_WORKSPACE_ID env var |
| CFG-02 | 3 | --export-dir flag and NOTES_EXPORT_DIR env var |
| CFG-03 | 3 | --dry-run flag (no API calls) |
| CFG-04 | 3 | Failed items logged with path and error; script continues |

**Total v1 requirements:** 20
**Mapped:** 20
**Unmapped:** 0

---

## Research Flags

The following items require live Nuclino API verification before Phase 2 implementation:

- Does the 429 response include a `Retry-After` header?
- Exact request body for `POST /v0/collections` (field names, required vs. optional)
- Is `parentId` mutable after collection/item creation?
- `POST /v0/items` required fields; does it accept empty string `content`?
- Does Nuclino auto-link bare `https://` URLs in item content? (48 bare URLs in this export)
- `POST /v0/files` size limit per plan, accepted MIME types, and URL stability

Reference: https://help.nuclino.com/d3a29686-api

---

*Roadmap created: 2026-03-21*
*Last updated: 2026-03-21 after Phase 1 planning*
