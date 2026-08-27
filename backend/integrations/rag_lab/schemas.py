"""Schemas owned by the Model/RAG Lab HTTP boundary."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.features.workspace_overlays.validation import (
    validate_git_revision,
    validate_posix_relative_path,
    validate_sha256,
)

GitRevision = Annotated[str, AfterValidator(validate_git_revision)]
PosixRelativePath = Annotated[str, AfterValidator(validate_posix_relative_path)]
ContentSha256 = Annotated[str, AfterValidator(validate_sha256)]


class RagLabIndexUpdateFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["added", "modified", "renamed"]
    path: PosixRelativePath
    content: str
    encoding: Literal["utf-8", "utf-8-sig", "cp949", "latin-1"] = "utf-8"
    content_sha256: ContentSha256 | None = None
    size_bytes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def supplied_content_metadata_must_match(self) -> Self:
        try:
            encoded = self.content.encode(self.encoding)
        except UnicodeEncodeError as exc:
            raise ValueError(f"content cannot be encoded as {self.encoding}") from exc

        if self.size_bytes is not None and self.size_bytes != len(encoded):
            raise ValueError("size_bytes does not match encoded content")
        if self.content_sha256 is not None:
            actual = hashlib.sha256(encoded).hexdigest()
            if self.content_sha256.lower() != actual:
                raise ValueError("content_sha256 does not match encoded content")
        return self


class RagLabIndexUpdateRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_path: PosixRelativePath
    new_path: PosixRelativePath

    @model_validator(mode="after")
    def paths_must_differ(self) -> Self:
        if self.old_path == self.new_path:
            raise ValueError("old_path and new_path must differ")
        return self


class RagLabIndexUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    base_revision: GitRevision
    target_revision: GitRevision
    snapshot_id: str | None = Field(default=None, min_length=1, max_length=512)
    branch: str | None = Field(default=None, min_length=1, max_length=512)
    files: list[RagLabIndexUpdateFile]
    deleted_paths: list[PosixRelativePath]
    renames: list[RagLabIndexUpdateRename]

    @field_validator("project_id")
    @classmethod
    def project_id_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project_id must not be blank")
        return normalized

    @field_validator("snapshot_id", "branch")
    @classmethod
    def optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_cross_field_path_rules(self) -> Self:
        file_paths = [item.path for item in self.files]
        deleted_paths = self.deleted_paths
        rename_old_paths = [item.old_path for item in self.renames]
        rename_new_paths = [item.new_path for item in self.renames]

        if len(file_paths) != len(set(file_paths)):
            raise ValueError("files contains duplicate paths")
        if len(deleted_paths) != len(set(deleted_paths)):
            raise ValueError("deleted_paths contains duplicate paths")
        if len(rename_old_paths) != len(set(rename_old_paths)):
            raise ValueError("renames contains duplicate old_path values")
        if len(rename_new_paths) != len(set(rename_new_paths)):
            raise ValueError("renames contains duplicate new_path values")

        file_path_set = set(file_paths)
        conflict = file_path_set & set(deleted_paths)
        if conflict:
            raise ValueError(f"paths cannot be both changed and deleted: {sorted(conflict)}")

        missing = set(rename_new_paths) - file_path_set
        if missing:
            raise ValueError(f"rename destinations require final content: {sorted(missing)}")
        return self


class RagLabIndexUpdateResponse(BaseModel):
    """Preserve Model-owned fields, including fields added in later revisions."""

    model_config = ConfigDict(extra="allow")

    ok: bool
    project_id: str | None = None
    state: str | None = None
    reason: str | None = None
    detail: str | None = None
    conflict: bool | None = None
    already_applied: bool | None = None
    base_revision: GitRevision | None = None
    target_revision: GitRevision | None = None


class RagLabProject(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str
    state: str | None = None
    commit: GitRevision | None = None


class RagLabProjectsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    projects: list[RagLabProject]


class RagLabIndexStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str
    state: str
    commit: GitRevision | None = None
    update_error: Any | None = None
