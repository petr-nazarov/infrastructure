#!/usr/bin/python
# Sets Zen keyboard shortcuts in <profile>/zen-keyboard-shortcuts.json by id, and extension
# command shortcuts in <profile>/extension-settings.json (see zen_files.merge_shortcuts and
# merge_extension_shortcuts). Zen reads both on start and writes them back from memory, so
# write them with Zen closed. Supports check mode.
import json
import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.zen_files import merge_extension_shortcuts, merge_shortcuts, write_atomic

DOCUMENTATION = r"""
module: zen_shortcuts
short_description: Set Zen keyboard shortcuts by id
options:
  profile: {type: path, required: true, description: Zen profile directory}
  shortcuts:
    type: list
    elements: dict
    required: true
    description: "{id, key, modifiers: [control|alt|shift|meta|accel], disabled}"
  control_is_accel: {type: bool, default: false}
  extension_shortcuts:
    type: list
    elements: dict
    default: []
    description: "{extension, command, shortcut}, shortcut like Ctrl+B (cmd on macOS)"
"""


def main():
    module = AnsibleModule(
        argument_spec=dict(
            profile=dict(type="path", required=True),
            shortcuts=dict(type="list", elements="dict", required=True),
            # Off macOS Zen stores ctrl as accel
            control_is_accel=dict(type="bool", default=False),
            extension_shortcuts=dict(type="list", elements="dict", default=[]),
        ),
        supports_check_mode=True,
    )
    profile = module.params["profile"]
    path = os.path.join(profile, "zen-keyboard-shortcuts.json")
    if not os.path.exists(path):
        module.fail_json(msg="%s missing, start Zen once on this profile first" % path)
    with open(path) as f:
        data = json.load(f)
    new, changes, missing = merge_shortcuts(data, module.params["shortcuts"], module.params["control_is_accel"])
    if missing:
        module.warn("Zen has no shortcut with id %s, skipped" % ", ".join(missing))

    ext_path = os.path.join(profile, "extension-settings.json")
    ext_changes = []
    if module.params["extension_shortcuts"]:
        settings = {"version": 3}
        if os.path.exists(ext_path):
            with open(ext_path) as f:
                settings = json.load(f)
        with open(os.path.join(profile, "extensions.json")) as f:
            addons = json.load(f).get("addons", [])
        new_settings, ext_changes, ext_missing = merge_extension_shortcuts(
            settings, addons, module.params["extension_shortcuts"])
        if ext_missing:
            # Policy installs them on Zen's next start; the run after that sets the shortcut
            module.warn("Extension %s not installed yet, its shortcut is set on a later run"
                        % ", ".join(ext_missing))

    if not module.check_mode:
        if changes:
            write_atomic(path, json.dumps(new).encode("utf-8"))
        if ext_changes:
            write_atomic(ext_path, json.dumps(new_settings).encode("utf-8"))
    module.exit_json(changed=bool(changes or ext_changes), changes=changes + ext_changes)


if __name__ == "__main__":
    main()
