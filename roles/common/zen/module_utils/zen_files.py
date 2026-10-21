# Reading and merging Zen's profile files: zen-sessions.jsonlz4 (spaces and their pinned
# tabs), containers.json and zen-keyboard-shortcuts.json. Pure functions, so the modules in
# ../library stay thin and tests/ can run them without Ansible.
import copy
import json
import os
import random
import re
import struct
import time
import uuid
from urllib.parse import urlsplit

MOZLZ4_MAGIC = b"mozLz40\0"


def mozlz4_decode(data):
    """Decompress Mozilla's lz4 container: magic, uint32 size, one raw lz4 block."""
    if data[:8] != MOZLZ4_MAGIC:
        raise ValueError("not a mozlz4 file")
    size = struct.unpack("<I", data[8:12])[0]
    src = data[12:]
    out = bytearray()
    i = 0
    while i < len(src):
        token = src[i]
        i += 1
        length = token >> 4
        if length == 15:
            while True:
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        out += src[i:i + length]
        i += length
        if i >= len(src):
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        length = token & 15
        if length == 15:
            while True:
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        length += 4
        start = len(out) - offset
        # Matches may overlap what they copy, so byte by byte
        for k in range(length):
            out.append(out[start + k])
    if len(out) != size:
        raise ValueError("mozlz4 size mismatch: %d != %d" % (len(out), size))
    return bytes(out)


def mozlz4_encode(raw):
    """A valid lz4 block holding only literals. No compression: Zen recompresses on its next save."""
    length = len(raw)
    if length < 15:
        block = bytes([length << 4]) + raw
    else:
        rest = length - 15
        ext = b"\xff" * (rest // 255) + bytes([rest % 255])
        block = b"\xf0" + ext + raw
    return MOZLZ4_MAGIC + struct.pack("<I", length) + block


def read_json_lz4(path):
    with open(path, "rb") as f:
        return json.loads(mozlz4_decode(f.read()))


def write_atomic(path, content):
    """Through a temp file next to it, so an interrupted run never leaves half a file."""
    tmp = path + ".ansible-tmp"
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, path)


def write_json_lz4(path, data):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    write_atomic(path, mozlz4_encode(raw))


def hex_to_rgb(value):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def url_key(url):
    """host + path without the trailing slash, ignoring scheme, query and fragment."""
    parts = urlsplit(url)
    return (parts.netloc + parts.path).rstrip("/").lower()


def tab_keys(tab):
    """Where a pinned tab points: the url it was pinned with and the one it shows now."""
    keys = []
    entry = (tab.get("_zenPinnedInitialState") or {}).get("entry") or {}
    if entry.get("url"):
        keys.append(url_key(entry["url"]))
    entries = tab.get("entries") or []
    if entries:
        index = min(max(tab.get("index", len(entries)), 1), len(entries))
        if entries[index - 1].get("url"):
            keys.append(url_key(entries[index - 1]["url"]))
    return keys


def pin_matches(pin, tab):
    # A pin this module added, before the page redirected it to where `match` points
    initial = ((tab.get("_zenPinnedInitialState") or {}).get("entry") or {}).get("url")
    if initial == pin["url"]:
        return True
    match = url_key("https://" + pin["match"]) if pin.get("match") else url_key(pin["url"])
    return any(k == match or k.startswith(match + "/") for k in tab_keys(tab))


def _new_sync_id(now_ms, rng):
    # Zen keys tabs by this id and drops duplicates; same shape as its own (ms-uuid)
    return "%d-%s" % (now_ms, uuid.UUID(int=rng.getrandbits(128), version=4))


def _new_uuid(rng):
    h = "%032x" % rng.getrandbits(128)
    return "{%s-%s-4%s-%s-%s}" % (h[:8], h[8:12], h[13:16], h[16:20], h[20:32])


