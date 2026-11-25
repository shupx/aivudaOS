"""Linux Popen ownership and cleanup, including children that create sessions.

The guardian reads a private pipe. EOF also occurs when its owner is SIGKILLed.
PID start times prevent cleanup from signalling a recycled PID.
"""
import json
import os
from pathlib import Path
import select
import signal
import sys
import time


def process_stat(path):
    # The parenthesized process name may contain ')' or non-UTF-8 bytes.
    fields = path.read_bytes().rsplit(b')', 1)[1].split()
    if fields[0] != b'Z':
        return int(fields[1]), int(fields[2]), fields[19].decode('ascii')
    return None


def processes():
    result = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            stat = process_stat(path)
            if stat is not None:
                result[int(path.parent.name)] = stat
        except (OSError, ValueError, IndexError):
            continue
    return result


def remember(tree, root, stamp, table=None):
    if table is None:
        table = processes()
    root_owned = root in table and table[root][2] == stamp
    if root_owned:
        tree[root] = stamp
    # Keep descendants already observed even after they are reparented.
    changed = True
    while changed:
        changed = False
        for pid, (parent, group, identity) in table.items():
            parent_owned = parent in tree and parent in table and table[parent][2] == tree[parent]
            if (parent_owned or (root_owned and group == root)) and pid not in tree:
                tree[pid] = identity
                changed = True
    return table


def send(tree, sig):
    table = processes()
    # Descendants first, so an entrypoint cannot exit before children are signalled.
    for pid, stamp in reversed(list(tree.items())):
        if pid in table and table[pid][2] == stamp:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass


def terminate(tree, root, stamp, timeout=5.0):
    remember(tree, root, stamp)
    send(tree, signal.SIGCONT)
    send(tree, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while True:
        table = remember(tree, root, stamp)
        alive = {pid for pid, identity in list(tree.items()) if pid in table and table[pid][2] == identity}
        if not alive:
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    send(tree, signal.SIGKILL)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        table = processes()
        if not any(pid in table and table[pid][2] == identity for pid, identity in list(tree.items())):
            return
        time.sleep(0.05)
    raise RuntimeError('Application processes survived cleanup')


def guardian():
    roots = {}
    trees = {}
    pending = b''
    while True:
        if roots:
            table = processes()
            for pid, stamp in roots.items():
                remember(trees[pid], pid, stamp, table)
        ready, _, _ = select.select([sys.stdin.buffer], [], [], 0.1)
        if not ready:
            continue
        data = os.read(sys.stdin.fileno(), 65536)
        if not data:
            break
        pending += data
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            item = json.loads(line)
            pid = item['pid']
            if item['action'] == 'add':
                roots[pid] = item['stamp']
                trees[pid] = {pid: item['stamp']}
            elif item['action'] == 'remove':
                roots.pop(pid, None)
                trees.pop(pid, None)
    # Stop all applications concurrently so the grace period is not per app.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(roots))) as pool:
        futures = [pool.submit(terminate, trees[pid], pid, stamp) for pid, stamp in roots.items()]
        for future in futures:
            future.result()


if __name__ == '__main__':
    guardian()
