# Domain Pitfalls

**Domain:** Apple Notes export → Nuclino API import (Python)
**Researched:** 2026-03-21
**Confidence note:** Pitfalls 1–10 are verified against the actual export at `~/Desktop/NotesExport/`
(133 files, 39 canonical notes). Nuclino-specific claims (rate limits, API field names, content
format) derive from training data (cutoff August 2025) and should be verified against
https://api.nuclino.com/v0 docs before implementation.

---

## Critical Pitfalls

Mistakes that cause silent data loss, duplicate content, or a broken import that cannot be undone.

---

### Pitfall 1: Versioned Files Are Revision Snapshots — Glob Will Import 3x the Notes

**What goes wrong:** The Apple Notes export tool emits multiple files per note: a canonical
`<Title>.md` plus numbered snapshots `<Title>-1.md`, `<Title>-2.md`, etc. A naive recursive
glob (`**/*.md`) imports every one as a separate Nuclino item, flooding the workspace with
duplicate content.

**Verified in actual export:**
- `Hus.md` is accompanied by `Hus-1.md` through `Hus-11.md` — 12 files for one note
- 39 canonical files vs 133 total `.md` files (3.4x ratio)
- Versioned files are either byte-identical to the canonical or differ only in extra blank lines
  between paragraphs — same logical content, just more whitespace
- The canonical (no-suffix) file is the cleaned, authoritative version

**Consequences:** Silent — no API error, everything "succeeds." 3–4x the expected Nuclino items.

**Prevention:** Filter to canonical files only. Exclude any file whose stem ends in `-\d+`:
```python
import re
from pathlib import Path

def is_canonical(path: Path) -> bool:
    return not re.search(r'-\d+$', path.stem)
```

**Detection:** Count `.md` files; if the count greatly exceeds expected note count, versioned
files are present.

---

### Pitfall 2: Mojibake in YAML Title for Versioned Files (and Only Versioned Files)

**What goes wrong:** For versioned (`-1`, `-2`) files containing Swedish (non-ASCII Latin)
characters, the `title:` YAML field contains double-encoded UTF-8: the UTF-8 bytes for `å/ä/ö`
were interpreted as latin-1 and then re-encoded to UTF-8, producing `Ã¥`/`Ã¤`/`Ã¶`.

**Verified in actual export:**
- 23 versioned files have mojibake titles; 0 canonical files do
- Examples: `Köpa-1.md` has `title: KÃ¶pa`; `Köpa.md` has `title: Köpa` (correct)
- The body text in ALL files (including affected ones) is correctly encoded UTF-8
- The mojibake is structurally valid UTF-8, so Python's `open(..., encoding='utf-8')` will not
  raise — it silently reads garbage

