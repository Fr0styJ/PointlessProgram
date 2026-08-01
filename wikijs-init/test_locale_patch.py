import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parent


class CuratedLocaleTests(unittest.TestCase):
    def test_reported_and_welcome_keys_have_curated_labels(self):
        data = json.loads((ROOT / "curated-en.json").read_text(encoding="utf-8"))
        expected = {
            "actions.exit": "Exit",
            "comments.title": "Comments",
            "search.title": "Search",
            "dashboard.title": "Dashboard",
            "welcome.createhome": "Create Home Page",
            "welcome.goadmin": "Go to Administration",
        }
        for dotted, label in expected.items():
            self.assertEqual(data[dotted], label)
            self.assertNotEqual(data[dotted], dotted)

    def test_patch_is_guarded_and_preserves_existing_translations(self):
        script = (ROOT / "install-curated-locale.js").read_text(encoding="utf-8")
        self.assertIn("if (!source.includes('fakecoEnglish'))", script)
        self.assertIn("addResourceBundle(locale, ns, data, true, false)", script)
        self.assertIn("Unsupported Wiki.js localization.js layout", script)
        self.assertIn('prefix:"fakeco_i18next_v1_"', script)
        self.assertIn("occurrences !== 1", script)
        self.assertIn("app.js?fakeco-locale-v1", script)
        self.assertIn("Unsupported Wiki.js master template", script)


if __name__ == "__main__":
    unittest.main()
