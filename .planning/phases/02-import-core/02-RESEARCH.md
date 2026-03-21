# Phase 2: Import Core - Research

**Researched:** 2026-03-21
**Domain:** Nuclino REST API integration -- authentication, workspace resolution, collection/item creation, rate limiting, metadata serialization
**Confidence:** HIGH -- API documentation verified against live official docs (help.nuclino.com), correcting several inaccuracies in earlier training-data-based research

## Summary

Phase 2 wires the Phase 1 parse functions to the Nuclino API. The script must authenticate, resolve a workspace, create collections idempotently, create items with cleaned Markdown and a metadata footer, and handle rate limits gracefully. The existing `sync.py` already has `discover_notes()`, `parse_note()`, `clean_body()`, state management, and a `typer` CLI -- Phase 2 adds a `run_import()` function and new CLI parameters (`--workspace`, API key from env).

**Critical corrections from live API docs** (vs earlier training-data research):
1. **Auth header is `Authorization: YOUR_API_KEY`** -- no `ApiKey` or `Bearer` prefix, just the raw key
2. **Rate limit is 150 requests/minute** (~2.5 req/s), not 5 req/s as previously assumed
3. **Collections and items share a single endpoint** `POST /v0/items` with `"object": "collection"` or `"object": "item"` -- there is no separate `/v0/collections` endpoint
4. **Response envelope uses `"status": "success"/"fail"/"error"`** -- not `"status": "ok"` as assumed
5. **Base URL is `https://api.nuclino.com`** -- the `/v0/` prefix is part of endpoint paths, not the base URL
6. **`workspaceId` and `parentId` are mutually exclusive** on POST -- set one or the other, not both

