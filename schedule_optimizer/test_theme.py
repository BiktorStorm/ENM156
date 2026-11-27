import tempfile
import unittest
from pathlib import Path

import theme
from GUI import NO_DEADLINE, deadlineChoices, parseDeadline


class ThemeTests(unittest.TestCase):
    def test_light_and_dark_have_the_same_colours(self):
        self.assertEqual(set(theme.LIGHT), set(theme.DARK))

    def test_palettes(self):
        self.assertIs(theme.palette("light"), theme.LIGHT)
        self.assertIs(theme.palette("dark"), theme.DARK)
        self.assertIn(theme.palette("system"), (theme.LIGHT, theme.DARK))
        self.assertIs(theme.palette("unknown"), theme.LIGHT)

    def test_settings_are_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "settings.json")
            self.assertEqual(theme.loadSettings(path), theme.DEFAULT_SETTINGS)
            theme.saveSettings({"appearance": "dark"}, path)
            self.assertEqual(theme.loadSettings(path)["appearance"], "dark")

    def test_broken_settings_give_the_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "settings.json")
            for content in ("not json", "[1, 2]", '{"appearance": "purple"}'):
                path.write_text(content)
                self.assertEqual(theme.loadSettings(path), theme.DEFAULT_SETTINGS)


class DeadlineChoiceTests(unittest.TestCase):
    def test_choices_start_after_the_process_ends(self):
        choices = deadlineChoices(40)          # ends 10:00
        self.assertEqual(choices[0], NO_DEADLINE)
        self.assertEqual(choices[1], "10:00")
        self.assertEqual(choices[-1], "24:00")
        self.assertEqual(len(deadlineChoices()), 1 + 96)

    def test_out_of_range_ends_are_clamped(self):
        self.assertEqual(deadlineChoices(500), [NO_DEADLINE, "24:00"])
        self.assertEqual(deadlineChoices(-3)[1], "00:15")

    def test_parse(self):
        self.assertIsNone(parseDeadline(NO_DEADLINE))
        self.assertIsNone(parseDeadline(""))
        self.assertEqual(parseDeadline("10:30"), "10:30")


if __name__ == "__main__":
    unittest.main()
