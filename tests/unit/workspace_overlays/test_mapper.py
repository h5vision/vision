from __future__ import annotations

from backend.features.workspace_overlays.mapper import to_rag_lab_update_request
from backend.features.workspace_overlays.schemas import WorkspaceOverlayRequest


def test_mapper_preserves_full_content_paths_and_revisions() -> None:
    frontend = WorkspaceOverlayRequest.model_validate(
        {
            "project_id": "h5vision/vision",
            "base_revision": "A" * 40,
            "target_revision": "B" * 40,
            "files": [
                {
                    "status": "modified",
                    "path": "vision/src/file.ts",
                    "content": "전체 파일 문자열\n두 번째 줄",
                    "encoding": "utf-8",
                }
            ],
            "deleted_paths": [],
            "renames": [],
        }
    )

    model = to_rag_lab_update_request(
        frontend,
        model_project_id="vision--rag-v2",
        snapshot_id="snapshot-internal-id",
        branch_ref="refs/heads/backend_P",
    )

    assert model.project_id == "vision--rag-v2"
    assert model.base_revision == frontend.base_revision
    assert model.target_revision == frontend.target_revision
    assert model.files[0].content == frontend.files[0].content
    assert model.files[0].content_sha256 is None
    assert model.files[0].size_bytes is None
    assert model.snapshot_id == "snapshot-internal-id"
    assert model.branch == "refs/heads/backend_P"
