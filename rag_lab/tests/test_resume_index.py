from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vss_rag.config import CFG
from vss_rag.resume.checkpoint import CheckpointStore
from vss_rag.resume.engine import ResumableIndexer
from vss_rag.resume.manifest import build_manifest


class FakeStore:
    """실제 Chroma 디렉터리를 열지 않는 resume 엔진 테스트 저장소."""

    def __init__(self):
        self.collections: dict[str, dict] = {}

    def collection_info(self, name):
        row = self.collections.get(name)
        if row is None:
            return None
        return {"name": name, "chunks": sum(row["paths"].values()),
                "metadata": dict(row["metadata"])}

    def begin_build(self, project_id, **kwargs):
        name = "building-" + project_id
        self.collections[name] = {
            "paths": {},
            "metadata": {
                "status": "building", "target": project_id,
                "run_id": kwargs.get("run_id"),
                "manifest_hash": kwargs.get("manifest_hash"),
            },
        }
        return name

    def open_build(self, project_id, *, expected_run_id):
        name = "building-" + project_id
        info = self.collection_info(name)
        if not info or info["metadata"].get("run_id") != expected_run_id:
            raise RuntimeError("bad building run")
        return name

    def delete_by_paths(self, collection_name, paths):
        for path in paths:
            self.collections[collection_name]["paths"].pop(path, None)
        return len(paths)

    def add(self, collection_name, chunks, vectors, id_prefix=None):
        del vectors, id_prefix
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk["path"]] = counts.get(chunk["path"], 0) + 1
        self.collections[collection_name]["paths"].update(counts)

    def path_chunk_count(self, collection_name, path):
        return self.collections[collection_name]["paths"].get(path, 0)

    def count(self, collection_name):
        return sum(self.collections[collection_name]["paths"].values())

    def all_chunks(self, collection_name):
        del collection_name
        return []

    def promote_resumable(self, project_id, *, expected_run_id):
        build = "building-" + project_id
        if project_id in self.collections:
            self.collections[project_id + "-prev"] = self.collections.pop(project_id)
        row = self.collections.pop(build)
        if row["metadata"].get("run_id") != expected_run_id:
            raise RuntimeError("bad promotion run")
        row["metadata"]["status"] = "ready"
        self.collections[project_id] = row

    def finish_promote(self, project_id):
        self.collections.pop(project_id + "-prev", None)

    def rollback_promote(self, project_id):
        build = "building-" + project_id
        if project_id in self.collections:
            self.collections[build] = self.collections.pop(project_id)
        if project_id + "-prev" in self.collections:
            self.collections[project_id] = self.collections.pop(project_id + "-prev")

    def reset(self, name):
        self.collections.pop(name, None)


class ResumeIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        (self.root / "one.py").write_text("def one():\n    return 'one'\n" * 8,
                                           encoding="utf-8")
        (self.root / "two.py").write_text("def two():\n    return 'two'\n" * 8,
                                           encoding="utf-8")
        self.db = Path(self.tmp.name) / "resume.sqlite3"
        self.profile = CFG.fingerprint()
        self.profile["use_bm25"] = False

    def tearDown(self):
        self.tmp.cleanup()

    def test_manifest_changes_when_source_changes(self):
        before = build_manifest(self.root, self.profile)
        (self.root / "one.py").write_text("def changed():\n    return 1\n" * 8,
                                           encoding="utf-8")
        after = build_manifest(self.root, self.profile)
        self.assertNotEqual(before.digest, after.digest)

    def test_interrupted_run_resumes_without_reembedding_completed_file(self):
        checkpoints = CheckpointStore(self.db)
        store = FakeStore()
        calls = {"count": 0}

        def failing_embed(texts, **kwargs):
            del kwargs
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("forced interruption")
            return [[0.0] * 1024 for _ in texts]

        no_state = patch("vss_rag.resume.engine.indexer.update_state")
        no_head = patch("vss_rag.resume.engine.indexer.git_head",
                        return_value="a" * 40)
        no_dirty = patch("vss_rag.resume.engine.indexer.git_dirty",
                         return_value=False)
        finish_hook = patch(
            "vss_rag.resume.engine.indexer.run_completion_hook",
            side_effect=lambda pid, root, commit, hook: (
                hook(pid, root, commit) if hook else None),
        )
        with no_state, no_head, no_dirty, finish_hook:
            engine = ResumableIndexer(
                checkpoints=checkpoints, store=store,
                embed_fn=failing_embed, batch_chunks=1,
            )
            with self.assertRaisesRegex(RuntimeError, "forced interruption"):
                engine.start_new(
                    str(self.root), "demo", blocking=True,
                    profile=self.profile,
                    on_done=lambda *_: {"ok": True},
                )

            interrupted = checkpoints.latest("demo", active_only=True)
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertEqual(interrupted["completed_files"], 1)

            resumed_calls = {"count": 0}

            def resumed_embed(texts, **kwargs):
                del kwargs
                resumed_calls["count"] += 1
                return [[0.0] * 1024 for _ in texts]

            resumed = ResumableIndexer(
                checkpoints=checkpoints, store=store,
                embed_fn=resumed_embed, batch_chunks=1,
            )
            result = resumed.resume(
                "demo", blocking=True, force=True,
                on_done=lambda *_: {"ok": True},
            )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["state"], "complete")
        self.assertEqual(resumed_calls["count"], 1)
        self.assertIsNotNone(store.collection_info("demo"))
        self.assertIsNone(store.collection_info("building-demo"))
        final = checkpoints.latest("demo")
        self.assertEqual(final["completed_files"], 2)
        self.assertEqual(final["status"], "complete")


if __name__ == "__main__":
    unittest.main()