def _theme(existing, rgb):
    theme = copy.deepcopy(existing) if existing else {"type": "gradient", "opacity": 0.5, "texture": 0}
    old = (theme.get("gradientColors") or [None])[0] or {}
    if old.get("c") == rgb and len(theme.get("gradientColors") or []) == 1:
        return theme
    theme["gradientColors"] = [{
        "c": rgb,
        "isCustom": False,
        "algorithm": "floating",
        "isPrimary": True,
        "lightness": old.get("lightness", "50"),
        "position": old.get("position", {"x": 120, "y": 120}),
        "type": "explicit-lightness",
    }]
    return theme


def _find_space(spaces, context):
    names = [n.lower() for n in [context["name"]] + list(context.get("aliases") or [])]
    for space in spaces:
        if (space.get("name") or "").lower() in names:
            return space
    return None


def _ensure_container(containers, space, context, palette, changes):
    """The container a space opens its tabs in. Kept by id: cookies and logins are keyed on it."""
    wanted = context.get("container")
    if not wanted:
        if space.get("containerTabId", 0) != 0:
            space["containerTabId"] = 0
            changes.append("%s: no container" % context["name"])
        return 0
    color = palette[context["color"]]["container"]
    identities = containers.setdefault("identities", [])
    names = [n.lower() for n in [wanted] + list(context.get("container_aliases") or [])]
    ident = next((i for i in identities if i.get("public", True)
                  and (i.get("name") or "").lower() in names), None)
    if ident is None and space.get("containerTabId"):
        # The space's current container, renamed (a typo fixed, say): its id keeps the logins
        ident = next((i for i in identities if i.get("public", True)
                      and i.get("userContextId") == space["containerTabId"] and i.get("name")), None)
    if ident is None:
        new_id = max([containers.get("lastUserContextId", 0)]
                     + [i["userContextId"] for i in identities if i.get("userContextId", 0) < 2 ** 31]) + 1
        ident = {"userContextId": new_id, "public": True, "icon": "briefcase",
                 "color": color, "name": wanted, "accessKey": ""}
        identities.append(ident)
        containers["lastUserContextId"] = new_id
        changes.append("%s: new container %s (%d)" % (context["name"], wanted, new_id))
    for k, v in (("name", wanted), ("color", color)):
        if ident.get(k) != v:
            changes.append("%s: container %s %r -> %r" % (context["name"], k, ident.get(k), v))
            ident[k] = v
    if space.get("containerTabId") != ident["userContextId"]:
        changes.append("%s: container id %r -> %d" % (context["name"], space.get("containerTabId"),
                                                      ident["userContextId"]))
        space["containerTabId"] = ident["userContextId"]
    return ident["userContextId"]


