# Run: python3 -m unittest discover -s roles/common/zen/tests
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "module_utils"))
import zen_files as z  # noqa: E402

PALETTE = {
    "white": {"hex": "#ececec", "container": "toolbar"},
    "blue": {"hex": "#5b6ea4", "container": "blue"},
}


def pinned(space, url, title="t", current=None, ctx=0):
    entries = [{"url": current or url, "title": title}]
    return {"entries": entries, "index": 1, "pinned": True, "zenWorkspace": space,
            "userContextId": ctx, "_zenPinnedInitialState": {"entry": {"url": url, "title": title}}}


def session():
    return {
        "spaces": [
            {"uuid": "{a}", "name": "Space", "theme": {"type": "gradient", "gradientColors": [],
                                                       "opacity": 0.5, "texture": 0}, "containerTabId": 0},
            {"uuid": "{b}", "name": "tadam", "theme": None, "containerTabId": 6},
            {"uuid": "{c}", "name": "Mine", "theme": None, "containerTabId": 0},
        ],
        "tabs": [
            pinned("{a}", "https://home.frrcode.com/", current="https://auth.frrcode.com/?rd=x"),
            pinned("{b}", "https://mail.google.com/mail/u/0/#inbox", ctx=6),
            pinned("{b}", "https://app.notion.com/p/123", ctx=6),
            {"entries": [{"url": "https://example.com"}], "index": 1, "pinned": False, "zenWorkspace": "{a}"},
        ],
    }


CONTAINERS = {"version": 8, "lastUserContextId": 7, "identities": [
    {"userContextId": 4294967295, "public": False, "name": "userContextIdInternal.webextStorageLocal"},
    {"userContextId": 6, "public": True, "icon": "briefcase", "color": "gray", "name": "Tadam"},
    {"userContextId": 7, "public": True, "icon": "briefcase", "color": "gray", "name": "Old"},
]}

CONTEXTS = [
    {"name": "Personal", "aliases": ["Space"], "color": "white", "container": None, "pins": [
        {"title": "FrrCode", "url": "https://home.frrcode.com/"},
        {"title": "Gmail", "url": "https://mail.google.com/mail/u/1/#inbox"},
    ]},
    {"name": "Tadam", "color": "blue", "container": "Tadam", "pins": [
        {"title": "Gmail", "url": "https://mail.google.com/mail/u/0/#inbox"},
        {"title": "Kimai", "url": "https://time.frrcode.com/en/timesheet/", "match": "time.frrcode.com"},
    ]},
    {"name": "Cardbook", "color": "blue", "container": "Cardbook", "pins": [
        {"title": "Dash", "url": "https://home.frrcode.com/cardbook"},
    ]},
]


def merge(s=None, c=None):
    return z.merge_session(s or session(), c or CONTAINERS, CONTEXTS, PALETTE, now_ms=1000, rng=random.Random(1))


class Mozlz4(unittest.TestCase):
    def test_roundtrip(self):
        for raw in (b"", b"x" * 14, b"y" * 15, b"z" * 270, b"{\"a\": 1}" * 5000):
            self.assertEqual(z.mozlz4_decode(z.mozlz4_encode(raw)), raw)

    def test_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.jsonlz4")
            z.write_json_lz4(p, {"spaces": [{"name": "Ä"}]})
            self.assertEqual(z.read_json_lz4(p), {"spaces": [{"name": "Ä"}]})

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            z.mozlz4_decode(b"notmozlz" + b"\0" * 8)


