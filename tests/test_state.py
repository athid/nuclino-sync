"""Tests for state management: load_state, save_state, run_parse_only integration."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from sync import load_state, run_parse_only, save_state


# --- State load/save (STATE-01, STATE-03) ---


class TestLoadState:
    def test_load_state_missing_file(self, tmp_path):
        result = load_state(tmp_path / "state.json")
        assert result == {"version": 1, "items": {}}

    def test_load_state_valid_file(self, tmp_path):
        state_path = tmp_path / "state.json"
        data = {"version": 1, "items": {"iCloud/Notes/Test.md": {"status": "parsed", "title": "Test"}}}
        state_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_state(state_path)
        assert result == data

    def test_load_state_corrupt_json(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json", encoding="utf-8")
        result = load_state(state_path)
        assert result == {"version": 1, "items": {}}


class TestSaveState:
    def test_save_state_creates_file(self, tmp_path):
        state_path = tmp_path / "state.json"
        save_state({"version": 1, "items": {}}, state_path)
        assert state_path.exists()
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data == {"version": 1, "items": {}}

    def test_save_state_roundtrip(self, tmp_path):
        state_path = tmp_path / "state.json"
        original = {
            "version": 1,
            "items": {
                "iCloud/Notes/Note.md": {
                    "status": "parsed",
                    "title": "Note",
                    "created": "2024-09-12T07:24:45",
                },
                "iCloud/Notes/Empty.md": {
                    "status": "skipped_empty",
                    "title": "Empty",
                },
            },
        }
        save_state(original, state_path)
        loaded = load_state(state_path)
        assert loaded == original

    def test_save_state_atomic_uses_replace(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.json"
        calls = []
        original_replace = os.replace

        def tracking_replace(src, dst):
            calls.append((src, dst))
            return original_replace(src, dst)

        monkeypatch.setattr("os.replace", tracking_replace)
        save_state({"version": 1, "items": {}}, state_path)

        assert len(calls) == 1
        src, dst = calls[0]
        assert str(src).endswith(".json.tmp")
        assert str(dst).endswith(".json")

    def test_save_state_no_tmp_leftover(self, tmp_path):
        state_path = tmp_path / "state.json"
        save_state({"version": 1, "items": {}}, state_path)
        tmp_file = state_path.with_suffix(".json.tmp")
        assert not tmp_file.exists()


# --- State schema correctness (STATE-01, D-04) ---


class TestStateSchema:
    def test_state_has_version_field(self, tmp_path):
        state_path = tmp_path / "state.json"
        save_state({"version": 1, "items": {}}, state_path)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["version"] == 1

    def test_state_items_keyed_on_relative_path(self, sample_export):
        run_parse_only(sample_export)
        state_path = sample_export / "nuclino-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        for key in data["items"]:
            # Keys should be relative paths, not absolute
            assert not key.startswith("/")
            assert key.startswith("iCloud/") or key.startswith("anders@")


# --- Idempotency (STATE-02) ---


class TestIdempotency:
    def test_rerun_skips_processed(self, sample_export, capsys):
        # First run processes all notes
        run_parse_only(sample_export)
        first_output = capsys.readouterr().out

        # Second run should not print "skipped empty note:" again
        # because the empty note is already in state
        run_parse_only(sample_export)
        second_output = capsys.readouterr().out

        # First run should have the skip warning
        assert "skipped empty note:" in first_output
        # Second run should NOT have the skip warning (already in state)
        assert "skipped empty note:" not in second_output

    def test_rerun_does_not_duplicate_items(self, sample_export):
        run_parse_only(sample_export)
        run_parse_only(sample_export)
        state_path = sample_export / "nuclino-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        # 3 canonical notes: Note.md, Empty.md, My-Note.md
        assert len(data["items"]) == 3


# --- Empty note handling (D-03, D-04) ---


class TestEmptyNoteHandling:
    def test_empty_note_skipped_with_warning(self, sample_export, capsys):
        run_parse_only(sample_export)
        output = capsys.readouterr().out
        assert "skipped empty note: Empty" in output

    def test_empty_note_recorded_in_state(self, sample_export):
        run_parse_only(sample_export)
        state_path = sample_export / "nuclino-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        empty_key = [k for k in data["items"] if "Empty" in k][0]
        assert data["items"][empty_key]["status"] == "skipped_empty"

    def test_parsed_note_has_status_parsed(self, sample_export):
        run_parse_only(sample_export)
        state_path = sample_export / "nuclino-state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        note_key = [k for k in data["items"] if k.endswith("Note.md") and "Empty" not in k and "My-Note" not in k][0]
        assert data["items"][note_key]["status"] == "parsed"


# --- Summary output (D-06) ---


class TestSummaryOutput:
    def test_parse_only_summary_format(self, sample_export, capsys):
        run_parse_only(sample_export)
        output = capsys.readouterr().out
        assert "canonical notes across" in output
        assert "accounts" in output
        assert "folders" in output
        assert "skipped (empty)" in output
        assert "versioned snapshots ignored" in output