def merge_session(session, containers, contexts, palette, now_ms=None, rng=None):
    """Make the session hold every context as a space, in order, with its pins.

    Spaces and containers are matched by name (or alias) and keep their ids. Pins are only
    added: a pinned tab that is not in a context's list is left alone. Spaces that no context
    names stay, after the managed ones. Returns (session, containers, changes).
    """
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    rng = rng or random.Random()
    session = copy.deepcopy(session)
    containers = copy.deepcopy(containers)
    changes = []
    spaces = session.setdefault("spaces", [])
    tabs = session.setdefault("tabs", [])

    managed = []
    for context in contexts:
        space = _find_space(spaces, context)
        if space is None:
            space = {"uuid": _new_uuid(rng), "name": context["name"], "theme": None,
                     "containerTabId": 0, "hasCollapsedPinnedTabs": False}
            changes.append("%s: new space" % context["name"])
        elif space.get("name") != context["name"]:
            changes.append("%s: renamed from %r" % (context["name"], space.get("name")))
            space["name"] = context["name"]
        theme = _theme(space.get("theme"), hex_to_rgb(palette[context["color"]]["hex"]))
        if theme != space.get("theme"):
            changes.append("%s: color %s" % (context["name"], context["color"]))
            space["theme"] = theme
        user_context_id = _ensure_container(containers, space, context, palette, changes)

        in_space = [t for t in tabs if t.get("pinned") and t.get("zenWorkspace") == space["uuid"]]
        for pin in context.get("pins") or []:
            if any(pin_matches(pin, t) for t in in_space):
                continue
            tab = {
                "entries": [{"url": pin["url"], "title": pin["title"],
                             "triggeringPrincipal_base64": '{"3":{}}'}],
                "lastAccessed": now_ms,
                "pinned": True,
                "hidden": False,
                "zenWorkspace": space["uuid"],
                "zenSyncId": _new_sync_id(now_ms, rng),
                "zenEssential": False,
                # The tab got its container from the space, as tabs Zen opens itself do
                "zenDefaultUserContextId": "true",
                "zenPinnedIcon": None,
                "zenIsEmpty": False,
                "zenHasStaticIcon": False,
                "zenGlanceId": None,
                "zenIsGlance": False,
                "_zenPinnedInitialState": {"entry": {"url": pin["url"], "title": pin["title"]}, "image": None},
                "zenLiveFolderItemId": None,
                "searchMode": None,
                "userContextId": user_context_id,
                "attributes": {},
                "index": 1,
                "userTypedValue": "",
                "userTypedClear": 0,
            }
            # Pinned tabs come before the unpinned ones; after the space's last pin keeps its order
            anchor = in_space[-1] if in_space else next((t for t in reversed(tabs) if t.get("pinned")), None)
            pos = tabs.index(anchor) + 1 if anchor is not None else 0
            tabs.insert(pos, tab)
            in_space.append(tab)
            changes.append("%s: pin %s" % (context["name"], pin["title"]))
        managed.append(space)

    others = [s for s in spaces if all(s is not m for m in managed)]
    ordered = managed + others
    if [s["uuid"] for s in ordered] != [s["uuid"] for s in spaces]:
        changes.append("space order: %s" % ", ".join(s["name"] for s in ordered))
    session["spaces"] = ordered
    return session, containers, changes


MODIFIERS = ("control", "alt", "shift", "meta", "accel")


def merge_shortcuts(data, overrides, control_is_accel=False):
    """Set each override's key, modifiers and disabled state on the shortcut with that id.

    Shortcuts the overrides don't name keep what Zen gave them. Ids Zen doesn't know are
    reported, not added: Zen drops entries it can't map to a command. Off macOS Zen stores
    ctrl as accel when it loads the file (control_is_accel), so compare it that way.
    """
    data = copy.deepcopy(data)
    changes, missing = [], []
    by_id = {s.get("id"): s for s in data.get("shortcuts", []) if s.get("id")}
    for o in overrides:
        s = by_id.get(o["id"])
        if s is None:
            missing.append(o["id"])
            continue
        mods = list(o.get("modifiers") or [])
        if control_is_accel and "control" in mods:
            mods = [m for m in mods if m != "control"] + ["accel"]
        want = {
            "key": o.get("key", s.get("key")),
            "keycode": o.get("keycode", s.get("keycode")),
            "modifiers": {m: m in mods for m in MODIFIERS},
            "disabled": bool(o.get("disabled", False)),
        }
        for k, v in want.items():
            if s.get(k) != v:
                changes.append("%s: %s %r -> %r" % (o["id"], k, s.get(k), v))
                s[k] = v
    return data, changes, missing


def profile_from_ini(text):
    """The profile Zen opens: Default= of the [Install...] section, else the Default=1 profile."""
    section, profiles, current = None, {}, {}
    install = None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1)
            current = profiles.setdefault(section, {})
            continue
        if "=" in line and section:
            k, v = line.split("=", 1)
            current[k] = v
            if section.startswith("Install") and k == "Default" and install is None:
                install = v
    if install:
        return install
    for values in profiles.values():
        if values.get("Default") == "1" and "Path" in values:
            return values["Path"]
    return None