**Primary recommendation:** Use `httpx` with a simple sleep-based throttle at ~0.35s between requests (staying safely under 150/min), plus `tenacity` retry on 429/5xx. Build the metadata footer as an HTML comment block per D-01/D-02. Use `rich.progress` for the import loop per D-05/D-06.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Metadata is appended as an HTML comment block -- invisible in Nuclino's rendered view
- **D-02:** Format: `<!-- nuclino-sync\ncreated: 2024-09-12T07:24:45\nmodified: 2024-09-12T09:00:00\n-->`
- **D-03:** Block is only appended when data exists -- omitted entirely if both `created` and `modified` are `None`
- **D-04:** ISO 8601 format for timestamps (already available from Phase 1's `datetime` objects via `.isoformat()`)
- **D-05:** Display a `rich` progress bar during import -- shows N/total notes processed
- **D-06:** Progress bar replaces per-note line output -- no per-note stdout during import
- **D-07:** After import completes, print summary counts only: `"Imported N notes. F failed. See nuclino-state.json for details."`
- **D-08:** Failures are recorded in `state.json` with `"status": "failed"` and error message -- not printed to stdout during the run
- **D-09:** `--workspace` flag (or `NUCLINO_WORKSPACE_ID` env var) is required -- hard error if omitted
- **D-10:** If the provided name/ID doesn't match any workspace, list available workspaces and prompt interactively
- **D-11:** Workspace can be specified by name (case-insensitive match) or by ID (exact match)

### Claude's Discretion
- httpx vs requests for HTTP client (research recommendation: httpx)
- Exact retry/backoff implementation (tenacity or manual loop)
- Collection creation endpoint details (now verified -- see Standard Stack)
- Item creation request body structure (now verified -- see Architecture Patterns)
- Whether to store workspace ID vs name in state.json

### Deferred Ideas (OUT OF SCOPE)
- Bare URL wrapping (`<https://...>`) -- pending live API verification of auto-linking behavior (STATE.md)
- `--dry-run` flag -- Phase 3 (CFG-03)
- Per-note verbose output (`--verbose`) -- Phase 4 polish
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | Script authenticates using `Authorization: ApiKey <key>` header; key read from `NUCLINO_API_KEY` env var | **CORRECTED:** Header format is `Authorization: YOUR_API_KEY` (no prefix). Verified against official docs. Use `typer.Option(envvar="NUCLINO_API_KEY")` for the key. |
| API-02 | Script self-throttles to <=4 req/s and implements exponential backoff on 429 responses | Rate limit is 150 req/min (~2.5 req/s). Self-throttle with ~0.35s sleep between requests. Use tenacity for 429 backoff. |
| API-03 | Script resolves target workspace by name or ID from env var or CLI flag | `GET /v0/workspaces` returns list; match by `name` (case-insensitive) or `id` (exact). Interactive prompt if no match (D-10). |
| API-04 | Script creates collections for each Notes folder, using idempotent check-before-create (keyed on `account/folder` path) | `POST /v0/items` with `"object": "collection"`, `parentId` set to workspace ID or parent collection ID. State keyed on `account/folder`. |
| API-05 | Script creates a Nuclino item per note with the cleaned markdown body | `POST /v0/items` with `"object": "item"` (default), `parentId` = collection ID, `title`, `content`. Write state IMMEDIATELY after success. |
| API-06 | Script serializes unmappable frontmatter fields into a metadata block appended to item body | HTML comment footer per D-01/D-02/D-03/D-04. Only `created` and `modified` exist in the actual export (0 tags found). |
</phase_requirements>

## Standard Stack

### Core (new dependencies for Phase 2)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | `0.28.1` | HTTP client for Nuclino API | Structured timeout config, composable transports, cleaner than requests for retry layering |
| `tenacity` | `9.1.4` | Retry with exponential backoff | Declarative retry policy; handles 429 + 5xx; `reraise=True` for clean error output |

### Already installed (Phase 1)
| Library | Version | Purpose |
|---------|---------|---------|
| `python-frontmatter` | `>=1.1` | YAML frontmatter parsing |
| `typer` | `>=0.12` | CLI framework |
| `rich` | `>=13` | Progress bars and styled output |

### Discretion Recommendation: httpx over requests

Use `httpx`. Rationale:
- `httpx.Client` provides structured `Timeout(connect=5, read=30)` -- better than requests' single float
- Transport-level retries via `HTTPTransport(retries=2)` for network errors, separate from semantic retries (429/5xx) via tenacity
- Already recommended in STACK.md research; no reason to deviate

### Discretion Recommendation: tenacity over manual loop

Use `tenacity`. Rationale:
- Single decorator expresses the full retry policy
- Custom `wait` callable can inspect `Retry-After` header if present
- `reraise=True` ensures the original exception surfaces in logs, not a wrapped `RetryError`

### Discretion Recommendation: Store workspace ID in state.json

Store `workspace_id` (UUID) in state, not workspace name. Rationale:
- Names can change; IDs are immutable
- All subsequent API calls use the ID
- Add to state root: `{"version": 1, "workspace_id": "uuid-here", "items": {...}}`

**Installation:**
```bash
pip install httpx>=0.28 tenacity>=9.0
```

Or add to `pyproject.toml`:
```toml
dependencies = [
    "python-frontmatter>=1.1",
    "typer>=0.12",
    "rich>=13",
    "httpx>=0.28",
    "tenacity>=9.0",
]
```

## Architecture Patterns

### Nuclino API Surface (verified against official docs 2026-03-21)

**Base URL:** `https://api.nuclino.com`

**Authentication:**
```
Authorization: YOUR_API_KEY
```
No prefix. The raw API key goes directly in the header value.

**Response envelope:**
```json
// Success (200)
{"status": "success", "data": {...}}

// Client error (4xx)
{"status": "fail", "message": "..."}

// Server error (5xx)
{"status": "error", "message": "..."}
```

**Rate limit:** 150 requests/minute per API key. Returns 429 on excess. No confirmed `Retry-After` header.

### Key Endpoints

#### List Workspaces
```
GET /v0/workspaces
Query: teamId (optional), limit (1-100), after (cursor)
```
Response fields: `object`, `id`, `teamId`, `name`, `createdAt`, `createdUserId`, `fields`, `childIds`

#### Get Workspace
```
GET /v0/workspaces/:id
```
Returns full workspace object including `childIds` (top-level item/collection IDs).

#### Create Item or Collection
```
POST /v0/items
```
Request body:
```json
{
  "workspaceId": "uuid",     // OR parentId, NOT both
  "parentId": "uuid",        // OR workspaceId, NOT both
  "object": "item",          // "item" (default) or "collection"
  "title": "string",         // optional
  "content": "markdown",     // optional
  "index": 0                 // optional, zero-based insertion position
}
```

**Critical:** `workspaceId` and `parentId` are mutually exclusive. For top-level collections, use `workspaceId`. For nested items inside collections, use `parentId`.

**Response does NOT include `content` field.** To read content, use `GET /v0/items/:id`.

#### Get Item/Collection
```
GET /v0/items/:id
```
Returns full object including `content`. Collections have `childIds`, items have `fields`.

#### List/Search Items
```
GET /v0/items
Query: workspaceId or teamId (required), search (optional), limit (1-100), after (cursor)
```
List response does NOT include `content` field.

#### Update Item
```
PUT /v0/items/:id
Body: { "title": "...", "content": "..." }  // both optional
```

#### Delete Item
```
DELETE /v0/items/:id
```
Moves to workspace trash (not permanent delete).

### Recommended Project Structure Addition

```
sync.py (single file -- Phase 2 adds to existing)
  # New constants
  NUCLINO_BASE = "https://api.nuclino.com"
  THROTTLE_DELAY = 0.35  # seconds between requests

  # New functions
  build_metadata_footer(created, modified) -> str
  make_nuclino_client(api_key) -> httpx.Client
  resolve_workspace(client, workspace_arg) -> str
  ensure_collection(client, workspace_id, account, folder, state) -> str
  create_nuclino_item(client, collection_id, title, content) -> str
  run_import(export_dir, workspace, api_key) -> None

  # Modified CLI
  sync() command gains --workspace and reads NUCLINO_API_KEY from env
```

### Pattern 1: Metadata Footer Construction
**What:** Build the HTML comment metadata block per D-01 through D-04.
**When to use:** For every note that has at least one non-None timestamp.

```python
def build_metadata_footer(created: datetime | None, modified: datetime | None) -> str:
    """Build HTML comment metadata footer. Returns empty string if no data."""
    if created is None and modified is None:
        return ""
    lines = ["<!-- nuclino-sync"]
    if created is not None:
        lines.append(f"created: {created.isoformat()}")
    if modified is not None:
        lines.append(f"modified: {modified.isoformat()}")
    lines.append("-->")
    return "\n" + "\n".join(lines)
```

### Pattern 2: Throttled API Client
**What:** httpx client with per-request throttle and tenacity retry on 429/5xx.
**When to use:** All Nuclino API calls.

```python
import time
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

NUCLINO_BASE = "https://api.nuclino.com"
THROTTLE_DELAY = 0.35  # ~170 req/min, well under 150 limit with retries

_last_request_time = 0.0

def _throttle():
    """Ensure minimum delay between API requests."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < THROTTLE_DELAY:
        time.sleep(THROTTLE_DELAY - elapsed)
    _last_request_time = time.monotonic()

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503)
    return False

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
)
def api_request(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    """Make a throttled, retried API request. Returns response data dict."""
    _throttle()
    resp = client.request(method, f"{NUCLINO_BASE}{path}", **kwargs)
    resp.raise_for_status()
    body = resp.json()
    return body["data"]
```

### Pattern 3: Idempotent Collection Creation
**What:** Check state before creating; key on `account/folder`.
**When to use:** Before creating items for a folder.

```python
def ensure_collection(
    client: httpx.Client,
    workspace_id: str,
    account: str,
    folder: str,
    state: dict,
) -> str:
    """Return collection ID, creating if needed. Idempotent via state."""
    # Account-level collection
    acct_key = account
    if acct_key not in state.get("collections", {}):
        data = api_request(client, "POST", "/v0/items", json={
            "workspaceId": workspace_id,
            "object": "collection",
            "title": account,
        })
        state.setdefault("collections", {})[acct_key] = data["id"]
        save_state(state, state_path)  # persist immediately

    acct_collection_id = state["collections"][acct_key]

    # Folder-level collection (nested under account)
    folder_key = f"{account}/{folder}"
    if folder_key not in state.get("collections", {}):
        data = api_request(client, "POST", "/v0/items", json={
            "parentId": acct_collection_id,
            "object": "collection",
            "title": folder,
        })
        state["collections"][folder_key] = data["id"]
        save_state(state, state_path)

    return state["collections"][folder_key]
```

### Pattern 4: Workspace Resolution with Interactive Fallback
**What:** Resolve workspace by name (case-insensitive) or ID, with interactive prompt on no match.
**When to use:** At import start, before any collection/item creation.

```python
def resolve_workspace(client: httpx.Client, workspace_arg: str) -> str:
    """Resolve workspace name or ID to workspace ID."""
    data = api_request(client, "GET", "/v0/workspaces")
    workspaces = data["results"] if "results" in data else data.get("items", [])

    # Try exact ID match
    for ws in workspaces:
        if ws["id"] == workspace_arg:
            return ws["id"]

    # Try case-insensitive name match
    for ws in workspaces:
        if ws["name"].lower() == workspace_arg.lower():
            return ws["id"]

    # Interactive fallback (D-10)
    if not workspaces:
        raise typer.BadParameter("No workspaces found for this API key.")

    typer.echo(f"No workspace '{workspace_arg}' found. Available:")
    for i, ws in enumerate(workspaces, 1):
        typer.echo(f"  {i}. {ws['name']}")
    choice = typer.prompt("Which one? (Ctrl+C to cancel)", type=int)
    if 1 <= choice <= len(workspaces):
        return workspaces[choice - 1]["id"]
    raise typer.BadParameter(f"Invalid choice: {choice}")
```

### Anti-Patterns to Avoid
- **Setting both `workspaceId` and `parentId`:** The API requires one or the other, never both. Top-level collections use `workspaceId`; nested items/collections use `parentId`.
- **Assuming `POST /v0/items` response includes `content`:** It does not. Only `GET /v0/items/:id` returns content. This is fine for our use case -- we only need the `id` from the create response.
- **Using `Authorization: ApiKey <key>` or `Authorization: Bearer <key>`:** The correct format is just `Authorization: <key>` with no prefix.
- **Fixed sleep between ALL requests:** Use a minimum-interval throttle instead. A fixed 1s sleep is wasteful; the throttle only sleeps when requests come faster than the minimum interval.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with backoff | Custom sleep loop with attempt counter | `tenacity` decorator | Edge cases in jitter, max delay capping, exception filtering; scattered logic across call sites |
| HTTP client with timeouts | Raw `urllib.request` | `httpx.Client` with `Timeout` | Connection vs read timeout separation, connection pooling, proper error types |
| Progress bar | Manual `\r` printing | `rich.progress.track()` or `Progress` context | Handles terminal width, redirect detection, task interleaving |
| Interactive prompts | Custom `input()` with validation | `typer.prompt()` | Type validation, Ctrl+C handling, consistent with CLI framework |

## Common Pitfalls

### Pitfall 1: Auth Header Format
**What goes wrong:** Using `Authorization: ApiKey <key>` or `Authorization: Bearer <key>` results in 401.
**Why it happens:** Earlier research (training data) assumed `ApiKey` prefix. The gist example uses `Bearer`. Official docs show raw key only.
**How to avoid:** Use `Authorization: <raw-key>` -- verified against official docs at help.nuclino.com.
**Warning signs:** 401 on first API call.

### Pitfall 2: workspaceId vs parentId Mutual Exclusion
**What goes wrong:** Setting both `workspaceId` and `parentId` on `POST /v0/items` causes a 400 error.
**Why it happens:** The API expects one or the other to determine placement. Top-level items/collections in a workspace use `workspaceId`; items inside a collection use `parentId`.
**How to avoid:** For account-level collections: `{"workspaceId": ws_id, "object": "collection", "title": "..."}`. For folder-level collections and items: `{"parentId": collection_id, ...}`.
**Warning signs:** 400 with message about workspaceId/parentId conflict.

### Pitfall 3: Rate Limit is 150/min, Not 5/s
**What goes wrong:** Throttling to 4 req/s (old assumption) is actually ~240 req/min, which exceeds the 150/min limit by 60%.
**Why it happens:** Earlier research cited "5 req/s" from training data. Official docs and PyNuclino both confirm 150/min.
**How to avoid:** Throttle to ~0.35s between requests (~170 req/min max, providing headroom for retries).
**Warning signs:** Frequent 429 responses.

### Pitfall 4: Response Status Values
**What goes wrong:** Checking for `response["status"] == "ok"` fails -- the API returns `"success"`, `"fail"`, or `"error"`.
**Why it happens:** Earlier research assumed `"ok"`.
**How to avoid:** Use `httpx.Response.raise_for_status()` for HTTP-level errors, then parse `resp.json()["data"]` for the payload. Only inspect `status` field for detailed error messages from 4xx/5xx.
**Warning signs:** Key error on `response["data"]` when the envelope structure doesn't match expectations.

### Pitfall 5: State Must Be Written Before Attachments (from Phase 1 research, still critical)
**What goes wrong:** Item created, attachment upload fails, exception propagates, item not recorded in state. Re-run creates a duplicate.
**How to avoid:** Write item ID to state IMMEDIATELY after `POST /v0/items` succeeds, BEFORE any attachment work. Phase 2 does not upload attachments, but the state must be written in a way that Phase 3 can layer attachments on top.
**Warning signs:** Duplicate items after re-running on failure.

### Pitfall 6: Collection Name Collision Across Accounts
**What goes wrong:** Both `iCloud/Notes` and `anders@thib.se/Notes` exist. Keying collections on folder name alone merges them.
**How to avoid:** Key state collections on `account/folder` string, not just folder name.
**Warning signs:** Notes from different accounts appearing in the same Nuclino collection.

## Code Examples

### Complete Import Loop (verified patterns)

```python
from rich.progress import Progress

def run_import(export_dir: Path, workspace_id: str, client: httpx.Client) -> None:
    state_path = export_dir / "nuclino-state.json"
    state = load_state(state_path)
    state["workspace_id"] = workspace_id

    notes, _ = discover_notes(export_dir)
    imported = 0
    failed = 0

    with Progress() as progress:
        task = progress.add_task("Importing notes...", total=len(notes))
        for note_file in notes:
            rel_path = str(note_file.md_path.relative_to(export_dir))

            # Skip if already imported
            if rel_path in state["items"] and state["items"][rel_path].get("status") == "imported":
                progress.advance(task)
                continue

            try:
                parsed = parse_note(note_file)
                body = clean_body(parsed.body, parsed.title)
                footer = build_metadata_footer(parsed.created, parsed.modified)
                content = body + footer

                collection_id = ensure_collection(
                    client, workspace_id,
                    note_file.account, note_file.folder,
                    state, state_path,
                )

                data = api_request(client, "POST", "/v0/items", json={
                    "parentId": collection_id,
                    "object": "item",
                    "title": parsed.title,
                    "content": content,
                })

                # Write state IMMEDIATELY
                state["items"][rel_path] = {
                    "status": "imported",
                    "title": parsed.title,
                    "nuclino_item_id": data["id"],
                    "nuclino_collection_id": collection_id,
                    "created": parsed.created.isoformat() if parsed.created else None,
                    "modified": parsed.modified.isoformat() if parsed.modified else None,
                }
                save_state(state, state_path)
                imported += 1

            except Exception as e:
                state["items"][rel_path] = {
                    "status": "failed",
                    "title": note_file.title,
                    "error": str(e),
                }
                save_state(state, state_path)
                failed += 1

            progress.advance(task)

    typer.echo(f"Imported {imported} notes. {failed} failed. See nuclino-state.json for details.")
```

### Client Construction

```python
def make_nuclino_client(api_key: str) -> httpx.Client:
    return httpx.Client(
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0),
    )
```

### CLI Extension

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
    workspace: str = typer.Option(
        None,
        "--workspace",
        envvar="NUCLINO_WORKSPACE_ID",
        help="Nuclino workspace name or ID",
    ),
) -> None:
    """Sync Apple Notes export to Nuclino."""
    if parse_only:
        run_parse_only(export_dir)
        return

    # API key from env (required for import)
    api_key = os.environ.get("NUCLINO_API_KEY")
    if not api_key:
        typer.echo("Error: NUCLINO_API_KEY environment variable is required.")
        raise typer.Exit(1)

    if not workspace:
        typer.echo("Error: --workspace is required. Set NUCLINO_WORKSPACE_ID or pass --workspace.")
        raise typer.Exit(1)

    client = make_nuclino_client(api_key)
    workspace_id = resolve_workspace(client, workspace)
    run_import(export_dir, workspace_id, client)
