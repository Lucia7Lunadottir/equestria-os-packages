"""Tests for CharacterStore (drop-in characters.d + legacy characters.json).

Run:  python3 -m unittest discover -s tests      (from the equestria-qt-kit folder)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from equestria_kit.character_store import CharacterStore, BACKUP_SUFFIX  # noqa: E402

PINKIE = {"Id": "pinkie", "DisplayName": "Pinkie Pie", "AccentColor": "#F06292", "HoverColor": "#111111"}
DASH = {"Id": "rainbow", "DisplayName": "Rainbow Dash", "AccentColor": "#1E88E5", "KonsoleTheme": {"Color0": "1,2,3"}}


class StoreCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.user, self.system = Path(tmp.name) / "user", Path(tmp.name) / "system"
        self.user.mkdir()
        self.system.mkdir()
        self.store = CharacterStore(self.user, self.system)

    def put_legacy(self, folder, chars):
        (folder / "characters.json").write_text(json.dumps({"Characters": chars}))

    def put_dropin(self, folder, data, name=None):
        d = folder / "characters.d"
        d.mkdir(exist_ok=True)
        (d / (name or f"{data['Id']}.json")).write_text(json.dumps(data))

    def by_id(self):
        return {c["Id"]: c for c in self.store.read()}


class Reading(StoreCase):
    def test_system_legacy_file_is_read(self):
        self.put_legacy(self.system, [PINKIE, DASH])
        self.assertEqual([c["Id"] for c in self.store.read()], ["pinkie", "rainbow"])

    def test_system_dropins_are_read_and_win_over_system_legacy(self):
        self.put_legacy(self.system, [PINKIE])
        self.put_dropin(self.system, {"Id": "pinkie", "AccentColor": "#000001"})
        self.put_dropin(self.system, DASH)
        got = self.by_id()
        self.assertEqual(got["pinkie"]["AccentColor"], "#000001")
        self.assertEqual(got["pinkie"]["DisplayName"], "Pinkie Pie")     # field merge
        self.assertIn("rainbow", got)

    def test_user_override_changes_only_its_fields(self):
        self.put_dropin(self.system, PINKIE)
        self.put_dropin(self.user, {"Id": "pinkie", "AccentColor": "#ff00ff"})
        got = self.by_id()["pinkie"]
        self.assertEqual((got["AccentColor"], got["HoverColor"]), ("#ff00ff", "#111111"))

    def test_package_update_reaches_user_who_overrides_other_fields(self):
        self.put_dropin(self.system, PINKIE)
        self.put_dropin(self.user, {"Id": "pinkie", "AccentColor": "#ff00ff"})
        self.put_dropin(self.system, {**PINKIE, "KeyboardBacklight": {"Rainbow": True}})   # new field shipped later
        self.assertEqual(self.by_id()["pinkie"]["KeyboardBacklight"], {"Rainbow": True})

    def test_null_removes_a_field_and_deleted_hides_a_builtin(self):
        self.put_dropin(self.system, {**PINKIE, "KeyboardBacklight": {"Color": "#112233"}})
        self.put_dropin(self.system, DASH)
        self.put_dropin(self.user, {"Id": "pinkie", "KeyboardBacklight": None})
        self.put_dropin(self.user, {"Id": "rainbow", "Deleted": True})
        got = self.by_id()
        self.assertNotIn("KeyboardBacklight", got["pinkie"])
        self.assertNotIn("rainbow", got)

    def test_users_own_character(self):
        self.put_dropin(self.system, PINKIE)
        self.put_dropin(self.user, {"Id": "mine", "DisplayName": "Mine", "AccentColor": "#abcdef"})
        self.assertEqual([c["Id"] for c in self.store.read()], ["pinkie", "mine"])

    def test_legacy_user_file_decides_the_set_but_fields_come_from_system(self):
        self.put_dropin(self.system, {**PINKIE, "KeyboardBacklight": {"Rainbow": True}})
        self.put_dropin(self.system, DASH)
        self.put_legacy(self.user, [{**PINKIE, "AccentColor": "#123456"}])   # old full copy; Dash not in it = deleted
        got = self.by_id()
        self.assertEqual(list(got), ["pinkie"])
        self.assertEqual(got["pinkie"]["AccentColor"], "#123456")
        self.assertEqual(got["pinkie"]["KeyboardBacklight"], {"Rainbow": True})   # not lost to the stale copy

    def test_a_builtin_added_after_the_old_file_was_written_is_not_hidden(self):
        self.put_dropin(self.system, PINKIE)
        self.put_dropin(self.system, {"Id": "canterlot", "DisplayName": "Canterlot"})   # shipped later, not in the old file
        self.put_legacy(self.user, [PINKIE])
        self.assertEqual(sorted(self.by_id()), ["canterlot", "pinkie"])

    def test_broken_files_are_skipped_not_fatal(self):
        self.put_dropin(self.system, PINKIE)
        (self.system / "characters.d" / "broken.json").write_text("{not json")
        (self.user / "characters.json").write_text("{also broken")
        self.assertEqual([c["Id"] for c in self.store.read()], ["pinkie"])

    def test_nothing_installed(self):
        self.assertEqual(self.store.read(), [])
        self.assertEqual(len(self.store.signature()), 5)


class Writing(StoreCase):
    def setUp(self):
        super().setUp()
        self.put_dropin(self.system, PINKIE)
        self.put_dropin(self.system, DASH)

    def files(self):
        d = self.user / "characters.d"
        return sorted(p.name for p in d.glob("*.json")) if d.exists() else []

    def test_unchanged_list_writes_no_override_files(self):
        self.store.write(self.store.read())
        self.assertEqual(self.files(), [])

    def test_only_changed_fields_are_stored(self):
        chars = self.store.read()
        chars[0]["AccentColor"] = "#00ff00"
        self.store.write(chars)
        self.assertEqual(self.files(), ["pinkie.json"])
        self.assertEqual(json.loads((self.user / "characters.d/pinkie.json").read_text()),
                         {"Id": "pinkie", "AccentColor": "#00ff00"})
        self.assertEqual(self.by_id()["pinkie"]["AccentColor"], "#00ff00")

    def test_going_back_to_the_default_removes_the_override_file(self):
        chars = self.store.read()
        chars[0]["AccentColor"] = "#00ff00"
        self.store.write(chars)
        chars[0]["AccentColor"] = PINKIE["AccentColor"]
        self.store.write(chars)
        self.assertEqual(self.files(), [])

    def test_removed_field_roundtrips(self):
        self.put_dropin(self.system, {**PINKIE, "KeyboardBacklight": {"Color": "#112233"}})
        chars = self.store.read()
        del chars[0]["KeyboardBacklight"]            # e.g. the editor's "Auto" prunes empty fields
        self.store.write(chars)
        self.assertNotIn("KeyboardBacklight", self.by_id()["pinkie"])

    def test_deleting_a_builtin_and_adding_own(self):
        chars = [c for c in self.store.read() if c["Id"] != "rainbow"]
        chars.append({"Id": "my pony!", "DisplayName": "Mine"})
        self.store.write(chars)
        got = self.by_id()
        self.assertNotIn("rainbow", got)
        self.assertEqual(got["my pony!"]["DisplayName"], "Mine")
        self.assertTrue(all("/" not in n and " " not in n for n in self.files()))   # safe file names

    def test_deleting_own_character_removes_its_file(self):
        self.store.write(self.store.read() + [{"Id": "mine", "DisplayName": "x"}])
        self.assertTrue(any(n.endswith("mine.json") for n in self.files()))
        self.store.write([c for c in self.store.read() if c["Id"] != "mine"])
        self.assertFalse(any(n.endswith("mine.json") for n in self.files()))


class Order(StoreCase):
    def test_own_characters_keep_creation_order_not_alphabetical(self):
        self.put_dropin(self.system, PINKIE, name="10-pinkie.json")
        self.store.write(self.store.read() + [{"Id": "zebra"}, {"Id": "apple"}])
        self.store.write(self.store.read() + [{"Id": "mango"}])
        self.assertEqual([c["Id"] for c in self.store.read()], ["pinkie", "zebra", "apple", "mango"])

    def test_system_files_without_numbers_still_work(self):
        self.put_dropin(self.system, {"Id": "luna"}, name="luna.json")          # third-party package, no number
        self.put_dropin(self.system, PINKIE, name="10-pinkie.json")
        self.put_dropin(self.system, {"Id": "abby"}, name="abby.json")
        self.assertEqual([c["Id"] for c in self.store.read()], ["pinkie", "abby", "luna"])   # numbered first, then A-Z

    def test_order_survives_migration_of_the_old_file(self):
        self.put_dropin(self.system, PINKIE, name="10-pinkie.json")
        self.put_legacy(self.user, [PINKIE, {"Id": "zebra"}, {"Id": "apple"}])
        before = [c["Id"] for c in self.store.read()]
        self.store.migrate_legacy()
        self.assertEqual([c["Id"] for c in self.store.read()], before)


class Migration(StoreCase):
    def setUp(self):
        super().setUp()
        self.put_dropin(self.system, {**PINKIE, "KeyboardBacklight": {"Rainbow": True}})
        self.put_dropin(self.system, DASH)

    def test_read_is_identical_before_and_after_and_old_file_is_kept(self):
        stale = {**PINKIE, "AccentColor": "#123456", "UiPalette": {"base": "#000000"}}
        custom = {"Id": "mine", "DisplayName": "Mine", "AccentColor": "#abcdef"}
        self.put_legacy(self.user, [stale, custom])             # Dash deleted by the user
        before = self.store.read()
        self.assertTrue(self.store.migrate_legacy())
        self.assertEqual(self.store.read(), before)
        self.assertFalse((self.user / "characters.json").exists())
        self.assertTrue((self.user / ("characters.json" + BACKUP_SUFFIX)).exists())   # never deleted

    def test_unedited_copy_becomes_no_overrides(self):
        self.put_legacy(self.user, [{**PINKIE, "KeyboardBacklight": {"Rainbow": True}}, DASH])
        self.store.migrate_legacy()
        self.assertEqual(list((self.user / "characters.d").glob("*.json")), [])

    def test_migration_keeps_a_newly_shipped_builtin_and_still_honours_old_deletions(self):
        self.put_dropin(self.system, {"Id": "canterlot", "DisplayName": "Canterlot"})
        self.put_legacy(self.user, [PINKIE])                   # old file: Dash was deleted, Canterlot did not exist yet
        self.store.migrate_legacy()
        got = self.by_id()
        self.assertIn("canterlot", got)
        self.assertNotIn("rainbow", got)
        tombstones = [p.name for p in (self.user / "characters.d").glob("*.json")
                      if json.loads(p.read_text()).get("Deleted")]
        self.assertEqual(tombstones, ["rainbow.json"])

    def test_second_run_does_nothing_and_broken_file_is_left_alone(self):
        self.put_legacy(self.user, [PINKIE])
        self.assertTrue(self.store.migrate_legacy())
        self.assertFalse(self.store.migrate_legacy())
        (self.user / "characters.json").write_text("{broken")
        self.assertFalse(self.store.migrate_legacy())
        self.assertEqual((self.user / "characters.json").read_text(), "{broken")

    def test_write_converts_first(self):
        self.put_legacy(self.user, [PINKIE, DASH])
        chars = self.store.read()
        chars[0]["AccentColor"] = "#00ff00"
        self.store.write(chars)
        self.assertFalse((self.user / "characters.json").exists())
        self.assertEqual(self.by_id()["pinkie"]["AccentColor"], "#00ff00")
        self.assertIn("rainbow", self.by_id())


if __name__ == "__main__":
    unittest.main()
