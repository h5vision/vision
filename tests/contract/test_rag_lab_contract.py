from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.integrations.rag_lab.schemas import (
    RagLabIndexUpdateRequest,
    RagLabIndexUpdateResponse,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "model"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text("utf-8"))


def test_model_request_allows_model_owned_optional_fields() -> None:
    request = RagLabIndexUpdateRequest.model_validate(
        {
            "project_id": "vision--rag-v2",
            "base_revision": "1" * 40,
            "target_revision": "2" * 40,
            "snapshot_id": "internal-snapshot-id",
            "branch": "refs/heads/backend_P",
            "files": [
                {
                    "status": "renamed",
                    "path": "vision/src/new.ts",
                    "content": "최종 문자열",
                    "encoding": "utf-8",
                }
            ],
            "deleted_paths": [],
            "renames": [{"old_path": "vision/src/old.ts", "new_path": "vision/src/new.ts"}],
        }
    )

    assert request.snapshot_id == "internal-snapshot-id"
    assert request.branch == "refs/heads/backend_P"


def test_accepted_response_preserves_model_extra_fields() -> None:
    payload = load_fixture("update_accepted.json")

    response = RagLabIndexUpdateResponse.model_validate(payload)

    assert response.model_dump()["files_received"] == 1
    assert response.model_dump()["ignored_paths"] == []


def test_already_applied_response_preserves_commit() -> None:
    payload = load_fixture("already_applied.json")

    response = RagLabIndexUpdateResponse.model_validate(payload)

    assert response.already_applied is True
    assert response.model_dump()["commit"] == payload["commit"]


def test_conflict_response_preserves_reason_detail_and_conflict() -> None:
    payload = load_fixture("revision_conflict.json")

    response = RagLabIndexUpdateResponse.model_validate(payload)

    assert response.reason == "base_revision_mismatch"
    assert response.detail == payload["detail"]
    assert response.conflict is True
    assert response.model_dump()["current_revision"] == payload["current_revision"]


def test_model_request_rejects_incorrect_supplied_content_metadata() -> None:
    payload = {
        "project_id": "vision--rag-v2",
        "base_revision": "1" * 40,
        "target_revision": "2" * 40,
        "files": [
            {
                "status": "modified",
                "path": "vision/src/file.ts",
                "content": "full content",
                "encoding": "utf-8",
                "content_sha256": "0" * 64,
                "size_bytes": 999,
            }
        ],
        "deleted_paths": [],
        "renames": [],
    }

    with pytest.raises(ValidationError):
        RagLabIndexUpdateRequest.model_validate(payload)


def test_model_request_rejects_duplicate_and_conflicting_paths() -> None:
    payload = {
        "project_id": "vision--rag-v2",
        "base_revision": "1" * 40,
        "target_revision": "2" * 40,
        "files": [
            {
                "status": "modified",
                "path": "vision/src/file.ts",
                "content": "full content",
                "encoding": "utf-8",
            }
        ],
        "deleted_paths": ["vision/src/file.ts"],
        "renames": [],
    }

    with pytest.raises(ValidationError, match="both changed and deleted"):
        RagLabIndexUpdateRequest.model_validate(payload)
