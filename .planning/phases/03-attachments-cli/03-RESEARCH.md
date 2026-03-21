# Phase 3: Attachments & CLI - Research

**Researched:** 2026-03-21
**Domain:** Nuclino file upload API, CLI dry-run mode, per-item error isolation
**Confidence:** HIGH for CLI/error-handling, LOW for attachment upload (API endpoint not publicly documented)

## Summary

Phase 3 adds three capabilities to the existing `sync.py`: (1) upload attachment files to Nuclino and link them to parent items, (2) a `--dry-run` flag that previews what would be imported without API calls, and (3) a post-run summary of failed notes printed to stdout.

**Critical finding: Nuclino's public API does NOT document a file upload endpoint.** The API docs list a `GET /v0/files/:id` endpoint for retrieving file metadata (including a time-limited download URL), but there is no documented `POST /v0/files` or multipart upload endpoint. Both the Python wrapper (PyNuclino) and the PHP wrapper (vdhicts/nuclino-api-client) confirm this gap -- they implement `get_file()` / `get_files()` but have no upload methods. The API is in "public preview" status, meaning upload support may exist undocumented or may be added later.

**Additional finding: The actual export at `~/Desktop/NotesExport/` contains zero attachment files.** No sibling directories exist alongside any of the 39 canonical notes. The `NoteFile.attachment_dir` field is structurally supported in the code but will always be `None` for this export. This means attachment upload code will be written but will have no real data to process in the current export.

**Primary recommendation:** Implement attachment upload as a best-effort feature using the most likely endpoint (`POST /v0/files` with `multipart/form-data`). If the endpoint does not exist, the per-attachment error isolation (ATT-02) will catch the failure gracefully. The `--dry-run` and error summary features are straightforward additions to the existing code.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** `--workspace` + `NUCLINO_WORKSPACE_ID` env var -- fully implemented in Phase 2
- **D-02:** `--export-dir` + `NOTES_EXPORT_DIR` env var -- already a `typer.Option` with envvar in `sync()`
- **D-03:** Per-note failure recording in `state.json` with `"status": "failed"` and `"error"` field -- already implemented in `run_import`
- **D-04:** Note-level error isolation via `except Exception` block in `run_import` -- already in place

### Claude's Discretion
- **Attachment linking format:** Use Nuclino's file attachment API endpoint (`POST /v0/files` or equivalent); after upload, append a reference block below the note body (outside the HTML comment footer) using whatever link format the API returns. If Nuclino's API returns a file URL or `![]()` embed syntax, use that. If the API only returns an item ID, append a plain-text reference: `Attachments: filename (id: <id>)`.
- **Attachment failure handling:** Each attachment failure is caught individually -- the parent note import proceeds as `"status": "imported"` regardless. Attachment failures are stored in `state.json` under the note's key as `"attachment_failures": [{"file": "name.jpg", "error": "..."}]` so they're recoverable.
- **Dry-run output format:** `--dry-run` should print a per-note plan: note title, folder, and whether attachments exist, without making any API calls. End with a summary count. Format should match the existing `--parse-only` style (plain text, no rich progress bar).
- **Failed item summary at run end:** After the rich progress bar completes, if any notes failed, print their paths and errors to stdout after the summary line: `"Failed notes:\n  - <path>: <error>\n"` -- this surfaces failures immediately without requiring the user to open state.json.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ATT-01 | Script uploads each attachment file and links it to the parent item | **BLOCKED (LOW confidence):** No documented upload endpoint. Best-effort implementation using `POST /v0/files` with `multipart/form-data`. If endpoint returns a file URL, append `[filename](url)` to item content via `PUT /v0/items/:id`. If endpoint fails with 404, log warning and skip all attachments gracefully. |
| ATT-02 | Attachment failures are logged as warnings and do not fail the parent note import | Fully supported by existing error isolation pattern. Each attachment upload is wrapped in its own try/except. Failures stored as `"attachment_failures"` list in state.json. Parent note stays `"status": "imported"`. |
| CFG-01 | Workspace target configurable via CLI flag or env var | **Already implemented** in Phase 2. `--workspace` flag with `envvar="NUCLINO_WORKSPACE_ID"` exists in `sync()`. No work needed. |
| CFG-02 | Notes export directory configurable via CLI flag or env var | **Already implemented** in Phase 2. `--export-dir` with `envvar="NOTES_EXPORT_DIR"` exists. No work needed. |
| CFG-03 | Dry-run mode prints what would be imported without making API calls | Add `--dry-run` flag to `sync()`. When set, call `run_dry_run()` which iterates notes and prints title/folder/attachment info. No API key required. |
| CFG-04 | Each failed item is logged with note path and error message; script continues | **Partially implemented** -- failure recording in state.json exists (D-03, D-04). Phase 3 adds: (a) post-run stdout summary of failed notes, (b) attachment-level failure recording. |
</phase_requirements>

