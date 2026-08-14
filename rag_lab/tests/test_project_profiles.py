import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vss_rag import incremental, searcher
from vss_rag.config import normalize_fingerprint


OLD_FP = {
    "embed_model": "bge-m3:latest",
    "chunk_size": 1200,
    "chunk_overlap": 150,
    "context_header": False,
    "use_bm25": False,
}


class FakeStore:
    def __init__(self, projects=None, fingerprint=None):
        self._projects = projects or []
        self._fingerprint = fingerprint

    def projects(self):
        return list(self._projects)

    def index_fingerprint(self, project_id):
        return self._fingerprint


class ProjectProfileTests(unittest.TestCase):
    def test_legacy_fingerprint_gets_historical_defaults(self):
        fp = normalize_fingerprint(OLD_FP)
        self.assertEqual(fp["exclude_globs"], "")
        self.assertEqual(fp["min_chunk_chars"], 80)
        self.assertEqual(fp["max_file_bytes"], 1_000_000)
        self.assertEqual(fp["embed_dim"], 1024)

    def test_serving_profile_uses_index_not_global_config(self):
        fp = normalize_fingerprint({**OLD_FP, "context_header": True,
                                    "use_bm25": True})
        store = FakeStore(["fest-api"], fp)
        self.assertEqual(searcher.serving_profile(store, "fest-api"), fp)

    def test_unknown_project_is_rejected_before_store_query(self):
        with self.assertRaises(searcher.ProjectNotFoundError):
            searcher.serving_profile(FakeStore(["fest-api"]), "typo")

    def test_incremental_plan_uses_saved_profile_despite_cfg_difference(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = {"state": "done", "commit": "abc", "fingerprint": OLD_FP}
            saved = normalize_fingerprint({**OLD_FP, "context_header": True,
                                           "use_bm25": True})
            with (patch.object(incremental, "_git", return_value="abc\n"),
                  patch.object(incremental, "detect_changes", return_value={
                      "modified": [], "added": [], "deleted": [], "renamed": []}),
                  patch.object(incremental, "collect_files",
                               return_value=[root / "README.md"])):
                plan = incremental.can_update(root, "fest-api", state,
                                              index_fp=saved)
            self.assertTrue(plan["ok"])
            self.assertTrue(plan["fingerprint"]["use_bm25"])
            self.assertTrue(plan["fingerprint"]["context_header"])


if __name__ == "__main__":
    unittest.main()
