import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vss_rag import indexer, profiles
from vss_rag import lexical
from vss_rag.experiments.runner import validate_matrix
from vss_rag.experiments.suite import ValidationError, load_questions
from vss_rag.store import Store


ROOT = Path(__file__).resolve().parent.parent


class ProfileRegistryTests(unittest.TestCase):
    def test_rag_versions_change_one_major_condition_at_a_time(self):
        v1 = profiles.resolve_profile("rag-v1")
        v2 = profiles.resolve_profile("rag-v2")
        v3 = profiles.resolve_profile("rag-v3")

        def changed(a, b):
            return {k for k in a if a[k] != b[k]}

        self.assertEqual(changed(v1["fingerprint"], v2["fingerprint"]), {"use_bm25"})
        self.assertEqual(changed(v2["fingerprint"], v3["fingerprint"]), {"context_header"})
        self.assertEqual(len({v1["profile_hash"], v2["profile_hash"], v3["profile_hash"]}), 3)

    def test_project_id_combines_repository_and_version(self):
        self.assertEqual(profiles.project_id_for("C:/Pj/fest-api", "rag-v3"),
                         "fest-api--rag-v3")


class SuiteValidationTests(unittest.TestCase):
    def test_person_or_llm_jsonl_is_validated_against_repository(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("def start():\n    pass\n", encoding="utf-8")
            suite = root / "suite.jsonl"
            suite.write_text(json.dumps({
                "id": "entry-001", "question": "진입점은?", "answerable": True,
                "gold": [{"path": "src/app.py", "line_start": 1, "line_end": 2,
                          "symbol": "start"}],
                "tags": ["architecture", "korean"],
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            rows = load_questions(suite, repository=root)
            self.assertEqual(rows[0]["id"], "entry-001")

    def test_answerable_question_without_gold_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "bad.jsonl"
            suite.write_text(json.dumps({
                "id": "bad-1", "question": "어디?", "answerable": True,
                "gold": [], "tags": ["semantic"],
            }, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_questions(suite, repository=root)


class MatrixTests(unittest.TestCase):
    def test_default_matrix_has_requested_five_cells(self):
        spec = validate_matrix(ROOT / "evaluation" / "matrices" / "fest-api-rag-v1-v3.json")
        cells = {(c["index_profile"], c["search_profile"]) for c in spec["cells"]}
        self.assertEqual(cells, {
            ("rag-v1", "vector"),
            ("rag-v2", "vector"), ("rag-v2", "hybrid"),
            ("rag-v3", "vector"), ("rag-v3", "hybrid"),
        })


class ExplicitIndexProfileTests(unittest.TestCase):
    def test_full_index_passes_explicit_profile_to_all_content_steps(self):
        fp = profiles.resolve_profile("rag-v1")["fingerprint"]

        class FakeStore:
            def begin_build(self, project_id, **kwargs):
                self.begin_kwargs = kwargs
                return "building-unit-profile"
            def add(self, project_id, chunks, vectors, id_prefix=None):
                self.added = (project_id, chunks, vectors, id_prefix)
            def promote(self, project_id, keep_previous=False):
                self.promoted = project_id
            def finish_promote(self, project_id):
                self.finished = project_id

        store = FakeStore()
        fake_file = Path("C:/tmp/repo/a.py")
        chunk = {"path": "a.py", "type": "code", "text": "def a(): pass", "chunk_index": 0}
        with (patch.object(indexer, "collect_files", return_value=[fake_file]) as collect,
              patch.object(indexer, "chunk_file", return_value=[chunk]) as chunk_file,
              patch.object(indexer, "embed_many", return_value=[[0.0] * 1024]) as embed,
              patch.object(indexer, "_update"),
              patch.object(indexer, "git_head", return_value="abc"),
              patch.object(indexer, "git_dirty", return_value=False)):
            indexer._run("C:/tmp/repo", "unit-profile", store, profile=fp,
                         profile_id="rag-v1", profile_hash="hash")

        collect.assert_called_once_with(Path("C:/tmp/repo").resolve(), fp)
        chunk_file.assert_called_once_with(fake_file, Path("C:/tmp/repo").resolve(), fp)
        self.assertEqual(embed.call_args.kwargs["model"], "bge-m3:latest")
        self.assertEqual(embed.call_args.kwargs["expected_dim"], 1024)
        self.assertEqual(store.begin_kwargs["fingerprint"], fp)
        self.assertEqual(store.promoted, "unit-profile")
        self.assertEqual(store.finished, "unit-profile")

    def test_hybrid_profile_does_not_promote_when_bm25_count_mismatches(self):
        fp = profiles.resolve_profile("rag-v2")["fingerprint"]

        class FakeStore:
            promoted = False
            def begin_build(self, project_id, **kwargs): return "building-unit-hybrid"
            def add(self, project_id, chunks, vectors, id_prefix=None): pass
            def all_chunks(self, project_id):
                return [{"_id": "one", "path": "a.py", "text": "a", "section": None}]
            def promote(self, project_id): self.promoted = True

        class BadIndex:
            doc_ids = []

        store = FakeStore()
        chunk = {"path": "a.py", "type": "code", "text": "def a(): pass", "chunk_index": 0}
        with TemporaryDirectory() as tmp:
            staging = Path(tmp) / "building.json"
            with (patch.object(indexer, "collect_files", return_value=[Path("a.py")]),
                  patch.object(indexer, "chunk_file", return_value=[chunk]),
                  patch.object(indexer, "embed_many", return_value=[[0.0] * 1024]),
                  patch.object(indexer, "_update"),
                  patch.object(indexer, "git_head", return_value="abc"),
                  patch.object(indexer, "git_dirty", return_value=False),
                  patch.object(indexer.lexical, "staging_path", return_value=staging),
                  patch.object(indexer.lexical, "build", return_value=BadIndex()),
                  patch("builtins.print")):
                with self.assertRaisesRegex(RuntimeError, "BM25 문서 수 불일치"):
                    indexer._run(".", "unit-hybrid", store, profile=fp,
                                 profile_id="rag-v2", profile_hash="hash")
        self.assertFalse(store.promoted)

    def test_small_hybrid_index_builds_matching_vector_and_bm25(self):
        fp = profiles.resolve_profile("rag-v2")["fingerprint"]
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            (repo / "app.py").write_text(
                "def alpha_router():\n" + "    return 'alpha router registration'\n" * 8,
                encoding="utf-8")
            index_dir = base / "data" / "index"
            state_path = base / "data" / "state.json"
            store = Store(str(index_dir))

            def fake_embed(texts, **kwargs):
                return [[1.0] + [0.0] * 1023 for _ in texts]

            with (patch.object(indexer.CFG, "state_path", str(state_path)),
                  patch.object(lexical.CFG, "index_dir", str(index_dir)),
                  patch.object(indexer, "embed_many", side_effect=fake_embed),
                  patch.object(indexer, "git_head", return_value="abc"),
                  patch.object(indexer, "git_dirty", return_value=False)):
                indexer._run(repo, "tiny--rag-v2", store, profile=fp,
                             profile_id="rag-v2", profile_hash="hash")
                chunks = store.count("tiny--rag-v2")
                self.assertGreater(chunks, 0)
                self.assertEqual(lexical.doc_count("tiny--rag-v2"), chunks)
                self.assertEqual(store.index_fingerprint("tiny--rag-v2"), fp)
            store._client.close()


if __name__ == "__main__":
    unittest.main()
