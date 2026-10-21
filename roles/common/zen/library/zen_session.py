#!/usr/bin/python
# Makes a Zen profile hold the given contexts as spaces with their pinned tabs (see
# zen_files.merge_session). Zen must be closed: it keeps the session in memory and writes
# it back on quit. Supports check mode, which the role uses to decide whether to quit Zen.
import json
import os
import shutil
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.zen_files import merge_session, read_json_lz4, write_atomic, write_json_lz4

DOCUMENTATION = r"""
module: zen_session
short_description: Ensure Zen spaces, their containers and pinned tabs
options:
  profile: {type: path, required: true, description: Zen profile directory}
  contexts: {type: list, elements: dict, required: true}
  palette: {type: dict, required: true, description: "color name -> {hex, container}"}
"""


def main():
    module = AnsibleModule(
        argument_spec=dict(
            profile=dict(type="path", required=True),
            contexts=dict(type="list", elements="dict", required=True),
            palette=dict(type="dict", required=True),
        ),
        supports_check_mode=True,
    )
    profile = module.params["profile"]
    session_file = os.path.join(profile, "zen-sessions.jsonlz4")
    containers_file = os.path.join(profile, "containers.json")
    # A profile Zen has never run in: Zen creates both on first start, containers.json with
    # internal identities (extension storage) that must not be left out
    for path in (session_file, containers_file):
        if not os.path.exists(path):
            module.fail_json(msg="%s missing, start Zen once on this profile first" % path)

    session = read_json_lz4(session_file)
    with open(containers_file) as f:
        containers = json.load(f)
    new_session, new_containers, changes = merge_session(
        session, containers, module.params["contexts"], module.params["palette"])

    if changes and not module.check_mode:
        # Next to Zen's own zen-sessions-backup/, one copy per run that changed something
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_dir = os.path.join(profile, "zen-sessions-ansible")
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(session_file, os.path.join(backup_dir, "zen-sessions-%s.jsonlz4" % stamp))
        shutil.copy2(containers_file, os.path.join(backup_dir, "containers-%s.json" % stamp))
        write_json_lz4(session_file, new_session)
        write_atomic(containers_file, json.dumps(new_containers).encode("utf-8"))

    module.exit_json(changed=bool(changes), changes=changes)


if __name__ == "__main__":
    main()