## Standard Stack

### Core (no new dependencies)
No new dependencies are needed for Phase 3. All required libraries are already installed from Phase 2.

| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| `httpx` | `0.28.1` | HTTP client (file upload via multipart) | Yes (Phase 2) |
| `tenacity` | `9.1.4` | Retry on 429/5xx for upload attempts | Yes (Phase 2) |
| `typer` | `>=0.12` | CLI `--dry-run` flag | Yes (Phase 1) |
| `rich` | `>=13` | Progress bar (already in use) | Yes (Phase 1) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `POST /v0/files` (unverified) | Skip attachments entirely | Loses ATT-01 but avoids unknown API surface; CONTEXT.md explicitly wants attachment upload attempted |
| Multipart upload via httpx | External image hosting + markdown links | Would bypass Nuclino storage; fragile if external host goes down |

## Architecture Patterns

### Nuclino Files API (partially verified)

**Verified (HIGH confidence):**
- `GET /v0/files/:id` returns `{"object": "file", "id": "uuid", "itemId": "uuid", "fileName": "name", "createdAt": "iso", "createdUserId": "uuid", "download": {"url": "https://...", "expiresAt": "iso"}}`
- File URLs in Nuclino content use format: `https://files.nuclino.com/files/<uuid>/<filename>`
- Files are embedded in item content as standard Markdown links: `[Example.txt](https://files.nuclino.com/files/<uuid>/Example.txt)`
- Images use Markdown image syntax: `![screenshot.png](https://files.nuclino.com/files/<uuid>/screenshot.png)`
- The `contentMeta` object on items includes `fileIds: Array[uuid]` listing all files in the content

**Unverified (LOW confidence) -- best-effort implementation:**
- Upload endpoint is likely `POST /v0/files` with `multipart/form-data` and an `itemId` field linking to the parent item
- The response likely returns a file object with `id` and a URL on `files.nuclino.com`
- After upload, the item content must be updated via `PUT /v0/items/:id` to include the Markdown link

### Recommended Implementation Structure

```
sync.py additions:
  # New function
  upload_attachments(client, item_id, attachment_dir, state_entry, state, state_path) -> None

  # New function
  run_dry_run(export_dir) -> None

  # Modified function
  run_import() -- add attachment upload after item creation, add post-run failure summary

  # Modified CLI
  sync() -- add --dry-run flag
```

### Pattern 1: Attachment Upload with Per-File Error Isolation
**What:** Upload each attachment individually; catch failures per-file, not per-note.
**When to use:** After item creation succeeds and state is saved.

```python
def upload_attachments(
    client: httpx.Client,
    item_id: str,
    attachment_dir: Path,
    state_entry: dict,
    state: dict,
    state_path: Path,
) -> None:
    """Upload attachments for an item. Failures are isolated per-file."""
    attachment_failures = []
    attachment_links = []

    for file_path in sorted(attachment_dir.iterdir()):
        if not file_path.is_file():
            continue
        try:
            # Attempt multipart upload
            with open(file_path, "rb") as f:
                _throttle()
                resp = client.post(
                    f"{NUCLINO_BASE}/v0/files",
                    data={"itemId": item_id},
                    files={"file": (file_path.name, f)},
                    headers={"Content-Type": None},  # let httpx set multipart boundary
                )
                resp.raise_for_status()
                file_data = resp.json()["data"]

            # Build markdown link from response
            download_url = file_data.get("download", {}).get("url", "")
            file_id = file_data.get("id", "")
            file_name = file_path.name

            # Use files.nuclino.com URL pattern for permanent link
            permanent_url = f"https://files.nuclino.com/files/{file_id}/{file_name}"

            # Image vs file link
            if file_name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                attachment_links.append(f"![{file_name}]({permanent_url})")
            else:
                attachment_links.append(f"[{file_name}]({permanent_url})")

        except Exception as e:
            attachment_failures.append({"file": file_path.name, "error": str(e)})

    # Update item content with attachment links if any succeeded
    if attachment_links:
        # Fetch current content, append links, update
        item_data = api_request(client, "GET", f"/v0/items/{item_id}")
        current_content = item_data.get("content", "")
        links_block = "\n\n" + "\n".join(attachment_links)
        api_request(client, "PUT", f"/v0/items/{item_id}", json={
            "content": current_content + links_block,
        })

    # Record failures in state
    if attachment_failures:
        state_entry["attachment_failures"] = attachment_failures
        save_state(state, state_path)
```

