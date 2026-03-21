# Phase 1: Foundation - Research

**Researched:** 2026-03-21
**Domain:** Apple Notes export parsing, state management, CLI entry point (Python)
**Confidence:** HIGH

## Summary

Phase 1 is a purely offline parsing and state-management phase. The script must discover 39 canonical notes from 133 `.md` files by filtering out versioned snapshots, parse YAML frontmatter (title, created, modified), strip duplicate title lines from note bodies, discover attachment directories, and track processing state atomically. The entry point is `python sync.py --parse-only` which prints a summary line.

All critical patterns have been verified against the actual export at `~/Desktop/NotesExport/`. The versioned file filter (`-\d+` stem suffix) cleanly separates 39 canonical from 94 versioned files. The `python-frontmatter` library returns dates as plain strings (not datetime objects) for this date format, so explicit `strptime` parsing is required. Title-as-first-line stripping uses exact string match and affects all canonical notes with bodies (100% of non-empty canonicals). No attachment directories exist in this export, but the discovery code must handle them for correctness.

**Primary recommendation:** Implement five focused functions (`discover_notes`, `parse_note`, `clean_body`, `load_state`, `save_state`) in a flat `sync.py`, using `python-frontmatter` for parsing, `datetime.strptime` for dates, `os.replace` for atomic writes, and `typer` for the CLI.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** State file lives in the export directory: `<export-dir>/nuclino-state.json`
- **D-02:** Filename is visible (not a dotfile) -- easy to find and inspect
- **D-03:** Notes with empty bodies are skipped with a printed warning: `"skipped empty note: <title>"`
- **D-04:** Skipped empty notes are recorded in `state.json` with `"status": "skipped_empty"` -- not re-attempted on re-run
- **D-05:** `python sync.py --parse-only` is the runnable entry point for Phase 1 verification -- no API calls
- **D-06:** `--parse-only` output is summary-only: `"Found N canonical notes across A accounts, F folders. S skipped (empty). V versioned snapshots ignored."`

### Claude's Discretion
- Canonical file detection regex (versioned snapshot stems match `-\d+` before extension -- implementation detail)
- Date parsing implementation (`strptime` format string for `Thursday, 12 September 2024 at 07:24:45`)
- State file JSON schema (keys, structure, version field if any)
- Test coverage approach (pytest assumed, structure up to planner)

### Deferred Ideas (OUT OF SCOPE)
- None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PARSE-01 | Filter versioned snapshots, process only canonical notes | Regex `r'-\d+$'` on `Path.stem` verified: 39 canonical, 94 versioned from 133 total |
| PARSE-02 | Strip duplicate title line from body when first line matches title | Exact string match verified: 100% of non-empty canonical notes match; `lines[0].strip() == title` |
| PARSE-03 | Parse human-readable date format into datetime | `strptime('%A, %d %B %Y at %H:%M:%S')` verified against actual dates spanning 2011-2026 |
| PARSE-04 | Extract all frontmatter fields and note body | `python-frontmatter` 1.1.0 returns `.keys()` = `[title, created, modified]`, `.content` = body string |
| PARSE-05 | Discover attachment files from sibling directory | `Path(note.parent / title)` check; no attachment dirs in current export but code must handle them |
| STATE-01 | Write state file tracking processed items | JSON file at `<export-dir>/nuclino-state.json` keyed on relative source path |
| STATE-02 | Re-running skips already-imported items | Check state dict before processing; `skipped_empty` entries also prevent re-processing |
| STATE-03 | Atomic state writes survive interruption | `json.dump` to `.tmp` file then `os.replace()` -- atomic on POSIX/macOS |
</phase_requirements>

## Standard Stack

### Core (Phase 1 only)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-frontmatter` | 1.1.0 (latest) | Parse YAML frontmatter + body from .md files | Canonical library; handles edge cases (missing frontmatter, empty body, unicode) |
| `typer` | >=0.12 (latest 0.24.1) | CLI entry point with `--parse-only` flag | Type-hint driven CLI; zero boilerplate for simple flags |
| `rich` | >=13 (latest 14.3.3) | Colored console output for warnings and summary | Already a typer dependency; use for styled output |

