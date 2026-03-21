"""Tests for API functions: metadata footer, client, workspace resolution, collections, import, attachments."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx
import typer
import pytest

from sync import (
    build_metadata_footer,
    ensure_collection,
    make_nuclino_client,
    resolve_workspace,
    run_import,
    upload_attachments,
)


# --- Metadata footer (D-01, D-02, D-03, D-04) ---


class TestBuildMetadataFooter:
    def test_both_dates(self):
        result = build_metadata_footer(
            created=datetime(2024, 9, 12, 7, 24, 45),
            modified=datetime(2024, 9, 12, 9, 0, 0),
        )
        assert "<!-- nuclino-sync" in result
        assert "created: 2024-09-12T07:24:45" in result
        assert "modified: 2024-09-12T09:00:00" in result
        assert "-->" in result

    def test_created_only(self):
        result = build_metadata_footer(
            created=datetime(2024, 9, 12, 7, 24, 45),
            modified=None,
        )
        assert "created: 2024-09-12T07:24:45" in result
        assert "modified" not in result

    def test_modified_only(self):
        result = build_metadata_footer(
            created=None,
            modified=datetime(2024, 9, 12, 9, 0, 0),
        )
        assert "modified: 2024-09-12T09:00:00" in result
        assert "created" not in result

    def test_both_none(self):
        result = build_metadata_footer(created=None, modified=None)
        assert result == ""

    def test_starts_with_newline(self):
        result = build_metadata_footer(
            created=datetime(2024, 9, 12, 7, 24, 45),
            modified=None,
        )
        assert result.startswith("\n")


# --- Nuclino client ---


class TestMakeNuclinoClient:
    def test_auth_header_no_prefix(self):
        client = make_nuclino_client("test-key-123")
        assert client.headers["authorization"] == "test-key-123"
        client.close()

    def test_content_type_header(self):
        client = make_nuclino_client("test-key-123")
        assert client.headers["content-type"] == "application/json"
        client.close()


# --- Workspace resolution ---


class TestResolveWorkspace:
    @patch("sync.api_request")
    def test_match_by_id(self, mock_api):
        mock_api.return_value = {"results": [{"id": "ws-123", "name": "My Workspace"}]}
        client = MagicMock()
        result = resolve_workspace(client, "ws-123")
        assert result == "ws-123"

    @patch("sync.api_request")
    def test_match_by_name_case_insensitive(self, mock_api):
        mock_api.return_value = {"results": [{"id": "ws-123", "name": "My Workspace"}]}
        client = MagicMock()
        result = resolve_workspace(client, "my workspace")
        assert result == "ws-123"

    @patch("sync.api_request")
    def test_no_match_empty_list(self, mock_api):
        mock_api.return_value = {"results": []}
        client = MagicMock()
        with pytest.raises(typer.BadParameter):
            resolve_workspace(client, "nonexistent")


# --- Collection creation ---


class TestEnsureCollection:
    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_creates_account_collection_with_workspace_id(self, mock_api, mock_save):
        mock_api.return_value = {"id": "col-1"}
        state = {"version": 1, "items": {}}
        state_path = Path("/tmp/state.json")
        client = MagicMock()

        ensure_collection(client, "ws-1", "iCloud", "Notes", state, state_path)

        # First call: account-level with workspaceId
        first_call = mock_api.call_args_list[0]
        assert first_call[0][1] == "POST"
        assert first_call[0][2] == "/v0/items"
        assert first_call[1]["json"]["workspaceId"] == "ws-1"
        assert first_call[1]["json"]["object"] == "collection"
        assert first_call[1]["json"]["title"] == "iCloud"
        assert "parentId" not in first_call[1]["json"]

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_creates_folder_collection_with_parent_id(self, mock_api, mock_save):
        # State already has account collection but not folder
        state = {"version": 1, "items": {}, "collections": {"iCloud": "col-acct"}}
        state_path = Path("/tmp/state.json")
        client = MagicMock()
        mock_api.return_value = {"id": "col-folder"}

        ensure_collection(client, "ws-1", "iCloud", "Notes", state, state_path)

        # Should only create folder-level (account already exists)
        assert mock_api.call_count == 1
        folder_call = mock_api.call_args_list[0]
        assert folder_call[1]["json"]["parentId"] == "col-acct"
        assert folder_call[1]["json"]["object"] == "collection"
        assert folder_call[1]["json"]["title"] == "Notes"
        assert "workspaceId" not in folder_call[1]["json"]

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_idempotent_from_state(self, mock_api, mock_save):
        state = {
            "version": 1,
            "items": {},
            "collections": {"iCloud": "col-1", "iCloud/Notes": "col-2"},
        }
        state_path = Path("/tmp/state.json")
        client = MagicMock()

        result = ensure_collection(client, "ws-1", "iCloud", "Notes", state, state_path)

        assert result == "col-2"
        mock_api.assert_not_called()

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_cross_account_keys(self, mock_api, mock_save):
        # Both accounts have "Notes" folder but should be separate keys
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return {"id": f"col-{call_count[0]}"}

        mock_api.side_effect = side_effect
        state = {"version": 1, "items": {}}
        state_path = Path("/tmp/state.json")
        client = MagicMock()

        id1 = ensure_collection(client, "ws-1", "iCloud", "Notes", state, state_path)
        id2 = ensure_collection(client, "ws-1", "anders@thib.se", "Notes", state, state_path)

        assert id1 != id2
        assert "iCloud/Notes" in state["collections"]
        assert "anders@thib.se/Notes" in state["collections"]


# --- Import loop ---


class TestRunImport:
    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_skips_already_imported(self, mock_api, mock_save, sample_export):
        # Pre-populate state with one note already imported
        state_path = sample_export / "nuclino-state.json"
        state = {
            "version": 1,
            "items": {
                "iCloud/Notes/Note.md": {
                    "status": "imported",
                    "title": "Note",
                    "nuclino_item_id": "existing-id",
                    "nuclino_collection_id": "col-1",
                },
            },
            "collections": {"iCloud": "col-acct", "iCloud/Notes": "col-1"},
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

        # Mock api_request for any non-skipped notes
        mock_api.return_value = {"id": "new-id"}

        client = MagicMock()
        run_import(sample_export, "ws-1", client)

        # api_request should NOT be called with Note.md's data
        # (it was already imported). It may be called for My-Note.md though.
        for c in mock_api.call_args_list:
            if len(c[0]) > 2 and "json" in (c[1] if c[1] else {}):
                json_data = c[1].get("json", {})
                if json_data.get("object") == "item":
                    assert json_data.get("title") != "Note"

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_records_failure(self, mock_api, mock_save, sample_export):
        # Make api_request raise on item creation
        def side_effect(client, method, path, **kwargs):
            json_data = kwargs.get("json", {})
            if json_data.get("object") == "collection":
                return {"id": "col-1"}
            # Raise for item creation
            response = MagicMock()
            response.status_code = 500
            raise httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=response,
            )

        mock_api.side_effect = side_effect

        client = MagicMock()
        run_import(sample_export, "ws-1", client)

        # Check that save_state was called with a failed status
        failed_saves = [
            c for c in mock_save.call_args_list
            if any(
                v.get("status") == "failed"
                for v in c[0][0].get("items", {}).values()
                if isinstance(v, dict)
            )
        ]
        assert len(failed_saves) > 0

        # Verify the error field is present
        last_failed_state = failed_saves[-1][0][0]
        failed_items = [
            v for v in last_failed_state["items"].values()
            if isinstance(v, dict) and v.get("status") == "failed"
        ]
        assert len(failed_items) > 0
        assert "error" in failed_items[0]

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_summary_output(self, mock_api, mock_save, sample_export, capsys):
        # Mock all API calls to succeed
        call_count = [0]

        def side_effect(client, method, path, **kwargs):
            call_count[0] += 1
            return {"id": f"item-{call_count[0]}"}

        mock_api.side_effect = side_effect

        client = MagicMock()
        run_import(sample_export, "ws-1", client)

        output = capsys.readouterr().out
        # sample_export has 2 canonical notes with content (Note.md, My-Note.md)
        # and 1 empty note (Empty.md) which is skipped
        assert "Imported 2 notes." in output
        assert "0 failed." in output


# --- Attachment upload ---


class TestUploadAttachments:
    """Tests for upload_attachments function (ATT-01, ATT-02)."""

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_upload_success_image_and_file(self, mock_api, mock_save, tmp_path):
        """Test 1: Uploads each file via POST, appends Markdown links via GET+PUT."""
        import sync

        sync._upload_not_supported = False

        att_dir = tmp_path / "attachments"
        att_dir.mkdir()
        (att_dir / "image.png").write_bytes(b"\x89PNG fake")
        (att_dir / "readme.pdf").write_bytes(b"%PDF fake")

        client = MagicMock()
        # Mock client.post for file uploads
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {"data": {"id": "file-1"}}
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"data": {"id": "file-2"}}
        client.post.side_effect = [mock_resp1, mock_resp2]

        # Mock api_request for GET (current content) and PUT (update)
        mock_api.side_effect = [
            {"content": "Original body"},  # GET item
            {},  # PUT item
        ]

        state_entry = {"status": "imported"}
        state = {"items": {"note.md": state_entry}}
        state_path = tmp_path / "state.json"

        upload_attachments(client, "item-1", att_dir, state_entry, state, state_path)

        # Verify client.post was called twice (once per file)
        assert client.post.call_count == 2

        # Verify Content-Type: None was passed to override default
        for post_call in client.post.call_args_list:
            assert post_call[1]["headers"] == {"Content-Type": None}

        # Verify GET+PUT for content update
        assert mock_api.call_count == 2
        get_call = mock_api.call_args_list[0]
        assert get_call[0][1] == "GET"
        assert "item-1" in get_call[0][2]

        put_call = mock_api.call_args_list[1]
        assert put_call[0][1] == "PUT"
        content = put_call[1]["json"]["content"]
        assert "Original body" in content
        # image.png should use ![name](url) syntax
        assert "![image.png]" in content
        # readme.pdf should use [name](url) syntax
        assert "[readme.pdf]" in content
        assert "![readme.pdf]" not in content

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_per_file_failure_isolation(self, mock_api, mock_save, tmp_path):
        """Test 2: One file fails, others still upload and get linked."""
        import sync

        sync._upload_not_supported = False

        att_dir = tmp_path / "attachments"
        att_dir.mkdir()
        (att_dir / "bad.png").write_bytes(b"bad")
        (att_dir / "good.jpg").write_bytes(b"good")

        client = MagicMock()
        # First file fails, second succeeds
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 500
        mock_resp_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_resp_fail,
        )
        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"data": {"id": "file-ok"}}
        client.post.side_effect = [mock_resp_fail, mock_resp_ok]

        # GET+PUT for the one successful file
        mock_api.side_effect = [
            {"content": "Body"},
            {},
        ]

        state_entry = {"status": "imported"}
        state = {"items": {"note.md": state_entry}}
        state_path = tmp_path / "state.json"

        upload_attachments(client, "item-1", att_dir, state_entry, state, state_path)

        # Verify failure was recorded
        assert "attachment_failures" in state_entry
        assert len(state_entry["attachment_failures"]) == 1
        assert state_entry["attachment_failures"][0]["file"] == "bad.png"

        # Verify the successful file was still linked
        put_call = mock_api.call_args_list[1]
        content = put_call[1]["json"]["content"]
        assert "![good.jpg]" in content

        # Verify state was saved (for failure recording)
        mock_save.assert_called()

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_404_skip_all(self, mock_api, mock_save, tmp_path):
        """Test 3: 404 on first POST sets flag and skips all remaining uploads."""
        import sync

        sync._upload_not_supported = False

        att_dir = tmp_path / "attachments"
        att_dir.mkdir()
        (att_dir / "file1.png").write_bytes(b"data1")
        (att_dir / "file2.png").write_bytes(b"data2")

        client = MagicMock()
        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404
        client.post.return_value = mock_resp_404

        state_entry = {"status": "imported"}
        state = {"items": {"note.md": state_entry}}
        state_path = tmp_path / "state.json"

        upload_attachments(client, "item-1", att_dir, state_entry, state, state_path)

        # Flag should be set
        assert sync._upload_not_supported is True

        # Only 1 POST call (returned early after 404)
        assert client.post.call_count == 1

        # No GET/PUT calls (no content update)
        mock_api.assert_not_called()

        # Second call should return immediately due to flag
        client.post.reset_mock()
        att_dir2 = tmp_path / "att2"
        att_dir2.mkdir()
        (att_dir2 / "file3.png").write_bytes(b"data3")

        upload_attachments(client, "item-2", att_dir2, {}, state, state_path)
        client.post.assert_not_called()

        # Reset flag for other tests
        sync._upload_not_supported = False

    @patch("sync.upload_attachments")
    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_run_import_with_attachment_dir(self, mock_api, mock_save, mock_upload, sample_export):
        """Test 4: run_import calls upload_attachments AFTER state save for notes with attachments."""
        call_count = [0]

        def api_side_effect(client, method, path, **kwargs):
            call_count[0] += 1
            return {"id": f"item-{call_count[0]}"}

        mock_api.side_effect = api_side_effect

        client = MagicMock()
        run_import(sample_export, "ws-1", client)

        # upload_attachments should have been called for Note.md (which has attachment_dir)
        assert mock_upload.call_count >= 1

        # Verify it was called with the right item_id and attachment_dir
        upload_call = mock_upload.call_args_list[0]
        # First positional args: client, item_id, attachment_dir, state_entry, state, state_path
        assert upload_call[0][0] is client  # client
        assert isinstance(upload_call[0][2], Path)  # attachment_dir
        assert upload_call[0][2].name == "Note"  # attachment dir for Note.md

    @patch("sync.save_state")
    @patch("sync.api_request")
    def test_content_type_override(self, mock_api, mock_save, tmp_path):
        """Test 5: POST /v0/files passes Content-Type: None to override client default."""
        import sync

        sync._upload_not_supported = False

        att_dir = tmp_path / "attachments"
        att_dir.mkdir()
        (att_dir / "doc.txt").write_bytes(b"hello")

        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"id": "file-1"}}
        client.post.return_value = mock_resp

        mock_api.side_effect = [
            {"content": "Body"},
            {},
        ]

        state_entry = {"status": "imported"}
        state = {"items": {"note.md": state_entry}}
        state_path = tmp_path / "state.json"

        upload_attachments(client, "item-1", att_dir, state_entry, state, state_path)

        # Verify Content-Type: None was passed
        post_call = client.post.call_args
        assert post_call[1]["headers"] == {"Content-Type": None}

        # Verify it used files= parameter (multipart)
        assert "files" in post_call[1]
