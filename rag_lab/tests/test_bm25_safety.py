from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vss_rag import incremental, lexical
from vss_rag.store import (ChunkScanError, ChunkScanMismatch,
                           DuplicateChunkId, Store)


class FakeCollection:
    def __init__(self, rows: list[dict], *, fail_offset: int | None = None):
        self.rows = rows
        self.fail_offset = fail_offset
        self.calls: list[tuple[int, int]] = []

    def count(self):
        return len(self.rows)

    def get(self, *, limit, offset, include):
        del include
        self.calls.append((offset, limit))
        if self.fail_offset is not None and offset >= self.fail_offset:
            raise RuntimeError("simulated Chroma page failure")
        page = self.rows[offset:offset + limit]
        return {
            "ids": [row["_id"] for row in page],
            "documents": [row["text"] for row in page],
            "metadatas": [{"path": row["path"], "section": row.get("section")}
                          for row in page],
        }


class FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, project_id):
        del project_id
        return self.collection


def make_store(collection) -> Store:
    store = Store.__new__(Store)
    store._client = FakeClient(collection)
    return store


def rows(count: int) -> list[dict]:
    return [
        {"_id": f"p:file.py:{i}", "text": f"token {i}",
         "path": "file.py", "section": None}
        for i in range(count)
    ]


class ChunkPaginationTests(unittest.TestCase):
    def test_iter_chunks_reads_large_collection_in_bounded_pages(self):
        collection = FakeCollection(rows(1203))
        got = list(make_store(collection).iter_chunks("p", batch_size=500))

        self.assertEqual(len(got), 1203)
        self.assertEqual(collection.calls, [(0, 500), (500, 500), (1000, 203)])
        self.assertTrue(all(limit <= 500 for _, limit in collection.calls))

    def test_page_failure_is_not_converted_to_empty_index(self):
        collection = FakeCollection(rows(700), fail_offset=500)
        store = make_store(collection)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bm25.json"
            target.write_text("previous-index", encoding="utf-8")

            with self.assertRaises(ChunkScanError):
                lexical.build(
                    "p", store.iter_chunks("p", batch_size=500),
                    path=target, expected_count=700)

            self.assertEqual(target.read_text(encoding="utf-8"), "previous-index")

    def test_duplicate_id_across_pages_is_rejected(self):
        data = rows(501)
        data[500] = dict(data[0])
        store = make_store(FakeCollection(data))

        with self.assertRaises(DuplicateChunkId):
            list(store.iter_chunks("p", batch_size=500))

    def test_count_change_during_scan_is_rejected(self):
        class ChangingCountCollection(FakeCollection):
            def __init__(self):
                super().__init__(rows(2))
                self.count_calls = 0

            def count(self):
                self.count_calls += 1
                return 2 if self.count_calls == 1 else 3

        with self.assertRaises(ChunkScanMismatch):
            list(make_store(ChangingCountCollection()).iter_chunks("p"))

    def test_expected_count_mismatch_does_not_replace_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bm25.json"
            target.write_text("previous-index", encoding="utf-8")

            with self.assertRaises(lexical.BM25BuildError):
                lexical.build("p", iter(rows(2)), path=target, expected_count=3)

            self.assertEqual(target.read_text(encoding="utf-8"), "previous-index")


class IncrementalAtomicityTests(unittest.TestCase):
    class FakeStore:
        def __init__(self, fingerprint: dict):
            self.rows = [{
                "_id": "p:a.py:0", "text": "old", "path": "a.py",
                "section": None, "metadata": {"path": "a.py", "section": ""},
                "embedding": [1.0],
            }]
            self.fingerprint = fingerprint
            self.set_calls = 0

        def index_fingerprint(self, project_id):
            del project_id
            return self.fingerprint

        def snapshot_by_paths(self, project_id, paths):
            del project_id
            selected = [row for row in self.rows if row["path"] in paths]
            return {
                "ids": [row["_id"] for row in selected],
                "documents": [row["text"] for row in selected],
                "metadatas": [dict(row["metadata"]) for row in selected],
                "embeddings": [list(row["embedding"]) for row in selected],
            }

        def delete_by_paths(self, project_id, paths):
            del project_id
            self.rows = [row for row in self.rows if row["path"] not in paths]
            return len(paths)

        def add(self, project_id, chunks, vectors):
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                self.rows.append({
                    "_id": f"{project_id}:{chunk['path']}:{i}",
                    "text": chunk["text"], "path": chunk["path"],
                    "section": chunk.get("section"),
                    "metadata": {"path": chunk["path"],
                                 "section": chunk.get("section") or ""},
                    "embedding": list(vector),
                })

        def restore_snapshot(self, project_id, snapshot):
            del project_id
            for cid, text, meta, vector in zip(
                    snapshot["ids"], snapshot["documents"],
                    snapshot["metadatas"], snapshot["embeddings"]):
                self.rows.append({
                    "_id": cid, "text": text, "path": meta["path"],
                    "section": meta.get("section"), "metadata": dict(meta),
                    "embedding": list(vector),
                })

        def iter_chunks(self, project_id):
            del project_id
            for row in self.rows:
                yield {key: row[key] for key in ("_id", "text", "path", "section")}

        def count(self, project_id):
            del project_id
            return len(self.rows)

        def set_index_fingerprint(self, project_id, fingerprint):
            del project_id
            self.set_calls += 1
            if self.set_calls == 1:
                raise RuntimeError("simulated metadata commit failure")
            self.fingerprint = fingerprint

    def test_failure_after_bm25_commit_restores_vectors_and_previous_bm25(self):
        profile = {
            "chunk_size": 1500, "chunk_overlap": 200,
            "embed_model": "bge-m3:latest", "embed_dim": 1024,
            "distance_metric": "cosine", "context_header": False,
            "use_bm25": True, "exclude_globs": "",
            "max_file_bytes": 2_000_000,
        }
        store = self.FakeStore(profile)
        old_rows = [dict(store.rows[0])]
        new_chunk = {
            "path": "a.py", "type": "code", "text": "new",
            "section": None, "chunk_index": 0,
        }
        plan = {
            "ok": True, "old_commit": "a" * 40, "new_commit": "b" * 40,
            "to_index": ["a.py"], "to_delete": ["a.py"],
            "changes": {"deleted": [], "renamed": []},
            "fingerprint": profile,
        }

        with tempfile.TemporaryDirectory() as tmp:
            final = Path(tmp) / "p.json"
            staged = Path(tmp) / "building-p.json"
            final.write_text("previous-index", encoding="utf-8")
            with (patch.object(incremental, "can_update", return_value=plan),
                  patch.object(incremental, "chunk_file", return_value=[new_chunk]),
                  patch.object(incremental, "embed_many", return_value=[[2.0]]),
                  patch.object(incremental.lexical, "index_path", return_value=final),
                  patch.object(incremental.lexical, "staging_path", return_value=staged)):
                with self.assertRaises(incremental.IncrementalApplyError) as caught:
                    incremental.update(".", "p", store, {"state": "done"})

            self.assertTrue(caught.exception.rollback_ok)
            self.assertEqual(final.read_text(encoding="utf-8"), "previous-index")
            self.assertEqual(len(store.rows), 1)
            self.assertEqual(store.rows[0]["_id"], old_rows[0]["_id"])
            self.assertEqual(store.rows[0]["text"], "old")


if __name__ == "__main__":
    unittest.main()
