import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parent


class CuratedLocaleTests(unittest.TestCase):
    def test_reported_raw_keys_have_human_labels(self):
        data = json.loads((ROOT / "curated-en.json").read_text(encoding="utf-8"))["common"]
        expected = {
            "actions.exit": "Exit",
            "comments.title": "Comments",
            "search.title": "Search",
            "dashboard.title": "Dashboard",
        }
        for dotted, label in expected.items():
            section, key = dotted.split(".", 1)
            self.assertEqual(data[section][key], label)
            self.assertNotEqual(data[section][key], dotted)

    def test_patch_is_guarded_and_preserves_existing_translations(self):
        script = (ROOT / "install-curated-locale.js").read_text(encoding="utf-8")
        self.assertIn("if (source.includes('fakecoEnglish')) process.exit(0)", script)
        self.assertIn("addResourceBundle(locale, ns, data, true, false)", script)
        self.assertIn("Unsupported Wiki.js localization.js layout", script)


if __name__ == "__main__":
    unittest.main()