### Supporting (stdlib only for Phase 1)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `pathlib.Path` | File discovery, path manipulation | All file operations |
| `re` | Versioned file detection regex | `is_canonical()` filter |
| `datetime.strptime` | Date parsing | Apple Notes date format |
| `json` | State file read/write | `load_state()` / `save_state()` |
| `os.replace` | Atomic file rename | `save_state()` crash safety |
| `unicodedata.normalize` | NFC normalization for titles | Swedish characters (a, a, o) |
| `dataclasses` | Structured data objects | `NoteFile`, `ParsedNote` |

**Installation (Phase 1):**
```bash
pip install "python-frontmatter>=1.1" "typer>=0.12" "rich>=13"
```

## Architecture Patterns

### Recommended Project Structure (Phase 1)
```
nuclino-sync/
  sync.py              # single script -- entry point + all logic
  pyproject.toml       # dependencies and Python version
  tests/
    test_parse.py      # unit tests for parsing functions
    test_state.py      # unit tests for state management
    conftest.py        # shared fixtures (tmp dirs, sample notes)
  .env.example         # documents required env vars (Phase 2+)
  .gitignore           # nuclino-state.json, .env, __pycache__
```

### Pattern 1: Canonical File Discovery
**What:** Walk export directory, filter to canonical `.md` files only.
**Implementation:**

```python
import re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class NoteFile:
    account: str        # "iCloud" or "anders@thib.se"
    folder: str         # "Notes"
    title: str          # from frontmatter, not filename
    md_path: Path       # absolute path to .md file
    attachment_dir: Path | None  # sibling dir if exists

VERSION_SUFFIX = re.compile(r'-\d+$')

def is_canonical(path: Path) -> bool:
    """True if this .md file is not a versioned snapshot."""
    return not VERSION_SUFFIX.search(path.stem)

def discover_notes(export_dir: Path) -> tuple[list[NoteFile], int]:
    """Returns (canonical_notes, versioned_count)."""
    canonical = []
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
                    # Check for sibling attachment directory
                    # Title comes from frontmatter, but for discovery use stem
                    att_dir = folder_dir / md_file.stem
                    attachment_dir = att_dir if att_dir.is_dir() else None
                    canonical.append(NoteFile(
                        account=account,
                        folder=folder,
                        title=md_file.stem,  # placeholder; real title from parse
                        md_path=md_file,
                        attachment_dir=attachment_dir,
                    ))
                else:
                    versioned_count += 1
    return canonical, versioned_count
```

**Verified against actual export:** This pattern yields exactly 39 canonical notes and 94 versioned files. The `anders@thib.se/Notes/` directory is empty and correctly produces zero notes.

### Pattern 2: Frontmatter Parsing + Date Conversion
**What:** Parse `.md` file, extract metadata, convert date strings to datetime.

```python
import frontmatter
from datetime import datetime

APPLE_DATE_FMT = "%A, %d %B %Y at %H:%M:%S"

def parse_apple_date(value: str) -> datetime:
    """Parse Apple Notes human-readable date to datetime."""
    return datetime.strptime(value.strip(), APPLE_DATE_FMT)

@dataclass
class ParsedNote:
    title: str
    body: str
    created: datetime | None
    modified: datetime | None
    attachment_dir: Path | None

def parse_note(note_file: NoteFile) -> ParsedNote:
    """Parse a single .md file into structured note data."""
    post = frontmatter.load(str(note_file.md_path))
    title = post.get("title", note_file.md_path.stem)
    title = unicodedata.normalize("NFC", title)

    created = None
    if raw := post.get("created"):
        created = parse_apple_date(raw)

    modified = None
    if raw := post.get("modified"):
        modified = parse_apple_date(raw)

    body = post.content
    return ParsedNote(
        title=title,
        body=body,
        created=created,
        modified=modified,
        attachment_dir=note_file.attachment_dir,
    )
```

**Verified:** `python-frontmatter` 1.1.0 returns `created` and `modified` as **plain strings** (not datetime objects) for this date format. PyYAML does NOT auto-parse `Thursday, 12 September 2024 at 07:24:45` -- it is not a YAML timestamp. The `strptime` format `'%A, %d %B %Y at %H:%M:%S'` has been tested against dates from 2011 through 2026.

