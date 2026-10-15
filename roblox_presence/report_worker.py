"""Bounded report renderer. Internal JSON arrives over stdin; HTML returns on stdout."""

import json
import os
import resource
import sys
from pathlib import Path
from types import SimpleNamespace


def main():
    try:
        resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 10))
        os.setpriority(os.PRIO_PROCESS, 0, 19)
        from .report import render, server_zone, snapshot
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            return 2
        data = json.loads(raw)
        config = SimpleNamespace(state_dir=Path(data['state_dir']), poll_seconds=data['poll_seconds'],
                                 scope=f"{data['observer_user_id']}:{data['target_user_id']}")
        now = data['now']
        zone, label = server_zone()
        content = render(snapshot(config, now, zone), now, zone, label, config.poll_seconds).encode()
        if len(content) > 32 * 1024 * 1024:
            return 2
        sys.stdout.buffer.write(content)
        return 0
    except BaseException:
        return 2  # No arbitrary exception/path/config/credential output.


if __name__ == '__main__':
    sys.exit(main())
