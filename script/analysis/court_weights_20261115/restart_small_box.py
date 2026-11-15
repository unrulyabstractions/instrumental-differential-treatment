"""Restart the small box's runner on a box that is still live, after a runner fix (2026-11-15, box 60745633).

    uv run python -m script.analysis.court_weights_20261115.restart_small_box <instance id>

Only for a box whose runner ended before any data (no responses, no Petri call): the watcher must already be
stopped. It makes a fresh export from HEAD (the launcher's own git_export and clean check), moves the old run's
markers aside on the box (RUNNER_DONE, flags/abort, the runner log; never deleted), moves the image's Hub cache into
the exempt cache path the fixed runner reads, pushes the export, restarts the runner, starts a new watcher and
ends with the launcher's own monitoring audit (box_progress.sh must say progress).
"""

from __future__ import annotations

import json
import sys
import time

from script.analysis.court_weights_20261115 import launch_small_box as S
from script.analysis.petri_20261115.box_launch_core import Launch, box_id_guard, git_export


def main() -> None:
    iid = int(sys.argv[1])
    L = Launch(S.RECIPE)
    e = [b for b in json.loads(L.registry.read_text())["boxes"] if b.get("id") == iid and not b.get("destroyed")]
    if len(e) != 1:
        raise SystemExit(f"{iid} is not one live entry of {L.registry}")
    e = e[0]
    host, port, R = e["host"], str(e["port"]), L.recipe["remote_root"]
    pid = int(e.get("watcher_pid") or 0)
    try:
        import os
        os.kill(pid, 0)
        raise SystemExit(f"the watcher pid {pid} still runs; stop it first")
    except OSError:
        pass
    exp = git_export(S.EXPORT_SPECS, S.EXPORT, S.MINE)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    res = L.ssh(host, port, box_id_guard(iid) + f"""set -e
cd {R}
test ! -e {R}/{S.OUTREL}/responses/C1 || {{ echo HAS_DATA; exit 4; }}
pgrep -f small_box_runner.sh > /dev/null && {{ echo RUNNER_LIVE; exit 5; }}
mkdir -p {R}/box/superseded_{ts}
for f in RUNNER_DONE flags/abort flags/stop box/runner.log box/runner.stdout; do
  [ -e "$f" ] && mv "$f" {R}/box/superseded_{ts}/$(echo $f | tr / _)
done
if [ -d /workspace/.hf_home/hub ]; then mkdir -p /root/.cache/huggingface && mv /workspace/.hf_home/hub /root/.cache/huggingface/hub; fi
echo MOVED_OK
""", timeout=120)
    if "MOVED_OK" not in res.stdout:
        raise SystemExit(f"box prep refused: {(res.stdout + res.stderr)[-400:]}")
    L.rsync(host, port, ["./"], f"{R}/", relative=False, cwd=S.EXPORT, extra=["--exclude=EXPORT_COMMIT"])
    L.log(f"restart {iid}: pushed the export of {exp['commit'][:12]}; old markers in box/superseded_{ts}")
    L.start_runner(host, port, "script/analysis/court_weights_20261115/box/small_box_runner.sh", iid)
    wpid = L.start_watcher(iid)
    L.registry_update(iid, watcher_pid=wpid, restarted_at=time.strftime("%FT%TZ", time.gmtime()),
                      restart_export=exp["commit"])
    ok = L.audit_monitored(iid, wpid)
    print(json.dumps({"instance": iid, "export": exp["commit"], "watcher_pid": wpid, "monitored": ok}))
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