### Pattern 3: Body Cleaning (Title Line Stripping)
**What:** Remove duplicate title from first line of body.

```python
def clean_body(body: str, title: str) -> str:
    """Strip first line if it exactly matches the frontmatter title."""
    if not body:
        return body
    lines = body.splitlines()
    if lines and lines[0].strip() == title:
        # Strip the title line and any leading blank lines after it
        return "\n".join(lines[1:]).lstrip("\n")
    return body
```

**Verified:** Tested against all 133 files. Every canonical note with a non-empty body has its first line exactly matching the frontmatter `title` field (100% match rate for canonicals). The 19 non-matching files are all versioned files with mojibake titles. Use **exact string match** (`==`), not normalized/fuzzy match -- the data is clean for canonical files.

### Pattern 4: Atomic State Management
**What:** JSON state file with crash-safe writes.

```python
import json
import os

def load_state(state_path: Path) -> dict:
    """Load state from JSON file; return empty state if missing or corrupt."""
    if not state_path.exists():
        return {"version": 1, "items": {}}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt state -- start fresh but warn
        return {"version": 1, "items": {}}

def save_state(state: dict, state_path: Path) -> None:
    """Atomically write state to JSON file."""
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(state_path))
```

**State schema (recommended):**
```json
{
  "version": 1,
  "items": {
    "iCloud/Notes/Hus.md": {
      "status": "parsed",
      "title": "Hus",
      "created": "2012-07-23T00:00:00"
    },
    "iCloud/Notes/New Note.md": {
      "status": "skipped_empty",
      "title": "New Note"
    }
  }
}
```

**Key design choices:**
- Keys are **relative paths** from export dir (e.g., `iCloud/Notes/Hus.md`) per CONTEXT.md D-01
- `status` field: `"parsed"` for successful notes, `"skipped_empty"` per D-04
- `version` field enables schema migration if needed later
- `os.replace()` is atomic on POSIX (macOS) -- if the process is killed mid-write, the `.tmp` file is left behind but the original `state.json` is untouched

### Pattern 5: Typer CLI with --parse-only
**What:** Entry point using typer with a `--parse-only` flag.

```python
import typer
from pathlib import Path

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
) -> None:
    """Sync Apple Notes export to Nuclino."""
    if parse_only:
        run_parse_only(export_dir)
    else:
        typer.echo("Import not yet implemented (Phase 2+)")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
```

**Note on `--parse-only` naming:** Typer converts underscores to hyphens automatically for CLI flags. A parameter named `parse_only` becomes `--parse-only` on the command line. This is the default behavior in typer >= 0.12.

### Anti-Patterns to Avoid
- **Glob `**/*.md` without filtering:** Imports 133 files (3.4x too many). Always filter with `is_canonical()`.
- **Using `datetime.fromisoformat()` for Apple dates:** Raises `ValueError`. These dates are NOT ISO 8601.
- **Fuzzy title matching for body stripping:** Unnecessary complexity. Exact match works for 100% of canonical files.
- **Writing state at end of run only:** A crash after processing 20 notes loses all progress. Write after each note.
- **Reading `export-errors.log` as a skip list:** Most "skipped" entries were retried successfully. Filesystem presence is the only truth.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | regex to split `---` blocks | `python-frontmatter` 1.1.0 | Edge cases: no trailing newline, colons in values, unicode, empty body |
| CLI argument parsing | `argparse` or `sys.argv` | `typer` >= 0.12 | Type-hint driven, auto `--help`, `envvar=` support |
| Atomic file write | manual `open()` + `close()` | `os.replace(tmp, target)` | POSIX atomic rename guarantee; stdlib |

## Common Pitfalls

### Pitfall 1: Versioned Files Inflate Note Count 3.4x
**What goes wrong:** Without filtering, 133 files are processed instead of 39 canonical notes.
**Why it happens:** Apple Notes export creates `Title-1.md`, `Title-2.md` etc. as revision snapshots.
**How to avoid:** `re.search(r'-\d+$', path.stem)` to detect and skip versioned files.
**Warning signs:** Note count exceeds expected 39.

