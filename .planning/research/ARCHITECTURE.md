# Architecture Patterns

**Project:** nuclino-sync
**Researched:** 2026-03-21

---

## 1. Script Structure: Flat Script vs. Package

**Recommendation: flat single-file script (`sync.py`) with a small number of well-named functions.**

**Rationale:**

This is a one-time migration tool, not a library to be imported by other code. A single `sync.py` at the project root is the right size. The logic naturally divides into five concerns (discover, parse, create collections, create items, upload attachments), each fitting in a focused function rather than a separate module.

A `src/` layout and full package structure add `__init__.py`, `pyproject.toml`, editable installs, and import path complexity that provide zero benefit for a script run once from the command line. Keep it simple.

**File layout:**

```
nuclino-sync/
  sync.py          # the script — entry point, all logic
  requirements.txt
  .env.example     # documents required env vars
  state.json       # written at runtime (gitignored)
  .gitignore
```

If the script grows beyond ~400 lines or needs unit tests against isolated components, extract into:

```
nuclino-sync/
  sync.py           # entry point only, calls migrate()
  nuclino_sync/
    __init__.py
    discover.py
    parser.py
    api.py
    state.py
    progress.py
```

Do not do this upfront. Wait for the pain.

---

## 2. Main Module / Function Structure

### Entry point

```python
# sync.py

@click.command()
@click.option("--export-dir", envvar="NOTES_EXPORT_DIR", ...)
@click.option("--api-key",    envvar="NUCLINO_API_KEY",  ...)
@click.option("--workspace-id", envvar="NUCLINO_WORKSPACE_ID", ...)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--state-file", default="state.json")
def main(export_dir, api_key, workspace_id, dry_run, state_file):
    ...
```

### Recommended function boundaries

| Function | Signature | Responsibility |
|----------|-----------|---------------|
| `discover_notes(export_dir)` | `Path -> list[NoteFile]` | Walk the tree, return structured list of discovered notes |
| `parse_note(path)` | `Path -> Note` | Read file, split frontmatter/body, return dataclass |
| `load_state(path)` | `Path -> State` | Read JSON state file; return empty State if missing |
| `save_state(state, path)` | `State, Path -> None` | Atomically write state to JSON |
| `ensure_collection(client, workspace_id, name, state)` | `-> str (collection_id)` | Create collection if not already tracked in state |
| `create_item(client, collection_id, note)` | `-> str (item_id)` | POST item, return its ID |
| `upload_attachment(client, item_id, file_path)` | `-> None` | Upload single attachment and link it to item |
| `run_migration(...)` | top-level orchestration | Calls all of the above; drives the main loop |

### Dataclasses

```python
@dataclass
class NoteFile:
    account: str
    folder: str
    title: str
    md_path: Path
    attachment_dir: Path | None  # sibling dir if it exists

@dataclass
class Note:
    title: str
    body: str
    frontmatter: dict        # raw YAML fields
    created: str | None
    tags: list[str]
    attachment_dir: Path | None

@dataclass
class State:
    collections: dict[str, str]  # folder_name -> nuclino_collection_id
    items: dict[str, str]        # md_path (str) -> nuclino_item_id
    errors: list[dict]           # {path, error, timestamp}
```

---

## 3. Idempotency Pattern

**Recommendation: local state file (JSON) keyed on file path.**

**Rationale:** Querying Nuclino for existing items by title is unreliable (titles are not unique) and consumes API quota. A local `state.json` file is the standard pattern for one-shot migration scripts. It is fast, requires no API calls, and survives restarts.

**How it works:**

1. On startup, load `state.json` (empty dict if missing).
2. State contains two maps: `collections` (folder name → collection ID) and `items` (md file path → item ID).
3. Before creating a collection or item, check the state map. If the key exists, skip creation and reuse the stored ID.
4. After every successful creation, immediately write the updated state back to disk (not just at the end — a mid-run crash must not lose progress).
5. Before processing attachments, check whether the item was newly created vs. loaded from state. If loaded from state, attachments were presumably already uploaded; skip unless a `--force` flag is set.

**Atomic state writes** — write to `state.json.tmp` then rename to `state.json`. This prevents a corrupt partial write from destroying the state file if the process is killed mid-write.

```python
def save_state(state: State, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2))
    tmp.rename(path)
```

**Alternative considered: query Nuclino for existing items.** Rejected because: no reliable unique key to match on, wastes API quota, slower startup.

---

## 4. Error Handling Pattern for Batch API Operations

**Recommendation: collect errors per-item, never fail fast, log all failures to state and stderr, print summary at end.**

**Rationale:** This is a migration script. A single bad note (e.g., malformed frontmatter, API error on one item) must not abort 500 other notes. The user needs a complete picture of what succeeded and what failed.

