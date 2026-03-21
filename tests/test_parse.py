"""Tests for parsing functions: is_canonical, discover_notes, parse_apple_date, parse_note, clean_body."""

from datetime import datetime
from pathlib import Path

from sync import (
    NoteFile,
    clean_body,
    discover_notes,
    is_canonical,
    parse_apple_date,
    parse_note,
)


# --- is_canonical tests ---


class TestIsCanonical:
    def test_is_canonical_regular_note(self):
        assert is_canonical(Path("Note.md")) is True

    def test_is_canonical_versioned_single_digit(self):
        assert is_canonical(Path("Note-1.md")) is False

    def test_is_canonical_versioned_multi_digit(self):
        assert is_canonical(Path("Note-12.md")) is False

    def test_is_canonical_hyphen_in_title(self):
        assert is_canonical(Path("My-Note.md")) is True

    def test_is_canonical_number_in_title(self):
        assert is_canonical(Path("80x90 rvg.md")) is True

    def test_is_canonical_trailing_digit_no_hyphen(self):
        assert is_canonical(Path("Note2.md")) is True


# --- discover_notes tests ---


class TestDiscoverNotes:
    def test_discover_notes_count(self, sample_export):
        notes, versioned = discover_notes(sample_export)
        # Canonical: Note.md, Empty.md, My-Note.md = 3
        assert len(notes) == 3
        # Versioned: Note-1.md, Note-12.md = 2
        assert versioned == 2

    def test_discover_notes_accounts(self, sample_export):
        notes, _ = discover_notes(sample_export)
        accounts = {n.account for n in notes}
        assert "iCloud" in accounts
        # anders@thib.se exists but has no notes, so not in discovered accounts
        assert "anders@thib.se" not in accounts

    def test_discover_notes_attachment_dir(self, sample_export):
        notes, _ = discover_notes(sample_export)
        by_title = {n.title: n for n in notes}

        # Note.md has a sibling "Note" directory with image.png
        assert by_title["Note"].attachment_dir is not None
        assert by_title["Note"].attachment_dir.is_dir()
        assert (by_title["Note"].attachment_dir / "image.png").exists()

        # Empty.md and My-Note.md have no attachment directories
        assert by_title["Empty"].attachment_dir is None
        assert by_title["My-Note"].attachment_dir is None

    def test_discover_notes_empty_export(self, empty_export):
        notes, versioned = discover_notes(empty_export)
        assert notes == []
        assert versioned == 0


# --- parse_apple_date tests ---


class TestParseAppleDate:
    def test_parse_apple_date_2024(self):
        result = parse_apple_date("Thursday, 12 September 2024 at 07:24:45")
        assert result == datetime(2024, 9, 12, 7, 24, 45)

    def test_parse_apple_date_2012(self):
        result = parse_apple_date("Monday, 23 July 2012 at 00:00:00")
        assert result == datetime(2012, 7, 23, 0, 0, 0)

    def test_parse_apple_date_strips_whitespace(self):
        result = parse_apple_date("  Thursday, 12 September 2024 at 07:24:45  ")
        assert result == datetime(2024, 9, 12, 7, 24, 45)


# --- parse_note tests ---


class TestParseNote:
    def _make_note_file(self, note_path):
        """Helper to create a NoteFile from a path."""
        return NoteFile(
            account="iCloud",
            folder="Notes",
            title=note_path.stem,
            md_path=note_path,
            attachment_dir=None,
        )

    def test_parse_note_extracts_title(self, sample_note):
        nf = self._make_note_file(sample_note)
        result = parse_note(nf)
        assert result.title == "Test Note"

    def test_parse_note_extracts_dates(self, sample_note):
        nf = self._make_note_file(sample_note)
        result = parse_note(nf)
        assert result.created == datetime(2024, 9, 12, 7, 24, 45)
        assert result.modified == datetime(2024, 9, 13, 10, 0, 0)

    def test_parse_note_extracts_body(self, sample_note):
        nf = self._make_note_file(sample_note)
        result = parse_note(nf)
        # Body includes the duplicate title line (cleaning is separate)
        assert result.body.startswith("Test Note")


# --- clean_body tests ---


class TestCleanBody:
    def test_clean_body_strips_matching_title(self):
        assert clean_body("Test Note\nBody content.", "Test Note") == "Body content."

    def test_clean_body_preserves_non_matching(self):
        result = clean_body("Different first line\nBody.", "Test Note")
        assert result == "Different first line\nBody."

    def test_clean_body_empty_string(self):
        assert clean_body("", "Test Note") == ""

    def test_clean_body_strips_leading_blank_lines(self):
        result = clean_body("Test Note\n\n\nBody content.", "Test Note")
        assert result == "Body content."

    def test_clean_body_whitespace_only(self):
        result = clean_body("   \n  ", "Test Note")
        assert result == "   \n  "
