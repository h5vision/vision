"""Explicit conversion from the Frontend contract to the RAG Lab contract."""

from __future__ import annotations

from backend.features.workspace_overlays.schemas import WorkspaceOverlayRequest
from backend.integrations.rag_lab.schemas import (
    RagLabIndexUpdateFile,
    RagLabIndexUpdateRename,
    RagLabIndexUpdateRequest,
)


def to_rag_lab_update_request(
    request: WorkspaceOverlayRequest,
    *,
    model_project_id: str,
    snapshot_id: str | None = None,
    branch_ref: str | None = None,
) -> RagLabIndexUpdateRequest:
    """Map fields without hashing content or changing revision/path semantics."""

    return RagLabIndexUpdateRequest(
        project_id=model_project_id,
        base_revision=request.base_revision,
        target_revision=request.target_revision,
        snapshot_id=snapshot_id,
        branch=branch_ref,
        files=[
            RagLabIndexUpdateFile(
                status=item.status,
                path=item.path,
                content=item.content,
                encoding=item.encoding,
            )
            for item in request.files
        ],
        deleted_paths=list(request.deleted_paths),
        renames=[
            RagLabIndexUpdateRename(old_path=item.old_path, new_path=item.new_path)
            for item in request.renames
        ],
    )