```

## State of the Art

| Old Approach (from training data) | Current Approach (verified 2026-03-21) | Impact |
|---|---|---|
| `Authorization: ApiKey <key>` | `Authorization: <key>` (raw) | Auth would fail with old format |
| Rate limit: 5 req/s | Rate limit: 150 req/min (~2.5 req/s) | Must throttle more aggressively |
| `POST /v0/collections` (separate endpoint) | `POST /v0/items` with `"object": "collection"` | Single endpoint for both; simplifies client |
| Response: `{"status": "ok", "data": {...}}` | `{"status": "success", "data": {...}}` | Must check for "success" not "ok" |
| `workspaceId` + `parentId` together | Mutually exclusive -- one or the other | Would get 400 errors with both |

## Open Questions

1. **`Retry-After` header on 429**
   - What we know: Rate limit is 150/min. 429 is returned on excess. Docs do not mention Retry-After.
   - What's unclear: Whether the header is present on 429 responses.
   - Recommendation: Code defensively -- check for it with `.get("Retry-After")` but always fall back to exponential backoff. The first real 429 will reveal the answer.

2. **Empty content on item creation**
   - What we know: 2 empty-body notes exist in the export. The API accepts `content` as optional.
   - What's unclear: Whether empty string content is accepted or rejected.
   - Recommendation: Phase 1 already handles this -- empty notes get `status: "skipped_empty"` in state. Phase 2 should skip these (they have no content to import).

3. **Workspace list pagination**
   - What we know: Pagination uses `limit` (1-100) and `after` cursor. Most users have few workspaces.
   - What's unclear: Whether a user could have >100 workspaces requiring pagination.
   - Recommendation: Fetch with `limit=100` (max). If >100 workspaces, paginate with `after`. For this one-time migration, unlikely to be an issue.

## Sources

### Primary (HIGH confidence)
- [Nuclino API Authentication](https://help.nuclino.com/8090bb76-authentication) -- header format: `Authorization: YOUR_API_KEY`
- [Nuclino Items and Collections](https://help.nuclino.com/fa38d15f-items-and-collections) -- unified `POST /v0/items` for both items and collections; `workspaceId`/`parentId` mutual exclusion; `object` field
- [Nuclino Workspaces](https://help.nuclino.com/702467a8-workspaces) -- `GET /v0/workspaces` response fields
- [Nuclino Response Format](https://help.nuclino.com/0a1bea6c-response-format-and-errors) -- `"status": "success"/"fail"/"error"` envelope
- [Nuclino Rate Limiting](https://help.nuclino.com/b147124e-rate-limiting) -- 150 requests/minute per API key
- [PyNuclino on PyPI](https://pypi.org/project/PyNuclino/) -- confirms 150 req/min, defaults to 140

### Secondary (MEDIUM confidence)
- [GitHub Gist: Creating notes in Nuclino](https://gist.github.com/danielrosehill/f34b72f2267acf7e5ff7917d63ab8eeb) -- working curl example (note: uses `Bearer` prefix which may be outdated vs official docs showing raw key)
- `.planning/research/STACK.md` -- httpx/tenacity recommendation (verified versions against pip index)
- `.planning/research/PITFALLS.md` -- export-side pitfalls (verified against actual data)

### Tertiary (LOW confidence)
- `Retry-After` header presence on 429 -- not confirmed in any official source; code defensively

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- httpx 0.28.1 and tenacity 9.1.4 verified via `pip index versions`
- Architecture: HIGH -- API endpoints and request/response formats verified against official docs
- Pitfalls: HIGH -- auth format, rate limit, and endpoint corrections all verified; export-side pitfalls verified against actual data

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (API is stable "public preview"; rate limits unlikely to change)