**Pattern: try/except per item, append to error log, continue.**

```python
for note_file in tqdm(notes, desc="Importing notes"):
    try:
        note = parse_note(note_file.md_path)
        collection_id = ensure_collection(client, workspace_id, note_file.folder, state)
        item_id = create_item(client, collection_id, note)
        # upload attachments...
        state.items[str(note_file.md_path)] = item_id
        save_state(state, state_file)
    except Exception as exc:
        error = {
            "path": str(note_file.md_path),
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }
        state.errors.append(error)
        save_state(state, state_file)
        click.echo(f"  SKIP {note_file.md_path}: {exc}", err=True)
```

**Summary at end:**

```python
if state.errors:
    click.echo(f"\n{len(state.errors)} items failed. See state.json for details.", err=True)
else:
    click.echo("\nAll notes imported successfully.")
```

**Exception granularity:** Catch broadly (`Exception`) at the note level. Let lower-level functions raise naturally — do not swallow inside `parse_note` or `create_item`. The outer loop is the single place to decide "skip this note and continue."

**For attachments specifically:** Treat attachment failures as warnings, not errors. Log them but do not mark the parent item as failed. A note with a missing attachment is still a successfully imported note.

---

## 5. Rate Limiting / Exponential Backoff

**Recommendation: manual retry loop with exponential backoff on 429, using `Retry-After` header when present.**

**Rationale:** The `tenacity` library is the cleanest solution for retry logic in Python, but it is an extra dependency. For this script's use case — a simple HTTP client wrapping one API — a thin manual retry decorator is zero-dependency and equally readable. Use `tenacity` if the retry logic needs to handle multiple different error conditions across many call sites.

**Nuclino API rate limits:** As of the Nuclino developer documentation, the API enforces rate limits and returns HTTP 429 when exceeded. The response includes a `Retry-After` header (seconds to wait).

**Recommended approach — a `_call_api` wrapper:**

```python
import time
import requests

MAX_RETRIES = 5

def _call_api(method: str, url: str, **kwargs) -> dict:
    """
    Make a single API call, retrying on 429 with exponential backoff.
    Raises requests.HTTPError for non-retryable failures.
    """
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", delay))
            wait = max(retry_after, delay)
            click.echo(f"  Rate limited. Waiting {wait:.1f}s...", err=True)
            time.sleep(wait)
            delay = min(delay * 2, 60)   # exponential backoff, cap at 60s
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Exceeded {MAX_RETRIES} retries for {method} {url}")
```

**Why not `requests.adapters.Retry`:** The urllib3 `Retry` adapter does not sleep between retries by default on 429 responses with `Retry-After` headers (it ignores the header value). Manual handling gives explicit control over the wait time.

**Why not `tenacity`:** Extra dependency for a 15-line manual implementation. If retry logic expands (e.g., retry on network timeouts, retry on 503), add tenacity at that point.

---

## 6. Progress Tracking

**Recommendation: `tqdm` wrapping the notes list, with per-item suffix updates.**

**Rationale:** `tqdm` is the de facto standard for Python CLI progress bars. It requires one import and one wrapping call. The alternative (`rich.progress`) is more powerful but heavier.

```python
from tqdm import tqdm

with tqdm(total=len(notes), desc="Importing", unit="note") as pbar:
    for note_file in notes:
        pbar.set_postfix_str(note_file.title[:40])
        # ... process note ...
        pbar.update(1)
```

**What to display:**
- Main bar: notes processed / total
- Postfix: current note title (truncated)
- After completion: summary line with counts of successes and failures

**Do not use logging for progress.** Use `tqdm` for the progress bar and `click.echo(..., err=True)` for skip/error messages. These write to stderr and do not corrupt the progress bar.

**Structured log file:** Write a `sync.log` alongside `state.json` using Python's `logging` module at DEBUG level. This gives post-run auditability without cluttering the terminal.

```python
logging.basicConfig(
    filename="sync.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
```

---

## 7. Configuration Pattern

**Recommendation: CLI flags with `envvar` fallback, no config file.**

**Rationale:** For a CLI tool run occasionally by one person, environment variables backed by a `.env` file are the right complexity level. A `config.toml` adds a file format to parse and document; CLI flags add discoverability via `--help`. Click's `envvar=` parameter gives both: the flag is visible in `--help`, but the user can set it in `.env` and never type it.

**Configuration surface:**

