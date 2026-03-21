"""nuclino-sync: Import Apple Notes exports into Nuclino."""

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import frontmatter
import httpx
import typer
from rich.progress import Progress
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

# --- Constants ---

VERSION_SUFFIX = re.compile(r"-\d+$")
APPLE_DATE_FMT = "%A, %d %B %Y at %H:%M:%S"
NUCLINO_BASE = "https://api.nuclino.com"
THROTTLE_DELAY = 0.35  # ~170 req/min, safely under 150/min limit

_last_request_time = 0.0
_upload_not_supported = False

# --- Data classes ---


@dataclass
class NoteFile:
    account: str
    folder: str
    title: str
    md_path: Path
    attachment_dir: Path | None


@dataclass
class ParsedNote:
    title: str
    body: str
    created: datetime | None
    modified: datetime | None
    attachment_dir: Path | None


# --- Core functions ---


def is_canonical(path: Path) -> bool:
    """True if this .md file is not a versioned snapshot."""
    return not VERSION_SUFFIX.search(path.stem)


def discover_notes(export_dir: Path) -> tuple[list[NoteFile], int]:
    """Walk export directory and return (canonical_notes, versioned_count)."""
    canonical: list[NoteFile] = []
    versioned_count = 0

    for account_dir in sorted(export_dir.iterdir()):
        if not account_dir.is_dir():
            continue
        account = account_dir.name
        for folder_dir in sorted(account_dir.iterdir()):
            if not folder_dir.is_dir():
                continue
            folder = folder_dir.name
            for md_file in sorted(folder_dir.glob("*.md")):
                if is_canonical(md_file):
                    att_dir = folder_dir / md_file.stem
                    attachment_dir = att_dir if att_dir.is_dir() else None
                    canonical.append(
                        NoteFile(
                            account=account,
                            folder=folder,
                            title=md_file.stem,
                            md_path=md_file,
                            attachment_dir=attachment_dir,
                        )
                    )
                else:
                    versioned_count += 1

    return canonical, versioned_count


def parse_apple_date(value: str) -> datetime:
    """Parse Apple Notes human-readable date to datetime."""
    return datetime.strptime(value.strip(), APPLE_DATE_FMT)


def parse_note(note_file: NoteFile) -> ParsedNote:
    """Parse a single .md file into structured note data."""
    post = frontmatter.load(str(note_file.md_path))
    title = post.get("title", note_file.md_path.stem)
    title = unicodedata.normalize("NFC", title)

    created = None
    if raw := post.get("created"):
        try:
            created = parse_apple_date(raw)
        except (ValueError, TypeError):
            pass

    modified = None
    if raw := post.get("modified"):
        try:
            modified = parse_apple_date(raw)
        except (ValueError, TypeError):
            pass

    return ParsedNote(
        title=title,
        body=post.content,
        created=created,
        modified=modified,
        attachment_dir=note_file.attachment_dir,
    )


def clean_body(body: str, title: str) -> str:
    """Strip first line if it exactly matches the frontmatter title."""
    if not body:
        return body
    lines = body.splitlines()
    if lines and lines[0].strip() == title:
        return "\n".join(lines[1:]).lstrip("\n")
    return body


# --- Nuclino API ---


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


