#!/usr/bin/env python3
"""Stdlib tests for nufi-ingest Public/Private accessibility enforcement."""
import json
import logging
import pathlib
import tempfile
import unittest

import nufi_ingest as I

logging.getLogger("nufi-ingest").addHandler(logging.NullHandler())
logging.getLogger("nufi-ingest").propagate = False


class FakeApp:
    def __init__(self):
        self.uploads, self.deletes, self.n = [], [], 0

    def upload(self, path, agent_id):
        self.n += 1
        self.uploads.append((pathlib.Path(path).name, agent_id))
        return f"f{self.n}", f"/p/{self.n}", True

    def delete(self, file_id, filepath, agent_id):
        self.deletes.append(file_id)

    def reconcile_agent(self, *a): pass
    def share_agent(self, *a): pass
    def find_or_create_team(self, name): return "t1"
    def find_or_create_agent(self, name, instr): return "a1", "oid1"


class AccessFnTests(unittest.TestCase):
    def test_effective_access(self):
        e = {"a": {"access": "private"}, "a/b": {"access": "public"},
             "a/b/own.pdf": {"access": "private"}}
        self.assertEqual(I.effective_access(e, "a/b/own.pdf"), "private")
        self.assertEqual(I.effective_access(e, "a/b/c.pdf"), "public")
        self.assertEqual(I.effective_access(e, "a/x.pdf"), "private")
        self.assertEqual(I.effective_access(e, "z/x.pdf"), "public")
        self.assertEqual(I.effective_access({}, "x.pdf"), "public")

    def test_load_access(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self.assertEqual(I.load_access(d), {})
            (d / I.ACCESS_FILE).write_text("{nope")
            self.assertEqual(I.load_access(d), {})
            (d / I.ACCESS_FILE).write_text("[1]")
            self.assertEqual(I.load_access(d), {})
            (d / I.ACCESS_FILE).write_text(json.dumps({"entries": {
                "ok": {"access": "private"}, "bad": {"access": "admin"},
                "__proto__": {"access": "nope"}, "str": "private"}}))
            self.assertEqual(I.load_access(d), {"ok": {"access": "private"}})
            self.assertEqual(I.effective_access(I.load_access(d), "bad"), "public")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.drives, self.state = root / "drives", root / "state"
        (self.drives / "eng" / "sub").mkdir(parents=True)
        self.dept = self.drives / "eng"
        (self.dept / "pub.txt").write_text("public")
        (self.dept / "sub" / "sec.txt").write_text("secret")
        cfg = I.Config(app_url="x", email="e", password="p", jwt_secret="s",
                       drives_dir=str(self.drives), state_dir=str(self.state),
                       model="m", settle_scans=1)
        self.app = FakeApp()
        self.ing = I.Ingester(cfg, app=self.app)

    def tearDown(self):
        self.tmp.cleanup()

    def set_access(self, entries):
        (self.dept / I.ACCESS_FILE).write_text(json.dumps({"entries": entries}))

    def names(self):
        return sorted(n for n, _ in self.app.uploads)

    def test_public_uploaded_private_not_and_dotfile_never(self):
        self.set_access({"sub": {"access": "private"}})
        self.ing.scan()
        self.assertEqual(self.names(), ["pub.txt"])
        self.assertEqual(self.app.uploads[0][1], "a1")
        self.assertNotIn(I.ACCESS_FILE, self.names())
        self.assertNotIn("file_id", self.ing.state["files"]["eng/sub/sec.txt"])
        self.ing.scan()
        self.assertEqual(self.names(), ["pub.txt"])
        self.assertEqual(self.app.deletes, [])

    def test_public_to_private_deletes(self):
        self.ing.scan()
        self.assertEqual(self.names(), ["pub.txt", "sec.txt"])
        fid = self.ing.state["files"]["eng/sub/sec.txt"]["file_id"]
        self.set_access({"sub": {"access": "private"}})
        self.ing.scan()
        self.assertEqual(self.app.deletes, [fid])
        self.assertEqual(len(self.app.uploads), 2)
        self.ing.scan()
        self.assertEqual(self.app.deletes, [fid])
        self.assertEqual(len(self.app.uploads), 2)

    def test_private_to_public_uploads(self):
        self.set_access({"sub": {"access": "private"}})
        self.ing.scan()
        self.assertEqual(self.names(), ["pub.txt"])
        self.set_access({})
        self.ing.scan()
        self.assertEqual(self.names(), ["pub.txt", "sec.txt"])
        self.assertEqual(self.app.deletes, [])

    def test_removed_private_file_needs_no_delete(self):
        self.set_access({"sub": {"access": "private"}})
        self.ing.scan()
        (self.dept / "sub" / "sec.txt").unlink()
        self.ing.scan()
        self.assertNotIn("eng/sub/sec.txt", self.ing.state["files"])
        self.assertEqual(self.app.deletes, [])


if __name__ == "__main__":
    unittest.main()
