import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chronofile.repo import Repo
from chronofile.storage import ObjectStore


class TestObjectStore(unittest.TestCase):
    def test_dedup_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            store = ObjectStore(Path(d))
            h1 = store.write(b"hello world")
            h2 = store.write(b"hello world")
            h3 = store.write(b"something else")
            self.assertEqual(h1, h2)
            self.assertNotEqual(h1, h3)
            self.assertEqual(store.read(h1), b"hello world")


class TestRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmp.name)
        self.repo = Repo.init(self.workdir)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        (self.workdir / name).write_text(content)

    def test_new_and_modified_detection(self):
        self.write("a.txt", "version 1")
        changes = self.repo.snapshot()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, "new")

        # no changes -> empty snapshot
        self.assertEqual(self.repo.snapshot(), [])

        self.write("a.txt", "version 2")
        changes = self.repo.snapshot()
        self.assertEqual(changes[0].kind, "modified")

    def test_history_and_restore(self):
        self.write("a.txt", "v1")
        self.repo.snapshot()
        self.write("a.txt", "v2")
        self.repo.snapshot()
        self.write("a.txt", "v3")
        self.repo.snapshot()

        hist = self.repo.history("a.txt")
        self.assertEqual(len(hist), 3)

        self.repo.restore("a.txt", "1")  # back to v1
        self.assertEqual((self.workdir / "a.txt").read_text(), "v1")

        # restore only rewrites the working file; it shows up as a pending
        # "modified" change until the next snapshot is taken
        pending = [s for s in self.repo.status() if s.path == "a.txt"]
        self.assertEqual(pending[0].kind, "modified")

        self.repo.snapshot()
        hist_after = self.repo.history("a.txt")
        self.assertEqual(len(hist_after), 4)

    def test_deleted_file_detected(self):
        self.write("b.txt", "content")
        self.repo.snapshot()
        (self.workdir / "b.txt").unlink()
        changes = self.repo.snapshot()
        self.assertEqual(changes[0].kind, "deleted")

    def test_ignored_dirs_are_skipped(self):
        (self.workdir / ".chronofile" / "objects" / "junk.txt").parent.mkdir(parents=True, exist_ok=True)
        files = self.repo.walk_files()
        self.assertTrue(all(".chronofile" not in f for f in files))


if __name__ == "__main__":
    unittest.main()