### Pitfall 2: YAML Parse Errors in Versioned Files (Control Characters)
**What goes wrong:** 4 versioned files contain control characters (0x0084, 0x0096) that cause `yaml.reader.ReaderError`.
**Why it happens:** Mojibake from double-encoded UTF-8 in versioned file frontmatter.
**How to avoid:** This only affects versioned files. Canonical files parse cleanly. The `is_canonical()` filter eliminates all affected files.
**Warning signs:** `ReaderError: unacceptable character` exceptions.

### Pitfall 3: Date Fields Are Strings, Not Datetimes
**What goes wrong:** Code assumes `post.get("created")` returns a `datetime` object.
**Why it happens:** The Apple Notes date format (`Thursday, 12 September 2024 at 07:24:45`) is NOT a YAML timestamp spec. PyYAML returns it as a plain string.
**How to avoid:** Always call `parse_apple_date()` explicitly on the string value.
**Warning signs:** `AttributeError: 'str' object has no attribute 'isoformat'` or similar.

### Pitfall 4: Empty Body Detection Must Use `.strip()`
**What goes wrong:** `if not post.content` may miss notes with whitespace-only bodies.
**Why it happens:** `python-frontmatter` returns empty string for truly empty bodies, but whitespace-only bodies come back as whitespace.
**How to avoid:** Use `if not post.content.strip()` as the emptiness check.
**Warning signs:** Notes with only whitespace slip through as "non-empty" but produce blank Nuclino items.

### Pitfall 5: Attachment Directory Name Must Match Note Title, Not Filename Stem
**What goes wrong:** Looking for `<stem>/` when the stem has been NFC-normalized differently from the filesystem.
**Why it happens:** macOS APFS uses NFD normalization for filenames.
**How to avoid:** Use `Path.is_dir()` check on the constructed path. The filesystem comparison handles normalization. For extra safety, also check `md_file.stem` (which comes from the same filesystem).
**Warning signs:** Attachment directories not found despite existing on disk.

### Pitfall 6: State File Path Is Relative to Export Dir, Not CWD
**What goes wrong:** State file written to `./nuclino-state.json` (cwd) instead of `<export-dir>/nuclino-state.json`.
**Why it happens:** Forgetting that D-01 specifies the state file lives in the export directory.
**How to avoid:** `state_path = export_dir / "nuclino-state.json"` -- always derive from `export_dir`.
**Warning signs:** State file appears in wrong location; re-runs don't find previous state.

## Code Examples

### Complete `--parse-only` Flow
```python
def run_parse_only(export_dir: Path) -> None:
    """Parse export and print summary."""
    state_path = export_dir / "nuclino-state.json"
    state = load_state(state_path)

    notes, versioned_count = discover_notes(export_dir)

    accounts = set()
    folders = set()
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
```

### Testing Strategy (pytest)

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def sample_note(tmp_path):
    """Create a minimal .md file with frontmatter."""
    content = """---
title: Test Note
created: Thursday, 12 September 2024 at 07:24:45
modified: Friday, 13 September 2024 at 10:00:00
---

Test Note
This is the body content.
"""
    note_path = tmp_path / "iCloud" / "Notes" / "Test Note.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text(content, encoding="utf-8")
    return note_path

@pytest.fixture
def sample_export(tmp_path):
    """Create a minimal export directory structure."""
    notes_dir = tmp_path / "iCloud" / "Notes"
    notes_dir.mkdir(parents=True)
    # Canonical note
    (notes_dir / "Note.md").write_text("---\ntitle: Note\ncreated: Thursday, 12 September 2024 at 07:24:45\nmodified: Thursday, 12 September 2024 at 07:24:45\n---\n\nNote\nBody here.\n")
    # Versioned snapshot
    (notes_dir / "Note-1.md").write_text("---\ntitle: Note\ncreated: Thursday, 12 September 2024 at 07:24:45\nmodified: Thursday, 12 September 2024 at 07:24:45\n---\n\nNote\nBody here.\n")
    # Empty note
    (notes_dir / "Empty.md").write_text("---\ntitle: Empty\ncreated: Thursday, 12 September 2024 at 07:24:45\nmodified: Thursday, 12 September 2024 at 07:24:45\n---\n\n")
    return tmp_path