### Pattern 2: Dry-Run Output
**What:** Print what would be imported without any API calls.
**When to use:** When `--dry-run` flag is set.

```python
def run_dry_run(export_dir: Path) -> None:
    """Preview what would be imported, without making API calls."""
    notes, versioned_count = discover_notes(export_dir)
    state_path = export_dir / "nuclino-state.json"
    state = load_state(state_path)

    would_import = 0
    would_skip = 0
    has_attachments = 0

    for note_file in notes:
        rel_path = str(note_file.md_path.relative_to(export_dir))

        # Check if already imported
        if rel_path in state["items"] and state["items"][rel_path].get("status") == "imported":
            would_skip += 1
            typer.echo(f"  skip (already imported): {note_file.title}")
            continue

        parsed = parse_note(note_file)
        body = clean_body(parsed.body, parsed.title)

        if not body.strip():
            would_skip += 1
            typer.echo(f"  skip (empty): {note_file.title}")
            continue

        att_info = ""
        if note_file.attachment_dir:
            att_count = sum(1 for f in note_file.attachment_dir.iterdir() if f.is_file())
            att_info = f" [{att_count} attachments]"
            has_attachments += 1

        typer.echo(f"  import: {note_file.account}/{note_file.folder}/{note_file.title}{att_info}")
        would_import += 1

    typer.echo(
        f"\nDry run: {would_import} notes to import, "
        f"{would_skip} to skip, "
        f"{has_attachments} with attachments. "
        f"{versioned_count} versioned snapshots ignored."
    )
```

### Pattern 3: Post-Run Failure Summary
**What:** After progress bar completes, print failed notes to stdout.
**When to use:** At end of `run_import()`, after the summary line.

```python
# At end of run_import(), after the existing summary echo:
failed_items = [
    (path, entry.get("error", "unknown"))
    for path, entry in state["items"].items()
    if entry.get("status") == "failed"
]
if failed_items:
    typer.echo("Failed notes:")
    for path, error in failed_items:
        typer.echo(f"  - {path}: {error}")
```

### Anti-Patterns to Avoid
- **Aborting the entire import on attachment failure:** ATT-02 explicitly requires attachment failures to be non-fatal. Each attachment must have its own try/except.
- **Setting Content-Type: application/json for multipart upload:** When sending files, let httpx auto-set the `Content-Type` with the multipart boundary. Override the default JSON content-type header.
- **Uploading attachments before saving item state:** The state MUST be saved after item creation but BEFORE attachment upload (Pitfall 5 from Phase 2). This prevents duplicate items on re-run if attachment upload crashes.
- **Requiring API key for dry-run:** `--dry-run` must work without `NUCLINO_API_KEY` set, since it makes no API calls.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multipart file upload | Manual boundary encoding | `httpx` `files=` parameter | Boundary generation, encoding, content-type header all handled |
| CLI flag with env var fallback | Custom `os.environ.get()` chain | `typer.Option(envvar="...")` | Consistent with existing pattern; handles precedence correctly |
| Progress bar suppression in dry-run | Conditional progress bar wrapper | Separate `run_dry_run()` function | Cleaner than threading a flag through the import loop |

## Common Pitfalls

### Pitfall 1: File Upload Endpoint May Not Exist
**What goes wrong:** `POST /v0/files` returns 404 or 405 because the endpoint is not part of the public API.
**Why it happens:** The Nuclino API is in "public preview." Only `GET /v0/files/:id` is documented. No third-party wrapper implements file upload.
**How to avoid:** Wrap the entire attachment upload path in a try/except. If the first upload attempt returns 404/405, log a warning like "File upload not supported by Nuclino API" and skip all remaining attachments for the run (not just for this note). Store this as a flag to avoid repeated 404s.
**Warning signs:** 404 on first `POST /v0/files` call.

