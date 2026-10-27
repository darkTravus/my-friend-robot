import json
import tempfile
import unittest
from pathlib import Path

from modules import ToolRegistry, listes


class ListToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name) / "data"
        self.cfg = {"lists": {"data_dir": str(self.data_dir)}}

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_tool(self, action, **kwargs):
        return listes.run({"action": action, **kwargs}, self.cfg)

    def test_add_creates_persistent_list_and_avoids_case_insensitive_duplicates(self):
        self.assertIn("a été ajouté", self.run_tool("add", list_name="Courses", item="Pain"))
        self.assertIn("déjà", self.run_tool("add", list_name="courses", item="pain"))

        data = json.loads((self.data_dir / "lists.json").read_text(encoding="utf-8"))
        self.assertEqual(data, {"Courses": ["Pain"]})

    def test_list_and_show_return_saved_lists_and_items(self):
        self.run_tool("add", list_name="Courses", item="Pain")
        self.run_tool("add", list_name="Animés", item="Ao Ashi")

        self.assertEqual(self.run_tool("list"), "Listes enregistrées : Animés, Courses")
        self.assertEqual(self.run_tool("show", list_name="courses"), "Liste Courses :\n- Pain")

    def test_remove_deletes_only_the_exact_case_insensitive_item(self):
        self.run_tool("add", list_name="Courses", item="Pain")
        self.run_tool("add", list_name="Courses", item="Lait")

        self.assertIn("a été supprimé", self.run_tool("remove", list_name="Courses", item="pain"))
        data = json.loads((self.data_dir / "lists.json").read_text(encoding="utf-8"))
        self.assertEqual(data, {"Courses": ["Lait"]})
        self.assertIn("n'est pas", self.run_tool("remove", list_name="Courses", item="Pains"))

    def test_export_writes_markdown_and_text_files(self):
        self.run_tool("add", list_name="Courses", item="Pain")

        self.assertIn(".md", self.run_tool("export", list_name="Courses"))
        self.assertIn(".txt", self.run_tool("export", list_name="Courses", format="txt"))
        exports = list((self.data_dir / "exports").iterdir())
        self.assertEqual({path.suffix for path in exports}, {".md", ".txt"})
        self.assertTrue(any("# Courses\n\n- Pain\n" == path.read_text(encoding="utf-8")
                            for path in exports if path.suffix == ".md"))

    def test_corrupt_store_is_not_overwritten(self):
        self.data_dir.mkdir(parents=True)
        store = self.data_dir / "lists.json"
        store.write_text("{invalid", encoding="utf-8")

        with self.assertRaises(json.JSONDecodeError):
            self.run_tool("add", list_name="Courses", item="Pain")
        self.assertEqual(store.read_text(encoding="utf-8"), "{invalid")

    def test_missing_arguments_and_invalid_export_format_are_reported(self):
        self.assertIn("Nom de liste manquant", self.run_tool("show"))
        self.run_tool("add", list_name="Courses", item="Pain")
        self.assertIn("Format d'export invalide",
                      self.run_tool("export", list_name="Courses", format="pdf"))

    def test_tool_is_discovered_and_called_by_registry(self):
        registry = ToolRegistry(self.cfg)

        self.assertIn("manage_list", registry.names())
        registry.call("manage_list", '{"action":"add","list_name":"courses","item":"bread"}')
        data = json.loads((self.data_dir / "lists.json").read_text(encoding="utf-8"))
        self.assertEqual(data, {"courses": ["bread"]})


if __name__ == "__main__":
    unittest.main()