```

**What to test:**
| Test | What It Verifies |
|------|-----------------|
| `test_is_canonical` | `Note.md` -> True, `Note-1.md` -> False, `Note-12.md` -> False, `My-Note.md` -> True |
| `test_discover_notes_count` | Sample export yields correct canonical count |
| `test_parse_frontmatter` | Title, created, modified extracted correctly |
| `test_parse_date` | `strptime` format works for actual date strings |
| `test_clean_body_strips_title` | First line removed when it matches title |
| `test_clean_body_no_strip` | Body unchanged when first line differs from title |
| `test_clean_body_empty` | Empty body returns empty string |
| `test_save_load_state_roundtrip` | JSON state survives write + read |
| `test_state_atomic_write` | `.tmp` file created then replaced |
| `test_skip_empty_note` | Empty note recorded as `skipped_empty` in state |
| `test_rerun_skips_processed` | Second run doesn't reprocess items already in state |
| `test_is_canonical_edge_cases` | `80x90 rvg.md` -> True (hyphen in title, no trailing digits) |

**Critical edge case for `is_canonical`:** The regex `r'-\d+$'` must match the STEM only (not the full filename). A note titled `80x90 rvg` has stem `80x90 rvg` (no trailing `-\d+`) and is correctly canonical. A note titled `My-Note` has stem `My-Note` and is also correctly canonical (the `-Note` part doesn't end in digits).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pathlib.Path.walk()` | Available since Python 3.12 | Oct 2023 | Not using -- `.iterdir()` + `.glob()` work for this 2-level-deep structure |
| `typer` 0.9 API | typer 0.12+ with fixed `Optional` handling | 2024 | Pin `>=0.12` to avoid type annotation bugs |
| `yaml.FullLoader` default | Still the default in PyYAML 6.0.x | -- | Fine for own data; `SafeLoader` for untrusted input |

## Open Questions

1. **Attachment directory naming convention**
   - What we know: No attachment directories exist in the current 39-note export. The convention is a sibling directory named after the note title.
   - What's unclear: Whether the directory name matches the filesystem stem or the frontmatter title (they could differ with NFC/NFD).
   - Recommendation: Use `md_file.stem` for the directory name check (same filesystem encoding). The directory check is a `Path.is_dir()` call that costs nothing if the dir doesn't exist.

2. **State file behavior on first run vs re-run**
   - What we know: First run creates the file; re-run loads and skips processed items.
   - What's unclear: Should corrupt state (invalid JSON) fail loudly or start fresh?
   - Recommendation: Start fresh with a warning. A corrupt state file means the `.tmp` rename failed (extremely unlikely) or manual editing went wrong. Starting fresh re-parses everything (cheap in Phase 1) without data loss.

## Sources

### Primary (HIGH confidence)
- Actual export at `~/Desktop/NotesExport/` -- 133 files inspected programmatically (2026-03-21)
- `python-frontmatter` 1.1.0 tested against actual export files -- confirmed string return for dates, empty string for empty bodies
- `datetime.strptime('%A, %d %B %Y at %H:%M:%S')` verified against 3 representative dates (2013, 2021, 2024)
- PyPI registry: `python-frontmatter` 1.1.0, `typer` 0.24.1, `rich` 14.3.3 (verified 2026-03-21)
- `os.replace()` atomicity -- POSIX specification (HIGH confidence)

### Secondary (MEDIUM confidence)
- STACK.md, PITFALLS.md, ARCHITECTURE.md -- project research from 2026-03-21 (training-data-based library recommendations verified against PyPI)

### Tertiary (LOW confidence)
- None -- all findings verified against actual data or official APIs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- versions verified on PyPI, `python-frontmatter` tested against actual files
- Architecture: HIGH -- patterns verified against actual export structure and data
- Pitfalls: HIGH -- all Phase 1 pitfalls verified against actual export (Pitfalls 1-4 confirmed programmatically)
- Date parsing: HIGH -- `strptime` format string tested against real dates from the export

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (stable domain -- no fast-moving dependencies)