### Pitfall 2: Content-Type Header Conflict for Multipart Upload
**What goes wrong:** The httpx client is configured with `Content-Type: application/json` in default headers (from `make_nuclino_client`). This conflicts with multipart form data uploads.
**Why it happens:** `make_nuclino_client()` sets `"Content-Type": "application/json"` as a default header.
**How to avoid:** For the upload request, explicitly set `headers={"Content-Type": None}` to remove the default and let httpx auto-generate the correct `multipart/form-data; boundary=...` header. Alternatively, remove the default Content-Type from the client and set it per-request for JSON calls.
**Warning signs:** Server rejects multipart upload with a parsing error.

### Pitfall 3: State Must Be Saved Before Attachments (carry-forward from Phase 2)
**What goes wrong:** Item is created, attachment upload fails, exception propagates before state is saved, re-run creates duplicate.
**Why it happens:** Attachment upload happens inside the same try/except as item creation.
**How to avoid:** The existing code already saves state immediately after `POST /v0/items`. Attachment upload must be a SEPARATE try/except block AFTER the state save. This is already the correct structure per CONTEXT.md.
**Warning signs:** Duplicate items appearing after re-runs.

### Pitfall 4: Dry-Run Still Requires API Key
**What goes wrong:** User runs `--dry-run` without setting `NUCLINO_API_KEY` and gets an error.
**Why it happens:** The existing `sync()` function validates the API key before dispatching to any mode.
**How to avoid:** Check for `--dry-run` BEFORE the API key validation. If dry-run is set, call `run_dry_run()` and return immediately, same pattern as `--parse-only`.
**Warning signs:** "Error: NUCLINO_API_KEY environment variable is required" when running with `--dry-run`.

### Pitfall 5: PUT /v0/items/:id Requires Content Fetch First
**What goes wrong:** Appending attachment links to item content overwrites the existing content because you only have the local content, not what Nuclino has stored.
**Why it happens:** The `POST /v0/items` response does not include `content`. To append links, you must first `GET /v0/items/:id` to fetch current content, then `PUT` with the combined content.
**How to avoid:** After all attachments for an item are uploaded, do a GET-then-PUT to append the links block. This costs 2 extra API calls per note with attachments.
**Warning signs:** Notes losing their body content after attachment linking.

## Code Examples

### CLI Extension for --dry-run

```python
@app.command()
def sync(
    export_dir: Path = typer.Option(
        Path.home() / "Desktop" / "NotesExport",
        help="Path to Apple Notes export directory",
        envvar="NOTES_EXPORT_DIR",
    ),
    parse_only: bool = typer.Option(
        False, "--parse-only",
        help="Parse export and print summary without importing",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Preview what would be imported without making API calls",
    ),
    workspace: str = typer.Option(
        None, "--workspace",
        envvar="NUCLINO_WORKSPACE_ID",
        help="Nuclino workspace name or ID",
    ),
) -> None:
    """Sync Apple Notes export to Nuclino."""
    if parse_only:
        run_parse_only(export_dir)
        return

    if dry_run:
        run_dry_run(export_dir)
        return

    # ... existing API key and workspace validation ...
```

### Attachment Upload Integration in run_import

```python
# Inside run_import(), AFTER state is saved for a successfully created item:
# (This is a separate try/except from the item creation)

# Upload attachments if any exist
if note_file.attachment_dir:
    try:
        upload_attachments(
            client, data["id"],
            note_file.attachment_dir,
            state["items"][rel_path],
            state, state_path,
        )
    except Exception as e:
        # Catch-all for unexpected attachment errors
        state["items"][rel_path].setdefault("attachment_failures", []).append(
            {"file": "*", "error": f"Unexpected: {str(e)}"}
        )
        save_state(state, state_path)
```

### Multipart Upload with httpx (Content-Type override)

