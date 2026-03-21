"""Shared pytest fixtures for nuclino-sync tests."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_note(tmp_path):
    """Create a minimal .md file with frontmatter and body."""
    content = """\
---
title: Test Note
created: Thursday, 12 September 2024 at 07:24:45
modified: Friday, 13 September 2024 at 10:00:00
---

Test Note
This is the body content.
"""
    note_dir = tmp_path / "iCloud" / "Notes"
    note_dir.mkdir(parents=True)
    note_path = note_dir / "Test Note.md"
    note_path.write_text(content, encoding="utf-8")
    return note_path


@pytest.fixture
def sample_export(tmp_path):
    """Create a realistic export directory with canonical, versioned, and empty notes."""
    notes_dir = tmp_path / "iCloud" / "Notes"
    notes_dir.mkdir(parents=True)

    # Canonical note with body
    (notes_dir / "Note.md").write_text(
        "---\ntitle: Note\ncreated: Thursday, 12 September 2024 at 07:24:45\n"
        "modified: Thursday, 12 September 2024 at 07:24:45\n---\n\nNote\nBody here.\n",
        encoding="utf-8",
    )

    # Versioned snapshot (single digit)
    (notes_dir / "Note-1.md").write_text(
        "---\ntitle: Note\ncreated: Thursday, 12 September 2024 at 07:24:45\n"
        "modified: Thursday, 12 September 2024 at 07:24:45\n---\n\nNote\nBody here.\n",
        encoding="utf-8",
    )

    # Versioned snapshot (multi-digit)
    (notes_dir / "Note-12.md").write_text(
        "---\ntitle: Note\ncreated: Thursday, 12 September 2024 at 07:24:45\n"
        "modified: Thursday, 12 September 2024 at 07:24:45\n---\n\nNote\nBody here.\n",
        encoding="utf-8",
    )

    # Empty note (body is just whitespace after frontmatter)
    (notes_dir / "Empty.md").write_text(
        "---\ntitle: Empty\ncreated: Thursday, 12 September 2024 at 07:24:45\n"
        "modified: Thursday, 12 September 2024 at 07:24:45\n---\n\n   \n",
        encoding="utf-8",
    )

    # Canonical note with hyphen in title
    (notes_dir / "My-Note.md").write_text(
        "---\ntitle: My-Note\ncreated: Thursday, 12 September 2024 at 07:24:45\n"
        "modified: Thursday, 12 September 2024 at 07:24:45\n---\n\nMy-Note\nContent.\n",
        encoding="utf-8",
    )

    # Second account directory (empty -- no notes)
    (tmp_path / "anders@thib.se" / "Notes").mkdir(parents=True)

    # Attachment directory for Note.md (sibling dir named "Note")
    att_dir = notes_dir / "Note"
    att_dir.mkdir()
    (att_dir / "image.png").write_bytes(b"\x89PNG fake image data")

    return tmp_path


@pytest.fixture
def empty_export(tmp_path):
    """Create an export directory with no .md files."""
    (tmp_path / "iCloud" / "Notes").mkdir(parents=True)
    return tmp_path