**Consequences:** If versioned files are imported (violating Pitfall 1's fix), Nuclino items get
garbled Swedish titles. Silent.

**Primary fix:** Filter versioned files out (Pitfall 1). This eliminates all affected files.

**Secondary defense:** Detect double-encoding in any title that passes through:
```python
import unicodedata

def fix_mojibake(title: str) -> str:
    try:
        candidate = title.encode('latin-1').decode('utf-8')
        # If round-trip changed the string, it was double-encoded
        if candidate != title:
            return candidate
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return title
```

---

### Pitfall 3: Note Body Repeats Title as Plain Text First Line (No Heading Markup)

**What goes wrong:** Apple Notes export places the note's title as the literal first line of the
body — as plain text, not as a `# Markdown heading`. Importing verbatim means every Nuclino item
shows the title twice: once as the item name, once as the first line of content.

**Verified in actual export:** 100 of 123 notes-with-bodies (81%) start the body with the exact
title string as plain text. No notes use a `#` heading at all.

**Consequences:** Cosmetically broken for 81% of imported notes. Cannot be bulk-undone after
import without editing each item individually.

**Prevention:** Strip the first line if it exactly matches the frontmatter `title`:
```python
lines = body.splitlines()
if lines and lines[0].strip() == title:
    body = '\n'.join(lines[1:]).lstrip('\n')
```

**Edge case:** Do not strip if the first line does NOT match — 23 notes in this export start with
different content (typically because the mojibake title didn't match the clean body first line).

---

### Pitfall 4: YAML `created`/`modified` Dates Are Human-Readable Strings, Not ISO 8601

**What goes wrong:** The frontmatter date fields use the format:
`Thursday, 12 September 2024 at 07:24:45` — not ISO 8601. Passing to `datetime.fromisoformat()`
or to the Nuclino API raises an error or silently discards the value.

**Verified in actual export:** All 133 files use this exact format. No variation across years
2011–2026.

**Consequences:**
- `datetime.fromisoformat()` raises `ValueError` — this is a loud failure (good for catching it)
- PyYAML will NOT auto-parse this as a datetime (it is not a YAML timestamp spec); it arrives
  as a plain string
- If caught silently or skipped, `created` date is permanently lost

**Prevention:** Parse explicitly with `strptime`:
```python
from datetime import datetime

def parse_apple_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), '%A, %d %B %Y at %H:%M:%S')
```

**Note:** The Nuclino API does not accept `created_at` on item creation (server-side timestamp
only). The parsed date should be appended to the note body as a visible metadata block.

---

### Pitfall 5: Frontmatter Fields `created`, `modified`, Tags Have No Nuclino API Equivalent

**What goes wrong:** All three frontmatter fields appear in the export but have no writable
Nuclino API field. If dropped silently, the user loses irreversible metadata after the import.

**Nuclino item creation fields (MEDIUM confidence — training knowledge):**
- `workspaceId` or `parentId` (required)
- `object` = `"item"`
- `title` (string)
- `content` (markdown string)

There is no `createdAt`, `tags`, or `modifiedAt` parameter.

**Verified in actual export:**
- 0 files have a `tags:` field — Apple Notes did not export tags for this dataset
- Only `title`, `created`, `modified` appear as frontmatter keys

**Consequences:** All imported notes show creation date as today (import date) unless `created`
is preserved somewhere in the content.

**Prevention:** Append metadata as a footer block in the note content:
```markdown

---
*Imported from Apple Notes*
*Originally created: Thursday, 12 September 2024 at 07:24:45*
```

Log every unmapped frontmatter field at import time so the user knows what was dropped vs
serialized.

---

### Pitfall 6: Silent Metadata Loss Is the Default Without Explicit Pre-Flight Warning

**What goes wrong:** The script successfully creates every item, the user declares the import
done, then discovers that all created dates are today (the import date) and the original dates
are gone — with no error in the log because the mapping gap was never surfaced.

**Prevention:**
1. Print a pre-flight summary before any API calls: "Fields that will be serialized to note body:
   created, modified. Fields with no destination: [none found in this export]."
2. Log per-note: `INFO: Hus.md — created: 2012-07-23 → appended to body (no API field)`
3. Never silently discard a frontmatter field.

---

### Pitfall 7: Attachment Upload Failure Treated as Note-Level Failure Creates Duplicates

**What goes wrong:** The script creates a Nuclino item, then uploads 3 attachments. The 3rd
fails (unsupported type, quota, timeout). The exception propagates to the outer loop; the note is
marked as failed and re-queued. On the next run, a duplicate note is created, then the attachments
are attempted again.

**Consequences:** Duplicate Nuclino items; re-running makes it worse; state becomes inconsistent.

**Prevention:**
1. Persist the item ID to state IMMEDIATELY after creating the item, BEFORE any attachment uploads
2. Wrap each attachment upload in its own try/except — separate from the note-level try/except
3. Log attachment failures as warnings, recording which item ID and which filename failed
4. On re-run, if item ID is in state, skip item creation but still retry failed attachments

```python
item_id = create_item(title, content)
state.record_item(source_file, item_id)   # write state NOW, before attachments

for attachment_path in attachments:
    try:
        upload_attachment(item_id, attachment_path)
    except Exception as e:
        state.record_failed_attachment(item_id, attachment_path, str(e))
        log.warning(f"Attachment failed: {attachment_path} on item {item_id}: {e}")
```

---

### Pitfall 8: State File Not Written Atomically — Crash Loses All Progress

**What goes wrong:** The script is killed (Ctrl-C, power loss) mid-write to `state.json`.
The file is truncated; on the next run, `json.loads()` raises `JSONDecodeError` and the script
exits without processing any notes — all previous progress appears lost.

**Prevention:** Use write-then-rename, which is atomic on POSIX (macOS):
```python
import os, json

def save_state(state: dict, path: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)  # atomic
```

**Detection:** Kill the script mid-run with `kill -9`; verify `state.json` is still valid JSON.

---

## Moderate Pitfalls

---

### Pitfall 9: Rate Limiting Will Terminate a Bulk Import Mid-Run Without Backoff

**What goes wrong:** A tight loop firing API calls at Python speed hits 429 errors. Without
proper backoff, the script either crashes (partial import) or retries endlessly.

**Known limits (MEDIUM confidence — training knowledge; verify against current docs):**
- ~60 requests/minute on standard Nuclino plans
- The `Retry-After` header may or may not be present on 429 responses (contradictory sources
  in training data — do not assume it exists)

**Prevention:**
1. Add a base inter-request delay of ~0.25s (4 req/s) — below the documented limit
2. Implement exponential backoff on 429 with a `Retry-After` fallback:

```python
import time

def api_call_with_retry(fn, *args, max_retries=5, **kwargs):
    for attempt in range(max_retries):
        resp = fn(*args, **kwargs)
        if resp.status_code == 429:
            # Do NOT assume Retry-After is present
            wait = float(resp.headers.get('Retry-After', 2 ** attempt))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("Rate limit retry exhausted")
```

---

### Pitfall 10: Collection Name Collision Across Accounts — Notes Intermingled Silently

**What goes wrong:** Multiple accounts each have a folder named "Notes" (this export's actual
structure). The script creates one Nuclino collection for the first account's "Notes" folder,
then finds it in state and assigns the second account's notes to the same collection.

**Verified relevant in this export:** Both `iCloud/Notes` and `anders@thib.se/Notes` are present.
In this case `anders@thib.se/Notes` is empty, so the collision would be harmless — but any
export with two non-empty same-named folders triggers the bug.

**Prevention:** Key state and collection hierarchy on `account_name/folder_name`, not just
`folder_name`:
```python
collection_key = f"{account_name}/{folder_name}"  # not just folder_name
```

When multiple accounts exist, create a top-level collection per account, with the folder
collection nested beneath it.

---

### Pitfall 11: Empty Account Directories Must Not Create Empty Collections

**What goes wrong:** `anders@thib.se/Notes/` exists as a directory but contains zero files.
Creating a Nuclino collection for it adds noise to the workspace.

**Verified in actual export:** `anders@thib.se/Notes/` has 0 files.

**Prevention:** Check for at least one canonical `.md` file before creating the Nuclino
collection for a folder.

---

### Pitfall 12: Unicode NFC Normalization for Titles and Collection Names

**What goes wrong:** Note titles with accented characters (Swedish å, ä, ö in this export) may
arrive in NFD (decomposed) form from macOS APFS/HFS+ filenames. The `title:` YAML field may
also carry NFD. Sending NFD strings to Nuclino means search may miss them.

**Prevention:**
```python
import unicodedata
title = unicodedata.normalize("NFC", title)
```

Apply to both item title and folder name (collection name) derived from the filesystem.

**Note:** Tested export has this in the YAML `title` field already NFC-encoded (all confirmed
UTF-8 clean), but the normalization is cheap insurance.

---

### Pitfall 13: Empty-Body Notes Are Valid But May Surprise the User

**What goes wrong:** 2 canonical notes (`!.md`, `New Note.md`) have only frontmatter and an
empty body. The Nuclino API will accept an item with empty content; it appears as a blank page.

**Prevention:** Define explicit policy:
- Skip empty-body notes (risks silent data loss — user may not know they were skipped)
- Import with a placeholder `*(empty note)*` (preserves note existence, clearly marked)
- Recommended: import with placeholder and log which notes got it

---

### Pitfall 14: "!" as a Note Title — API and UI Behavior Unknown

**What goes wrong:** One canonical note is titled `!` (single exclamation mark). Nuclino item
titles are free-form strings but edge cases with single-character special-character titles may
trigger API rejections or render oddly.

**Verified in actual export:** `!.md` exists with `title: !` in frontmatter.

**Prevention:** Validate the HTTP response after every item creation. Log any `4xx` response
alongside the source filename and title. Do not silently swallow creation errors — they indicate
a note was not imported.

---

### Pitfall 15: Raw URLs in Note Bodies Should Render as Clickable Links — Verify

**What goes wrong:** The export contains 48 bare `https://...` URLs in note bodies (not wrapped
in `[text](url)` Markdown syntax). Nuclino's content rendering may display these as plaintext
rather than clickable links depending on its Markdown flavor.

**Verified in actual export:** Multiple notes contain bare URLs; none use `[text](url)` format.

**Prevention:** Test with one note containing a bare URL before bulk import. If bare URLs don't
auto-link, wrap them: `<https://...>` (CommonMark autolink format).

---

### Pitfall 16: Export Error Log Is Misleading — Do Not Use It as a Skip List

**What goes wrong:** `export-errors.log` lists 41 "Skipped" notes. Most (`User cancelled`)
were retried successfully and ARE in the export. If the import script reads this log to exclude
notes, it skips 39 notes that actually exported correctly.

**Verified in actual export:** Notes like `Hus`, `!`, `VPN` appear in both the error log and
the canonical file list. The canonical files are the source of truth.

**Exception:** One note (`omic Strive 12 GW … Stopperbredd…`) had error code 100000 and is
genuinely absent. Notes with very long titles containing commas, currency symbols, and mixed
scripts may fail to export at all.

**Prevention:** Import based solely on which `.md` files exist — not on what the error log says.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| File discovery | Importing versioned `-N` files as separate notes (Pitfall 1) | Filter: exclude stem ending `-\d+` |
| Title extraction | Mojibake in YAML title of `-N` files (Pitfall 2) | Primary fix: skip versioned files |
| Body cleaning | Title repeated as plain-text first line (Pitfall 3) | Strip first line if it matches title |
| Date parsing | Non-ISO date format in frontmatter (Pitfall 4) | `strptime('%A, %d %B %Y at %H:%M:%S')` |
| Metadata mapping | `created`/`modified` have no Nuclino field (Pitfall 5) | Append as footer block in content |
| User communication | Silent metadata loss (Pitfall 6) | Pre-flight summary + per-note INFO log |
| Attachment upload | Exception propagates to item level (Pitfall 7) | Separate try/except per attachment |
| State management | Non-atomic JSON write (Pitfall 8) | `os.replace()` write-then-rename |
| API calls | 429 rate limiting mid-import (Pitfall 9) | Base delay + backoff; `Retry-After` fallback |
| Collection creation | Name collision across accounts (Pitfall 10) | Key on `account/folder`, not `folder` |
| Collection creation | Empty account directory (Pitfall 11) | Skip folder if zero canonical files |
| Title/collection names | NFD Unicode (Pitfall 12) | `unicodedata.normalize("NFC", ...)` |
| Empty notes | `!` and `New Note` have no body (Pitfall 13) | Import with `*(empty note)*` placeholder |
| API edge cases | `!` title may fail or render oddly (Pitfall 14) | Always validate `POST /items` response |
| Content rendering | Bare URLs may not autolink (Pitfall 15) | Test before bulk import |

---

## Sources

- Direct inspection of `~/Desktop/NotesExport/` (133 .md files, 2 accounts) — HIGH confidence
- Python analysis scripts run against actual export data on 2026-03-21 — HIGH confidence
- Nuclino API v0 (training knowledge through August 2025) — MEDIUM confidence for field names,
  LOW confidence for exact rate limits and response headers; verify at https://api.nuclino.com/v0
- macOS APFS/HFS+ NFD normalization behavior — HIGH confidence (documented Apple behavior)
- PyYAML timestamp parsing behavior — HIGH confidence (PyYAML documentation)
- Python `os.replace()` atomicity guarantee — HIGH confidence (POSIX specification)
