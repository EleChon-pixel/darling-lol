"""Inert fixtures: no real Darling execution or live prefix modification."""
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class IdleTests(unittest.TestCase):
    def test_unreadable_maps_fail_closed_but_disappearing_process_is_skipped(self):
        spec = importlib.util.spec_from_file_location('nix_idle_fixture', ROOT / 'scripts/nix-idle.py')
        assert spec is not None and spec.loader is not None
        idle = importlib.util.module_from_spec(spec)
        # Older versions run on import: point even those at an inert prefix.
        with tempfile.TemporaryDirectory() as folder:
            from unittest.mock import patch
            with patch.dict(os.environ, DPREFIX=folder):
                spec.loader.exec_module(idle)
        process = MagicMock()
        process.name = '123'
        process.stat.return_value.st_uid = os.getuid()
        (process / 'maps').read_text.side_effect = PermissionError('denied')
        with self.assertRaisesRegex(RuntimeError, 'Cannot inspect'):
            idle.client_active(Path('/fixture/prefix'), processes=[process])
        (process / 'maps').read_text.side_effect = FileNotFoundError()
        self.assertFalse(idle.client_active(Path('/fixture/prefix'), processes=[process]))

    def test_crash_handlers_alone_do_not_keep_the_prefix_active(self):
        spec = importlib.util.spec_from_file_location('nix_idle_handlers', ROOT / 'scripts/nix-idle.py')
        assert spec is not None and spec.loader is not None
        idle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(idle)
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / 'prefix'
            app = prefix / 'Applications/League of Legends.app'

            def process(pid, executable):
                entry = Path(folder) / 'proc' / str(pid)
                entry.mkdir(parents=True)
                (entry / 'maps').write_text(f'7f00-7f01 r-xp 0 0:0 1 {app}/Contents/MacOS/{executable}\n')
                (entry / 'cmdline').write_bytes(f'/Applications/League of Legends.app/Contents/MacOS/{executable}\0--flag\0'.encode())
                return entry

            handlers = [process(1, 'LeagueCrashHandler'), process(2, 'chrome_crashpad_handler')]
            self.assertFalse(idle.client_active(prefix, processes=handlers))
            self.assertTrue(idle.client_active(prefix, processes=[*handlers, process(3, 'LeagueClientUx')]))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for name in ('nix-session.sh', 'nix-lifecycle.py'):
            if (ROOT / 'scripts' / name).exists():
                shutil.copy(ROOT / 'scripts' / name, scripts / name)
        self.log = self.root / 'log'
        self.env = dict(os.environ, DARLING_WORKSPACE=str(self.root),
                        DPREFIX=str(self.root / 'prefix'), TEST_LOG=str(self.log))
        (self.root / 'prefix/Applications/Riot Client.app').mkdir(parents=True)
        (scripts / 'nix-state.py').write_text('raise SystemExit(0)\n')
        (scripts / 'nix-idle.py').write_text('''import os
calls = 0
def client_active(prefix, **kwargs):
    global calls
    calls += 1
    with open(os.environ['TEST_LOG'], 'a') as f:
        f.write('scan\\n')
    return calls < 2
def server_running(prefix):
    return os.environ.get('SERVER_RUNNING', '1') == '1'
def server_pid(prefix):
    try:
        with open(os.environ['TEST_LOG'] + '.server') as f:
            return int(f.read())
    except FileNotFoundError:
        return 0
''')
        (scripts / 'darling-rootless.sh').write_text('''#!/bin/bash
echo "shutdown:$*" >> "$TEST_LOG"
rm -f "$TEST_LOG.server"
# Like darling shutdown, end the client command that the server ran.
if [ -n "${CLIENT_SLEEP:-}" ]; then
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -e "$TEST_LOG.pid" ] && break; sleep 0.2; done
fi
[ -e "$TEST_LOG.pid" ] && kill "$(cat "$TEST_LOG.pid")"
if [ "${SHUTDOWN_RC:-0}" != 0 ] && [ ! -e "$TEST_LOG.retried" ]; then
  touch "$TEST_LOG.retried"
  exit "$SHUTDOWN_RC"
fi
exit 0
''')
        client = scripts / 'run.sh'
        client.write_text('''#!/usr/bin/env bash
if [ -n "${CLIENT_SLEEP:-}" ]; then
  echo "$$" > "$TEST_LOG.pid"
  exec sleep "$CLIENT_SLEEP"
fi
if [ -n "${CLIENT_STARTING:-}" ]; then
  # A launcher that is still starting: Darling's shutdown does not end it, and
  # one of its helpers starts the server again.
  (sleep 1; echo 4242 > "$TEST_LOG.server"; echo "$BASHPID" > "$TEST_LOG.helper"; exec sleep 60) &
  sleep 60
fi
echo client-finished >> "$TEST_LOG"
exit "${CLIENT_RC:-0}"
'''.replace('#!/usr/bin/env bash', '#!' + str(shutil.which('bash'))))
        client.chmod(0o755)

    def run_session(self, **environment):
        return subprocess.run(['bash', str(self.root / 'scripts/nix-session.sh')],
                              env=dict(self.env, **environment), text=True,
                              capture_output=True, timeout=10)

    def test_exit_waits_for_command_and_clients_before_shutdown(self):
        result = self.run_session()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(),
                         ['client-finished', 'scan', 'scan', 'shutdown:shutdown'])

    def test_command_failure_preserved_and_shutdown_failure_reported(self):
        result = self.run_session(CLIENT_RC='17', SHUTDOWN_RC='23')
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertIn('shutdown failed', result.stderr)
        self.assertIn('23', result.stderr)
        self.assertEqual(self.log.read_text().splitlines().count('shutdown:shutdown'), 2)
        self.assertIn('shutdown:shutdown', self.log.read_text())

    def test_stop_request_shuts_down_without_waiting_for_command_or_clients(self):
        (self.root / '.stop-request').touch()
        result = self.run_session(CLIENT_SLEEP='60')
        self.assertEqual(result.returncode, 128 + 15, result.stderr)
        self.assertIn('Stopping Darling', result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ['shutdown:shutdown'])

    def test_stop_request_ends_a_starting_command_that_restarted_the_server(self):
        (self.root / '.stop-request').touch()
        started = time.monotonic()
        result = self.run_session(CLIENT_STARTING='1')
        self.assertLess(time.monotonic() - started, 8, 'waited for the command instead of ending it')
        self.assertEqual(result.returncode, 128 + signal.SIGKILL, result.stderr)
        self.assertIn('stopping Darling again', result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ['shutdown:shutdown', 'shutdown:shutdown'])
        helper = int(Path(str(self.log) + '.helper').read_text())
        for _ in range(20):
            state = Path(f'/proc/{helper}/stat')
            if not state.exists() or state.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                break
            time.sleep(0.1)
        else:
            self.fail('the command\'s helper outlived the session')

    def test_interrupt_shuts_down_without_waiting_for_command_or_clients(self):
        session = subprocess.Popen(['bash', str(self.root / 'scripts/nix-session.sh')],
                                   env=dict(self.env, CLIENT_SLEEP='60'), text=True,
                                   stderr=subprocess.PIPE)
        pid_file = Path(str(self.log) + '.pid')
        for _ in range(50):
            if pid_file.exists():
                break
            time.sleep(0.1)
        session.send_signal(signal.SIGINT)
        _, stderr = session.communicate(timeout=10)
        self.assertEqual(session.returncode, 128 + signal.SIGINT, stderr)
        self.assertEqual(self.log.read_text().splitlines(), ['shutdown:shutdown'])

    def test_failed_shutdown_is_not_retried_once_the_server_is_gone(self):
        result = self.run_session(SHUTDOWN_RC='23', SERVER_RUNNING='0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines().count('shutdown:shutdown'), 1)

    def test_shutdown_retries_when_terminal_diagnostics_fail(self):
        spec = importlib.util.spec_from_file_location('lifecycle_fixture', self.root / 'scripts/nix-lifecycle.py')
        lifecycle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lifecycle)
        child = MagicMock()
        child.poll.return_value = 17
        child.wait.return_value = 17
        stderr = MagicMock()
        stderr.write.side_effect = OSError('terminal disconnected')
        with patch.dict(os.environ, self.env), \
             patch.object(lifecycle.signal, 'signal'), \
             patch.object(lifecycle.subprocess, 'Popen', return_value=child), \
             patch.object(lifecycle.subprocess, 'run', side_effect=[
                 subprocess.CompletedProcess([], 23), subprocess.CompletedProcess([], 0)]) as shutdown, \
             patch.object(lifecycle.time, 'sleep'), \
             patch.object(lifecycle.sys, 'stderr', stderr):
            self.assertEqual(lifecycle.main(), 17)
        self.assertEqual(shutdown.call_count, 2)
        stderr.write.assert_called()
