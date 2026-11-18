import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from workbench.app import App, make_handler
from workbench.cli import find_repos
from workbench.notes import Notes
from workbench.providers import ProviderError, load_provider
from workbench.providers.demo import DemoProvider, make_workspace
from workbench.settings import Settings, ui_config, validate_ui_config


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.notes = Notes(os.path.join(self.tmp.name, "notes.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_numeric_archive_entries_still_load(self):
        with open(self.notes.path, "w") as f:
            json.dump({"requirements": {"7": {"track": True}}, "archived": [{"seq": 123, "title": "t", "date": "2026-01-01"}]}, f)
        self.assertEqual(self.notes.load()["archived"][0]["id"], "123")

    def test_doc_add_update_delete(self):
        self.notes.save_doc({"id": "acme/api#1", "action": "add", "url": "https://example.com/a", "title": "A", "type": "prd"})
        with self.assertRaises(ValueError):
            self.notes.save_doc({"id": "acme/api#1", "action": "add", "url": "https://example.com/a", "title": "dup"})
        with self.assertRaises(ValueError):
            self.notes.save_doc({"id": "acme/api#1", "action": "add", "url": "javascript:alert(1)", "title": "bad"})
        self.notes.save_doc({"id": "acme/api#1", "action": "update", "old_url": "https://example.com/a",
                             "url": "https://example.com/b", "title": "B"})
        self.assertEqual(self.notes.load()["requirements"]["acme/api#1"]["docs"][0]["url"], "https://example.com/b")
        self.notes.save_doc({"id": "acme/api#1", "action": "delete", "url": "https://example.com/b"})
        self.assertEqual(self.notes.load()["requirements"]["acme/api#1"]["docs"], [])

    def test_archive_is_idempotent(self):
        self.notes.archive("5", "x")
        self.notes.archive("5", "x")
        self.assertEqual(len(self.notes.load()["archived"]), 1)

    def test_local_requirement_create_update_delete(self):
        body = {"title": "Retry", "status": "Doing", "note": "api first",
                "repos": [{"repo": "acme/web", "branch": "dev"}, {"repo": "acme/api", "branch": "dev"}],
                "edges": [["acme/web", "acme/api", "calls"]]}
        first = self.notes.save_local_requirement({**body, "action": "create"})
        second = self.notes.save_local_requirement({**body, "action": "create"})
        self.assertEqual((first, second), ("local-1", "local-2"))
        self.notes.save_doc({"id": first, "action": "add", "url": "https://example.com/p", "title": "PRD"})
        self.notes.save_local_requirement({**body, "action": "update", "id": first, "title": "Retry v2"})
        saved = self.notes.load()["requirements"][first]
        self.assertEqual(saved["title"], "Retry v2")
        self.assertEqual(saved["nodes"], ["acme/web", "acme/api"])
        self.assertEqual(len(saved["docs"]), 1)          # an update keeps docs added elsewhere
        self.notes.save_local_requirement({"action": "delete", "id": first})
        self.assertNotIn(first, self.notes.load()["requirements"])

    def test_local_requirement_is_validated(self):
        ok = {"action": "create", "title": "T", "repos": [{"repo": "a", "branch": "b"}]}
        bad = [{**ok, "title": " "}, {**ok, "repos": []}, {**ok, "repos": [{"repo": "a", "branch": ""}]},
               {**ok, "edges": [["a", "elsewhere", "x"]]}, {**ok, "edges": [["a", "a", "x"]]}, {**ok, "edges": ["a"]},
               {**ok, "action": "update", "id": "7"}, {**ok, "action": "rename"}]
        for body in bad:
            with self.assertRaises(ValueError, msg=body):
                self.notes.save_local_requirement(body)


class UiConfigTest(unittest.TestCase):
    def test_update_keeps_other_keys_and_validates(self):
        with tempfile.TemporaryDirectory() as home:
            settings = Settings(home)
            settings.save_config({"provider": "demo", "workspace": "/w"})
            self.assertEqual(ui_config(settings.config)["recent_branch_days"], 7)
            settings.update_config(validate_ui_config({"recent_branch_days": "14"}))
            self.assertEqual(ui_config(settings.config)["recent_branch_days"], 14)
            self.assertEqual(Settings(home).config["workspace"], "/w")
            self.assertEqual(Settings(home).config["recent_branch_days"], 14)
            for body in ({"recent_branch_days": 0}, {"recent_branch_days": "abc"}, {"recent_branch_days": True},
                         {"workspace": "/elsewhere"}):
                with self.assertRaises(ValueError, msg=body):
                    validate_ui_config(body)

    def test_unusable_value_in_the_file_falls_back(self):
        self.assertEqual(ui_config({"recent_branch_days": "x"})["recent_branch_days"], 7)


class ProviderLoadingTest(unittest.TestCase):
    def test_missing_provider_says_how_to_create_the_config(self):
        with self.assertRaises(ProviderError) as ctx:
            load_provider({})
        self.assertIn("workbench init", str(ctx.exception))
        self.assertIn("--demo", str(ctx.exception))

    def test_unknown_provider_explains_itself(self):
        with self.assertRaises(ProviderError) as ctx:
            load_provider({"provider": "nope"})
        self.assertIn("provider_module", str(ctx.exception))

    def test_plugin_module_is_used(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "my_plugin.py"), "w") as f:
                f.write("from workbench.providers import Provider as B\nclass Provider(B):\n    name = 'mine'\n")
            p = load_provider({"provider": "mine", "provider_module": "my_plugin", "plugin_paths": [d]})
            self.assertEqual(p.name, "mine")


class CliHelpersTest(unittest.TestCase):
    def test_find_repos_walks_a_few_levels(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("a", "org/b", "org/deep/c/d/e"):
                os.makedirs(os.path.join(d, rel, ".git"))
            self.assertEqual(find_repos(d), ["a", "org/b"])


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        commits = make_workspace(cls.tmp.name)
        settings = Settings(os.path.join(cls.tmp.name, "_home"), {"provider": "demo", "workspace": cls.tmp.name})
        cls.app = App(settings, DemoProvider(settings.config, commits))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def post(self, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        return urllib.request.urlopen(req)

    def test_static_files_and_data(self):
        self.assertIn(b"<title>", urllib.request.urlopen(self.base + "/").read())
        self.assertIn(b"const lbl", urllib.request.urlopen(self.base + "/static/core.js").read())
        data = json.load(urllib.request.urlopen(self.base + "/api/data"))
        self.assertEqual(data["provider"], "demo")

    def test_path_traversal_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + "/static/..%2F..%2Fsettings.py")
        self.assertEqual(ctx.exception.code, 404)

    def test_cross_origin_posts_are_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/archive", {"id": "1"}, {"Origin": "https://evil.example"})
        self.assertEqual(ctx.exception.code, 403)

    def test_archive_roundtrip(self):
        data = json.load(self.post("/api/archive", {"id": "5", "title": "Rate limiting"}))
        self.assertEqual([a["id"] for a in data["archived"]], ["5"])
        self.assertNotIn("5", [r["id"] for r in data["requirements"]])

    def test_local_requirement_and_config_endpoints(self):
        data = json.load(self.post("/api/local-requirement", {
            "action": "create", "title": "Search v2", "repos": [{"repo": "acme/api", "branch": "feature/rate-limit"}]}))
        self.assertIn(data["savedId"], [r["id"] for r in data["requirements"]])
        data = json.load(self.post("/api/config", {"recent_branch_days": 30}))
        self.assertEqual(data["uiConfig"]["recent_branch_days"], 30)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/config", {"provider": "other"})
        self.assertIn("provider", json.load(ctx.exception)["error"])


if __name__ == "__main__":
    unittest.main()
