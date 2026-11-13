#!/usr/bin/env python3
"""Read-only, fail-closed rootless maintenance preflight. Never signal a process."""
import os
from pathlib import Path

# Crash handlers do not exit after their clients under Darling, so a mapping by
# one of them alone does not mean that a client still uses the prefix.
CRASH_HANDLERS = {'RiotClientCrashHandler', 'LeagueCrashHandler', 'chrome_crashpad_handler'}


def crash_handler(process):
    executable = (process / 'cmdline').read_bytes().split(b'\0', 1)[0]
    return os.path.basename(executable.decode(errors='replace')) in CRASH_HANDLERS


def server_pid(prefix):
    """PID of the live (not zombie) process the prefix marker names, or 0."""
    try:
        pid = int((prefix / '.init.pid').read_text().strip())
    except FileNotFoundError:
        return 0
    if pid <= 0:
        return 0
    try:
        status = (Path('/proc') / str(pid) / 'status').read_text()
    except (FileNotFoundError, ProcessLookupError):
        return 0
    if any(line.startswith('State:') and line.split()[1] == 'Z' for line in status.splitlines()):
        return 0
    return pid


def server_running(prefix):
    """Whether the prefix marker names a live (not zombie) process."""
    return bool(server_pid(prefix))


def client_active(prefix, *, processes=None):
    """Check exact-prefix mappings; only vanished processes may be skipped."""
    paths = [str(prefix / name) + '/' for name in (
        'Applications/Riot Client.app', 'Applications/League of Legends.app',
        'Users/Shared/Riot Games')]
    namespace_map = Path('/proc/self/uid_map').read_text()
    for process in Path('/proc').iterdir() if processes is None else processes:
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            # The outer live-marker gate excludes earlier Darling namespaces.
            # Host processes are not ours to inspect; their maps are commonly
            # unreadable from a child user namespace (including systemd --user).
            if processes is None and (process / 'uid_map').read_text() != namespace_map:
                continue
            mappings = (process / 'maps').read_text()
            if any(path in mappings for path in paths) and not crash_handler(process):
                return True
        except (FileNotFoundError, ProcessLookupError):
            # Process exited between enumeration and inspection.
            continue
        except OSError as error:
            raise RuntimeError(f'Cannot inspect process {process.name}; cannot establish that the prefix is idle: {error}') from error
    return False


def main():
    prefix = Path(os.environ.get('DPREFIX', str(Path.home() / '.darling'))).resolve()
    try:
        running = server_running(prefix)
    except ValueError:
        raise SystemExit('Cannot validate prefix server marker; inspect it before maintenance.')
    except OSError as error:
        raise SystemExit(f'Cannot validate prefix server marker: {error}') from error
    if running:
        raise SystemExit('Prefix has a live server marker; exit Riot/League and run darling-lol --stop before updating. No process was stopped.')
    try:
        active = client_active(prefix)
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    if active:
        raise SystemExit('A client maps this prefix; exit it before rootless maintenance. No process was stopped.')


if __name__ == '__main__':
    main()