```python
# The client has Content-Type: application/json as default.
# For multipart, we must override it.
with open(file_path, "rb") as f:
    resp = client.post(
        f"{NUCLINO_BASE}/v0/files",
        data={"itemId": item_id},
        files={"file": (file_path.name, f)},
        headers={"Content-Type": None},  # removes default JSON content-type
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Assume file upload exists | Only `GET /v0/files/:id` documented | Verified 2026-03-21 | Must implement upload as best-effort; may fail with 404 |
| Fail entire import on attachment error | Per-attachment error isolation | ATT-02 requirement | Each attachment failure is independent |
| All CLI modes require API key | `--parse-only` and `--dry-run` work offline | Phase 3 | Dry-run must bypass API key check |

## Open Questions

1. **Does `POST /v0/files` exist?**
   - What we know: `GET /v0/files/:id` exists and is documented. File URLs use `files.nuclino.com`. The item `contentMeta` includes `fileIds`. No documented upload endpoint. No third-party wrapper implements upload.
   - What's unclear: Whether the endpoint exists but is undocumented, or genuinely does not exist in the API.
   - Recommendation: Implement the upload attempt with the most likely endpoint signature. The per-attachment error handling (ATT-02) ensures graceful degradation if it fails. If the first upload returns 404/405, set a flag to skip all remaining attachment uploads for the run and log a single clear warning.

2. **What request format does file upload require?**
   - What we know: Standard REST APIs typically use `multipart/form-data` with a `file` field and metadata fields like `itemId`.
   - What's unclear: Exact field names, whether `itemId` is required or whether files are uploaded independently then linked.
   - Recommendation: Try `multipart/form-data` with `itemId` field first. If that fails, try without `itemId`. The error message will guide debugging.

3. **How should uploaded files be linked in item content?**
   - What we know: Existing Nuclino content uses `[filename](https://files.nuclino.com/files/<uuid>/filename)` for files and `![filename](url)` for images.
   - What's unclear: Whether the upload response returns the permanent `files.nuclino.com` URL directly, or just the file ID.
   - Recommendation: If response includes a URL, use it directly. If only ID is returned, construct the URL as `https://files.nuclino.com/files/{id}/{filename}`. If neither works, fall back to plain text: `Attachment: filename (id: <id>)`.

4. **Current export has zero attachments**
   - What we know: The export at `~/Desktop/NotesExport/` has 39 canonical notes, none with sibling attachment directories. `NoteFile.attachment_dir` will be `None` for all notes.
   - What's unclear: Whether the user expects to add attachments later or if this feature is purely precautionary.
   - Recommendation: Implement the feature fully since it is a v1 requirement. The code path simply won't execute for the current export. This is fine -- the dry-run output will show "0 with attachments" confirming correctness.

## Sources

### Primary (HIGH confidence)
- [Nuclino Files API](https://help.nuclino.com/9a737add-files) -- `GET /v0/files/:id` response format, download URL structure
- [Nuclino Item Content Format](https://help.nuclino.com/4adea846-item-content-format) -- file/image Markdown syntax, `files.nuclino.com` URL pattern, `contentMeta.fileIds`
- [Nuclino Items and Collections](https://help.nuclino.com/fa38d15f-items-and-collections) -- `PUT /v0/items/:id` for content updates
- [Nuclino API Introduction](https://help.nuclino.com/04bc3b92-introduction) -- "public preview" status
- Phase 2 Research (`.planning/phases/02-import-core/02-RESEARCH.md`) -- API auth, rate limiting, response format (all carry-forward)
- Existing `sync.py` source code -- verified current implementation of `run_import`, `sync()` CLI, state management

### Secondary (MEDIUM confidence)
- [PyNuclino on GitHub](https://github.com/Vanderhoof/PyNuclino) -- confirms no upload method exists; only `get_file()` / `get_files()` implemented
- [vdhicts/nuclino-api-client](https://github.com/vdhicts/nuclino-api-client) -- PHP client also lacks file upload support

### Tertiary (LOW confidence)
- `POST /v0/files` endpoint signature -- inferred from REST conventions and the existing `GET /v0/files/:id` endpoint; NOT verified against official docs or any working implementation
- `multipart/form-data` with `itemId` field -- standard REST pattern; exact field names unverified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all libraries already installed and verified
- Architecture (CLI/dry-run/error handling): HIGH -- straightforward additions to existing patterns
- Architecture (attachment upload): LOW -- upload endpoint is undocumented; implementation is best-effort
- Pitfalls: HIGH -- identified 5 concrete pitfalls with mitigations

**Research date:** 2026-03-21
**Valid until:** 2026-04-07 (short validity due to LOW confidence on attachment upload; re-verify if Nuclino API docs update)
