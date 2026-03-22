# nuclino-sync

Import Apple Notes exports into Nuclino.

## Prerequisites

- Python 3.12+
- pip
- A Nuclino account with an API key

## Install

```bash
pip install -e .
```

## Configuration

Two environment variables are required:

- `NUCLINO_API_KEY` -- your API key from Nuclino Settings > API. The key value itself (no prefix needed).
- `NUCLINO_WORKSPACE_ID` -- the Nuclino workspace name or ID to import into. Can also be passed as `--workspace`.

One environment variable is optional:

- `NOTES_EXPORT_DIR` -- path to the Apple Notes export directory. Defaults to `~/Desktop/NotesExport`. Can also be passed as `--export-dir`.

```bash
export NUCLINO_API_KEY="your-api-key"
export NUCLINO_WORKSPACE_ID="My Workspace"
```

## Usage

**Dry-run first (recommended):**

```bash
python sync.py --dry-run
```

This prints a pre-flight summary and per-note import plan without making any API calls. Use it to verify the script sees the right notes before committing to an import.

**Run the import:**

```bash
python sync.py
```

**Parse-only (offline):**

```bash
python sync.py --parse-only
```

Parses the export directory and prints a summary. No API key required.

**Repair attachments:**

```bash
python sync.py --repair-attachments
```

Re-processes attachments for all already-imported notes. Useful if attachment uploads failed on a previous run. If the Nuclino API supports file uploads, files are uploaded and inline references are rewritten to permanent URLs. If uploads are not supported, inline references are left as-is so you can identify and replace them manually.

## Attachments and inline images

Apple Notes exports embed image references as local relative paths, e.g.:

```
![image-1.heic](Note Title/image-1.heic)
```

The script attempts to upload each file in the note's attachment directory to Nuclino and rewrite the inline reference to the permanent URL. If the Nuclino API does not support file uploads (the `/v0/files` endpoint returns 404 or 405), the original local path reference is left in the note content unchanged — so you can find and replace images manually.

Nuclino's API is a v0 (limited) API that only covers core content operations. File upload was never added to it — it's a deliberate scope limitation, not a missing feature. The web app supports attachments, but the public API does not. Upload images manually through the Nuclino web UI and update the references in the note.

## State file

The script writes `nuclino-state.json` in the export directory after each successful note import. This file tracks which notes and collections have been created.

- Safe to re-run: already-imported notes are skipped.
- If interrupted, the state file is not corrupted (atomic writes via temporary file + rename).
- Delete `nuclino-state.json` to start a fresh import.

## Links

- [Nuclino API documentation](https://help.nuclino.com/d3a29686-api)