| Parameter | CLI flag | Env var | Notes |
|-----------|----------|---------|-------|
| Nuclino API key | `--api-key` | `NUCLINO_API_KEY` | Required |
| Workspace ID | `--workspace-id` | `NUCLINO_WORKSPACE_ID` | Required |
| Export directory | `--export-dir` | `NOTES_EXPORT_DIR` | Default: `~/Desktop/NotesExport` |
| State file path | `--state-file` | `NUCLINO_STATE_FILE` | Default: `./state.json` |
| Dry run | `--dry-run` | — | Flag only; no env var needed |
| Verbose | `--verbose` / `-v` | — | Sets log level to DEBUG on stderr |

**`.env` loading:** Use `python-dotenv` to auto-load a `.env` file in the current directory. One line at the top of the script:

```python
from dotenv import load_dotenv
load_dotenv()
```

This means the user creates a `.env` file with their key, never passes it on the command line, and it is not stored in shell history. Provide `.env.example` in the repo.

**Why not a TOML/YAML config file:** Config files are better when settings are complex (nested, typed, shared across tools). Three string values do not justify a config file format.

**Why not hardcoded defaults for API key:** Never. The script must fail with a clear error message if `NUCLINO_API_KEY` is not set.

---

## 8. Component Boundaries and Data Flow

```
CLI entry (main)
  |
  +-- load_state(state_file)
  |
  +-- discover_notes(export_dir)
  |     -> list[NoteFile]
  |
  +-- for each NoteFile:
  |     parse_note(md_path)
  |       -> Note (frontmatter + body)
  |
  |     ensure_collection(client, workspace_id, folder, state)
  |       -> collection_id
  |       [reads/writes state.collections]
  |       [calls _call_api POST /collections if not in state]
  |
  |     create_item(client, collection_id, note)
  |       -> item_id
  |       [calls _call_api POST /items]
  |
  |     for each attachment in note.attachment_dir:
  |       upload_attachment(client, item_id, file_path)
  |         [calls _call_api POST /files]
  |
  |     state.items[path] = item_id
  |     save_state(state, state_file)
  |
  +-- print summary
```

---

## 9. Key Architectural Decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Single file vs. package | Single file `sync.py` | Migration tool; no reuse needed |
| Idempotency mechanism | Local `state.json` | No API quota cost; survives restarts |
| Error handling | Collect per-item, continue | Migration must not stop on partial failure |
| Retry mechanism | Manual loop with backoff | No extra dependency; respects `Retry-After` |
| Progress display | `tqdm` | De facto standard, one dependency |
| Config | CLI flags + env vars via `python-dotenv` | Discoverable, no shell history exposure |
| State persistence | Atomic write (tmp + rename) | Crash-safe |
| Attachment failures | Log as warning, don't fail note | Partial success is better than none |

---

## 10. Pitfalls Specific to This Architecture

**State file drift.** If a Nuclino item is deleted manually after import, the state file still records its ID. Re-running the script will skip re-creating it. Mitigation: add a `--force` flag that ignores state and re-imports everything.

**Collection name collisions.** Two Apple Notes folders in different accounts could have the same name and map to the same Nuclino collection. State keys on folder name alone. Mitigation: key state on `account/folder` not just `folder`.

**Large attachment files.** The Nuclino API may have a file size limit per attachment. The script should check file size before attempting upload and log an informative error (not a generic HTTP 413 stack trace) when exceeded.

**Frontmatter parse failures.** Malformed YAML in a note's frontmatter will raise an exception inside `parse_note`. This is fine — the outer loop catches it and skips the note. Do not silently fall back to empty frontmatter; log the parse error.

**Path encoding on macOS.** Apple Notes exports file names with Unicode NFD normalization (composed characters decomposed). Nuclino API titles should use NFC. Apply `unicodedata.normalize("NFC", title)` when setting item titles.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Python project structure | HIGH | Well-established patterns, training data reliable |
| Idempotency via state file | HIGH | Standard migration script pattern |
| Error collection pattern | HIGH | Well-established batch processing pattern |
| Exponential backoff implementation | HIGH | Standard HTTP retry pattern |
| tqdm for progress | HIGH | Confirmed via official docs fetch |
| Click + envvar config | HIGH | Click's envvar= is a documented feature |
| Nuclino API specifics (rate limit header name, file size limit) | LOW | Could not fetch Nuclino developer docs; flag for validation during implementation |

---

## Sources

- pathlib.Path.walk() — Python 3.12 official documentation (fetched 2026-03-21)
- tqdm README — pypi.org/project/tqdm (fetched 2026-03-21)
- Click envvar support — training knowledge (HIGH confidence, well-documented)
- urllib3 Retry / requests HTTPAdapter — training knowledge (HIGH confidence)
- tenacity library — training knowledge (MEDIUM confidence, verify version)
- python-dotenv — training knowledge (HIGH confidence)
- Nuclino API developer docs — NOT fetched (access blocked); all Nuclino-specific claims are LOW confidence and must be verified against https://developers.nuclino.com/