class MergeSession(unittest.TestCase):
    def test_spaces_matched_by_alias_renamed_and_ordered(self):
        s, _, _ = merge()
        self.assertEqual([x["name"] for x in s["spaces"]], ["Personal", "Tadam", "Cardbook", "Mine"])
        self.assertEqual([x["uuid"] for x in s["spaces"][:2]], ["{a}", "{b}"])

    def test_existing_pin_found_by_initial_url_or_match(self):
        s, _, _ = merge()
        a = [t for t in s["tabs"] if t["zenWorkspace"] == "{a}" and t["pinned"]]
        # FrrCode already pinned (now showing the login redirect), Gmail u/1 added
        self.assertEqual([z.url_key(t["_zenPinnedInitialState"]["entry"]["url"]) for t in a],
                         ["home.frrcode.com", "mail.google.com/mail/u/1"])

    def test_manual_pins_kept_and_new_pins_follow_space_pins(self):
        s, _, _ = merge()
        b = [t["_zenPinnedInitialState"]["entry"]["url"] for t in s["tabs"] if t["zenWorkspace"] == "{b}"]
        self.assertEqual(b, ["https://mail.google.com/mail/u/0/#inbox", "https://app.notion.com/p/123",
                             "https://time.frrcode.com/en/timesheet/"])
        firsts = [t["pinned"] for t in s["tabs"]]
        self.assertEqual(firsts, sorted(firsts, reverse=True))

    def test_new_pin_uses_space_container(self):
        s, _, _ = merge()
        kimai = next(t for t in s["tabs"] if "time.frrcode.com" in t["entries"][0]["url"])
        self.assertEqual(kimai["userContextId"], 6)
        self.assertEqual(kimai["zenWorkspace"], "{b}")

    def test_container_kept_by_id_and_recolored_new_one_created(self):
        s, c, _ = merge()
        tadam = next(i for i in c["identities"] if i["userContextId"] == 6)
        self.assertEqual((tadam["name"], tadam["color"]), ("Tadam", "blue"))
        cardbook = next(x for x in s["spaces"] if x["name"] == "Cardbook")
        self.assertEqual(cardbook["containerTabId"], 8)
        self.assertEqual(c["lastUserContextId"], 8)
        self.assertTrue(any(i["name"] == "Cardbook" and i["userContextId"] == 8 for i in c["identities"]))

    def test_sync_ids_unique(self):
        s, _, _ = merge()
        ids = [t["zenSyncId"] for t in s["tabs"] if t.get("zenSyncId")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_container_found_by_name_before_space_id(self):
        # The space points at the user's own container: it is left alone, Tadam is used
        s = session()
        s["spaces"][1]["containerTabId"] = 7
        out, c, _ = merge(s)
        self.assertEqual(out["spaces"][1]["containerTabId"], 6)
        self.assertEqual(next(i for i in c["identities"] if i["userContextId"] == 7)["name"], "Old")

    def test_renamed_container_adopted_by_space_id(self):
        c = {"lastUserContextId": 6, "identities": [
            {"userContextId": 6, "public": True, "color": "gray", "name": "Tadm"}]}
        out, c2, _ = merge(None, c)
        self.assertEqual(out["spaces"][1]["containerTabId"], 6)
        self.assertEqual(c2["identities"][0]["name"], "Tadam")

    def test_color_from_palette(self):
        s, _, _ = merge()
        self.assertEqual(s["spaces"][1]["theme"]["gradientColors"][0]["c"], [0x5b, 0x6e, 0xa4])

    def test_idempotent(self):
        s, c, changes = merge()
        self.assertTrue(changes)
        s2, c2, changes2 = merge(s, c)
        self.assertEqual(changes2, [])
        self.assertEqual((s2, c2), (s, c))

    def test_pin_whose_url_differs_from_match_is_found_again(self):
        contexts = [{"name": "Personal", "aliases": ["Space"], "color": "white", "container": None, "pins": [
            {"title": "G", "url": "https://mail.google.com/mail/?authuser=x@y", "match": "mail.google.com/mail/u/1"}]}]
        s, c, changes = z.merge_session(session(), CONTAINERS, contexts, PALETTE, now_ms=1, rng=random.Random(1))
        self.assertIn("Personal: pin G", changes)
        _, _, again = z.merge_session(s, c, contexts, PALETTE, now_ms=1, rng=random.Random(1))
        self.assertEqual(again, [])

    def test_pin_on_its_login_redirect_without_initial_state(self):
        s = session()
        s["tabs"][0] = {"entries": [{"url": "https://auth.frrcode.com/?rd=https%3A%2F%2Fhome.frrcode.com%2F&rm="}],
                        "index": 1, "pinned": True, "zenWorkspace": "{a}", "_zenPinnedInitialState": None}
        _, _, changes = merge(s)
        self.assertNotIn("Personal: pin FrrCode", changes)

    def test_pin_in_another_contexts_container(self):
        contexts = CONTEXTS + [{"name": "Communication", "color": "white", "container": None, "pins": [
            {"title": "Slack", "url": "https://app.slack.com/client", "match": "app.slack.com",
             "container": "Tadam"}]}]
        s = session()
        s["spaces"].append({"uuid": "{d}", "name": "Communication", "theme": None, "containerTabId": 0})
        s["tabs"].insert(0, pinned("{d}", "https://app.slack.com/client/T1", ctx=0))
        s["tabs"][0]["zenDefaultUserContextId"] = "true"
        out, c, changes = z.merge_session(s, CONTAINERS, contexts, PALETTE, now_ms=1, rng=random.Random(1))
        slack = next(t for t in out["tabs"] if t["zenWorkspace"] == "{d}")
        self.assertEqual(slack["userContextId"], 6)
        self.assertNotIn("zenDefaultUserContextId", slack)
        self.assertIn("Communication: Slack in container Tadam", changes)
        _, _, again = z.merge_session(out, c, contexts, PALETTE, now_ms=1, rng=random.Random(1))
        self.assertEqual(again, [])

    def test_manual_pin_added_after_first_run_survives_second(self):
        s, c, _ = merge()
        s["tabs"].insert(0, pinned("{b}", "https://github.com/x/y", ctx=6))
        s2, _, changes = merge(s, c)
        self.assertEqual(changes, [])
        self.assertTrue(any(t["entries"][0]["url"] == "https://github.com/x/y" for t in s2["tabs"]))


class MergeShortcuts(unittest.TestCase):
    DATA = {"shortcuts": [
        {"id": "zen-workspace-switch-1", "key": "", "keycode": None, "disabled": False,
         "modifiers": {"control": False, "alt": False, "shift": False, "meta": False, "accel": False}},
        {"id": "key_selectTab1", "key": "1", "keycode": None, "disabled": False,
         "modifiers": {"control": False, "alt": False, "shift": False, "meta": False, "accel": True}},
        {"id": None, "key": "x", "modifiers": {}},
    ]}

    def test_sets_and_reports(self):
        data, changes, missing = z.merge_shortcuts(self.DATA, [
            {"id": "zen-workspace-switch-1", "key": "1", "modifiers": ["control"]},
            {"id": "key_selectTab1", "key": "1", "modifiers": ["alt"]},
            {"id": "nope", "key": "q"},
        ])
        s = {x["id"]: x for x in data["shortcuts"]}
        self.assertEqual(s["zen-workspace-switch-1"]["key"], "1")
        self.assertTrue(s["zen-workspace-switch-1"]["modifiers"]["control"])
        self.assertEqual(s["key_selectTab1"]["modifiers"],
                         {"control": False, "alt": True, "shift": False, "meta": False, "accel": False})
        self.assertEqual(missing, ["nope"])
        self.assertTrue(changes)
        _, again, _ = z.merge_shortcuts(data, [{"id": "key_selectTab1", "key": "1", "modifiers": ["alt"]}])
        self.assertEqual(again, [])


    def test_control_stored_as_accel_off_macos(self):
        data = {"shortcuts": [{"id": "zen-workspace-switch-1", "key": "1", "keycode": "", "disabled": False,
                               "modifiers": {"control": False, "alt": False, "shift": False,
                                             "meta": False, "accel": True}}]}
        _, changes, _ = z.merge_shortcuts(
            data, [{"id": "zen-workspace-switch-1", "key": "1", "modifiers": ["control"]}], control_is_accel=True)
        self.assertEqual(changes, [])


class MergeExtensionShortcuts(unittest.TestCase):
    ADDONS = [{"id": "bw@x", "installDate": 5, "defaultLocale": {"name": "Bitwarden"}},
              {"id": "other@x", "installDate": 9}]
    WANT = [{"extension": "bw@x", "command": "_execute_browser_action", "shortcut": "Ctrl+B"}]

    def test_adds_entry_next_to_other_extensions(self):
        settings = {"version": 3, "commands": {"_execute_browser_action": {"precedenceList": [
            {"id": "other@x", "installDate": 9, "value": {"shortcut": "Alt+K"}, "enabled": True}]}}}
        out, changes, missing = z.merge_extension_shortcuts(settings, self.ADDONS, self.WANT)
        items = out["commands"]["_execute_browser_action"]["precedenceList"]
        self.assertEqual([i["id"] for i in items], ["other@x", "bw@x"])
        self.assertEqual(items[1], {"id": "bw@x", "installDate": 5, "value": {"shortcut": "Ctrl+B"},
                                    "enabled": True})
        self.assertEqual(items[0]["value"], {"shortcut": "Alt+K"})
        self.assertTrue(changes)
        self.assertEqual(missing, [])
        _, again, _ = z.merge_extension_shortcuts(out, self.ADDONS, self.WANT)
        self.assertEqual(again, [])

    def test_keeps_other_updates_and_reports_missing(self):
        settings = {"commands": {"_execute_browser_action": {"precedenceList": [
            {"id": "bw@x", "installDate": 5, "value": {"description": "d", "shortcut": "Ctrl+Y"}, "enabled": True}]}}}
        out, _, missing = z.merge_extension_shortcuts(
            settings, self.ADDONS, self.WANT + [{"extension": "gone@x", "command": "c", "shortcut": "Ctrl+Q"}])
        self.assertEqual(out["commands"]["_execute_browser_action"]["precedenceList"][0]["value"],
                         {"description": "d", "shortcut": "Ctrl+B"})
        self.assertEqual(missing, ["gone@x"])


class ProfileIni(unittest.TestCase):
    def test_install_default_wins(self):
        text = "[Profile1]\nPath=b\nDefault=1\n\n[Profile0]\nPath=a (release)\n\n[Install15B]\nDefault=a (release)\n"
        self.assertEqual(z.profile_from_ini(text), "a (release)")

    def test_falls_back_to_default_profile(self):
        self.assertEqual(z.profile_from_ini("[Profile0]\nPath=x\nDefault=1\n"), "x")


if __name__ == "__main__":
    unittest.main()