def _throttle() -> None:
    """Ensure minimum delay between API requests."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < THROTTLE_DELAY:
        time.sleep(THROTTLE_DELAY - elapsed)
    _last_request_time = time.monotonic()


def _is_retryable(exc: BaseException) -> bool:
    """Return True if exception is a retryable HTTP status error."""
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


def make_nuclino_client(api_key: str) -> httpx.Client:
    """Create an httpx Client configured for the Nuclino API."""
    return httpx.Client(
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0),
    )


def resolve_workspace(client: httpx.Client, workspace_arg: str) -> str:
    """Resolve workspace name or ID to workspace ID."""
    data = api_request(client, "GET", "/v0/workspaces")
    workspaces = data.get("results", [])

    # Try exact ID match first
    for ws in workspaces:
        if ws["id"] == workspace_arg:
            return ws["id"]

    # Try case-insensitive name match (D-11)
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


def ensure_collection(
    client: httpx.Client,
    workspace_id: str,
    account: str,
    folder: str,
    state: dict,
    state_path: Path,
) -> str:
    """Return collection ID, creating if needed. Idempotent via state."""
    # Account-level collection (top-level in workspace)
    acct_key = account
    if acct_key not in state.get("collections", {}):
        data = api_request(client, "POST", "/v0/items", json={
            "workspaceId": workspace_id,
            "object": "collection",
            "title": account,
        })
        state.setdefault("collections", {})[acct_key] = data["id"]
        save_state(state, state_path)

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


# --- Attachment upload ---


def upload_attachments(
    client: httpx.Client,
    item_id: str,
    attachment_dir: Path,
    state_entry: dict,
    state: dict,
    state_path: Path,
) -> None:
    """Upload attachments for an item. Failures are isolated per-file."""
    global _upload_not_supported
    if _upload_not_supported:
        return

    attachment_failures: list[dict] = []
    attachment_links: list[str] = []

    for file_path in sorted(attachment_dir.iterdir()):
        if not file_path.is_file():
            continue
        try:
            with open(file_path, "rb") as f:
                _throttle()
                resp = client.post(
                    f"{NUCLINO_BASE}/v0/files",
                    data={"itemId": item_id},
                    files={"file": (file_path.name, f)},
                    headers={"Content-Type": None},
                )
                if resp.status_code in (404, 405):
                    _upload_not_supported = True
                    typer.echo(
                        "Warning: File upload not supported by Nuclino API. "
                        "Skipping all attachment uploads."
                    )
                    return
                resp.raise_for_status()
                file_data = resp.json()["data"]

            file_id = file_data.get("id", "")
            file_name = file_path.name
            permanent_url = f"https://files.nuclino.com/files/{file_id}/{file_name}"

            if file_name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                attachment_links.append(f"![{file_name}]({permanent_url})")
            else:
                attachment_links.append(f"[{file_name}]({permanent_url})")

        except Exception as e:
            attachment_failures.append({"file": file_path.name, "error": str(e)})

    # Update item content with attachment links (GET then PUT)
    if attachment_links:
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


# --- State management ---


def load_state(state_path: Path) -> dict:
    """Load state from JSON file; return empty state if missing or corrupt."""
    if not state_path.exists():
        return {"version": 1, "items": {}}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        typer.echo(f"Warning: corrupt state file at {state_path}, starting fresh")
        return {"version": 1, "items": {}}


def save_state(state: dict, state_path: Path) -> None:
    """Atomically write state to JSON file via tmp + rename."""
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(str(tmp), str(state_path))


# --- Import ---


def run_import(
    export_dir: Path,
    workspace_id: str,
    client: httpx.Client,
) -> None:
    """Import all notes to Nuclino with progress bar."""
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

            # Skip already-imported items (idempotent)
            if rel_path in state["items"] and state["items"][rel_path].get("status") == "imported":
                progress.advance(task)
                continue

            try:
                parsed = parse_note(note_file)
                body = clean_body(parsed.body, parsed.title)

                # Skip empty notes
                if not body.strip():
                    if rel_path not in state["items"]:
                        state["items"][rel_path] = {
                            "status": "skipped_empty",
                            "title": parsed.title,
                        }
                        save_state(state, state_path)
                    progress.advance(task)
                    continue

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

                # Write state IMMEDIATELY after item creation (Pitfall 5)
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

                # Upload attachments if any exist (separate error boundary)
                if note_file.attachment_dir:
                    try:
                        upload_attachments(
                            client, data["id"],
                            note_file.attachment_dir,
                            state["items"][rel_path],
                            state, state_path,
                        )
                    except Exception as e:
                        state["items"][rel_path].setdefault(
                            "attachment_failures", []
                        ).append({"file": "*", "error": f"Unexpected: {str(e)}"})
                        save_state(state, state_path)

            except Exception as e:
                # Record failure in state (D-08)
                state["items"][rel_path] = {
                    "status": "failed",
                    "title": note_file.title,
                    "error": str(e),
                }
                save_state(state, state_path)
                failed += 1

            progress.advance(task)

    # Summary line (D-07)
    typer.echo(
        f"Imported {imported} notes. {failed} failed. "
        f"See nuclino-state.json for details."
    )


# --- Parse-only command ---


def run_parse_only(export_dir: Path) -> None:
    """Parse export and print summary."""
    state_path = export_dir / "nuclino-state.json"
    state = load_state(state_path)

    notes, versioned_count = discover_notes(export_dir)

    accounts: set[str] = set()
    folders: set[str] = set()
    skipped_empty = 0
    parsed_count = 0

    for note_file in notes:
        accounts.add(note_file.account)
        folders.add(f"{note_file.account}/{note_file.folder}")

        rel_path = str(note_file.md_path.relative_to(export_dir))

        # Skip if already in state
        if rel_path in state["items"]:
            item = state["items"][rel_path]
            if item.get("status") == "skipped_empty":
                skipped_empty += 1
            else:
                parsed_count += 1
            continue

        parsed = parse_note(note_file)
        body = clean_body(parsed.body, parsed.title)

        if not body.strip():
            typer.echo(f"skipped empty note: {parsed.title}")
            state["items"][rel_path] = {
                "status": "skipped_empty",
                "title": parsed.title,
            }
            skipped_empty += 1
        else:
            state["items"][rel_path] = {
                "status": "parsed",
                "title": parsed.title,
                "created": parsed.created.isoformat() if parsed.created else None,
                "modified": parsed.modified.isoformat() if parsed.modified else None,
            }
            parsed_count += 1

        save_state(state, state_path)

    typer.echo(
        f"Found {parsed_count} canonical notes across "
        f"{len(accounts)} accounts, {len(folders)} folders. "
        f"{skipped_empty} skipped (empty). "
        f"{versioned_count} versioned snapshots ignored."
    )


# --- CLI ---

app = typer.Typer()


@app.command()
def sync(
    export_dir: Path = typer.Option(
        Path.home() / "Desktop" / "NotesExport",
        help="Path to Apple Notes export directory",
        envvar="NOTES_EXPORT_DIR",
    ),
    parse_only: bool = typer.Option(
        False,
        "--parse-only",
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
        typer.echo(
            "Error: --workspace is required. Set NUCLINO_WORKSPACE_ID or pass --workspace."
        )
        raise typer.Exit(1)

    client = make_nuclino_client(api_key)
    workspace_id = resolve_workspace(client, workspace)
    run_import(export_dir, workspace_id, client)


if __name__ == "__main__":
    app()
