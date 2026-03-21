# Requirements: nuclino-sync

**Defined:** 2026-03-21
**Core Value:** Every note and its attachments land in the right Nuclino collection without manual copy-paste, preserving as much metadata as possible.

## v1 Requirements

### Export Parsing

- [ ] **PARSE-01**: Script filters versioned snapshot files and only processes canonical notes (filename pattern: files without version-suffix; ~39 canonical from 133 total in reference export)
- [ ] **PARSE-02**: Script strips duplicate title line from note body when first line matches frontmatter `title` field (affects ~81% of notes)
- [ ] **PARSE-03**: Script parses human-readable date format from frontmatter (`Thursday, 12 September 2024 at 07:24:45`) into a datetime object
- [ ] **PARSE-04**: Script extracts all frontmatter fields (`title`, `created`, `modified`) and note body from each `.md` file
- [ ] **PARSE-05**: Script discovers attachment files from sibling directory (`<Note Title>/`) alongside each note

### Nuclino API Client

- [ ] **API-01**: Script authenticates using `Authorization: ApiKey <key>` header; key read from `NUCLINO_API_KEY` env var
- [ ] **API-02**: Script self-throttles to ≤4 req/s and implements exponential backoff on 429 responses
- [ ] **API-03**: Script resolves target workspace by name or ID from env var or CLI flag
- [ ] **API-04**: Script creates collections for each Notes folder, using idempotent check-before-create (keyed on `account/folder` path)
- [ ] **API-05**: Script creates a Nuclino item per note with the cleaned markdown body
- [ ] **API-06**: Script serializes unmappable frontmatter fields (`created`, `modified`, and any tags if present) into a metadata block appended to item body — no silent loss

### Attachments

- [ ] **ATT-01**: Script uploads each attachment file and links it to the parent item
- [ ] **ATT-02**: Attachment failures are logged as warnings and do not fail the parent note import

### Configuration & UX

- [ ] **CFG-01**: Workspace target configurable via CLI flag (`--workspace`) or env var (`NUCLINO_WORKSPACE_ID` or name)
- [ ] **CFG-02**: Notes export directory configurable via CLI flag (`--export-dir`) or env var (`NOTES_EXPORT_DIR`), defaults to `~/Desktop/NotesExport`
- [ ] **CFG-03**: Dry-run mode (`--dry-run`) prints what would be imported without making API calls
- [ ] **CFG-04**: Each failed item is logged with note path and error message; script continues to next note

### State & Idempotency

- [ ] **STATE-01**: Script writes a state file tracking which collections and items have been created (keyed on source path)
- [ ] **STATE-02**: Re-running the script skips already-imported items (idempotent)
- [ ] **STATE-03**: State file is written atomically (tmp + rename) to survive interruption mid-run

## v2 Requirements

### Enhanced Metadata

- **META-01**: Support custom Nuclino fields if/when the API exposes them for tags and dates
- **META-02**: Option to not append metadata block (for users who prefer clean notes)

### Selective Import

- **SEL-01**: `--account` flag to import only one Apple Notes account
- **SEL-02**: `--folder` flag to import only one folder/collection

### Undo / Cleanup

- **UNDO-01**: `--delete` mode to remove all items/collections created by a previous run (using state file)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Ongoing sync / incremental updates | One-time migration; adds complexity not needed |
| Creating a new Nuclino workspace | Target workspace must already exist |
| Filtering by account in v1 | Not needed for user's single-export use case |
| Concurrent API calls | Rate limit (5 req/s) is bottleneck; parallelism buys nothing |
| Rich Markdown transformation | Nuclino accepts standard Markdown; no transformation needed |
| GUI / web interface | CLI is sufficient for a one-time migration |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PARSE-01 | Phase 1 | Pending |
| PARSE-02 | Phase 1 | Pending |
| PARSE-03 | Phase 1 | Pending |
| PARSE-04 | Phase 1 | Pending |
| PARSE-05 | Phase 1 | Pending |
| STATE-01 | Phase 1 | Pending |
| STATE-02 | Phase 1 | Pending |
| STATE-03 | Phase 1 | Pending |
| API-01 | Phase 2 | Pending |
| API-02 | Phase 2 | Pending |
| API-03 | Phase 2 | Pending |
| API-04 | Phase 2 | Pending |
| API-05 | Phase 2 | Pending |
| API-06 | Phase 2 | Pending |
| ATT-01 | Phase 3 | Pending |
| ATT-02 | Phase 3 | Pending |
| CFG-01 | Phase 3 | Pending |
| CFG-02 | Phase 3 | Pending |
| CFG-03 | Phase 3 | Pending |
| CFG-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-03-21 after initial definition*
