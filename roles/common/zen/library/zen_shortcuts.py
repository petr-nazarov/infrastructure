#!/usr/bin/python
# Sets Zen keyboard shortcuts in <profile>/zen-keyboard-shortcuts.json by id (see
# zen_files.merge_shortcuts). Zen reads the file on start and rewrites it from memory when a
# shortcut is changed in its settings, so write it with Zen closed. Supports check mode.
import json
import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.zen_files import merge_shortcuts, write_atomic

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
"""


def main():
    module = AnsibleModule(
        argument_spec=dict(
            profile=dict(type="path", required=True),
            shortcuts=dict(type="list", elements="dict", required=True),
            # Off macOS Zen stores ctrl as accel
            control_is_accel=dict(type="bool", default=False),
        ),
        supports_check_mode=True,
    )
    path = os.path.join(module.params["profile"], "zen-keyboard-shortcuts.json")
    if not os.path.exists(path):
        module.fail_json(msg="%s missing, start Zen once on this profile first" % path)
    with open(path) as f:
        data = json.load(f)
    new, changes, missing = merge_shortcuts(data, module.params["shortcuts"], module.params["control_is_accel"])
    if missing:
        module.warn("Zen has no shortcut with id %s, skipped" % ", ".join(missing))
    if changes and not module.check_mode:
        write_atomic(path, json.dumps(new).encode("utf-8"))
    module.exit_json(changed=bool(changes), changes=changes)


if __name__ == "__main__":
    main()
