#!/usr/bin/env python3
"""Record reproducible darling-lol qualification runs and enforce release gates.

Safe host/source phases can be executed automatically. Interactive phases that
install or launch the Riot client are deliberately recorded by the operator;
this tool never handles credentials, submits input, or starts a live phase on
its own.
"""
import argparse
import hashlib
import json
import os
import platform
import shlex
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import doctor  # noqa: E402

SCHEMA = 1
PHASES = (
    'source', 'preflight', 'build', 'runtime_install', 'riot_bootstrap',
    'client_install', 'client_startup', 'game_startup', 'rendering',
    'audio_input', 'client_restart_1', 'client_restart_2',
    'client_restart_3', 'client_update', 'shutdown_cleanup',
)
AUTOMATED = {
    'source': [
        [sys.executable, 'scripts/validate.py'],
        [sys.executable, 'tools/riot-input-offline-check.py'],
        [sys.executable, 'tools/riot-launcher-offline-check.py'],
        [sys.executable, 'tools/riot-runtime-cleanup-offline-check.py'],
        [sys.executable, 'tools/riot-cdn-dns-offline-check.py'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
    ],
    'preflight': [[sys.executable, 'scripts/preflight.py', '--json']],
    'build': [['sh', 'scripts/build.sh']],
}


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command):
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def repo_state():
    commit = command_output(['git', 'rev-parse', 'HEAD'])
    # Porcelain includes staged and untracked source, unlike `git diff` alone.
    # build/ qualification artifacts remain ignored by the repository policy.
    dirty = bool(command_output([
        'git', 'status', '--porcelain=v1', '--untracked-files=normal',
        '--ignore-submodules=all',
    ]))
    manifest = ROOT / 'upstream/manifest.json'
    patch_hashes = {}
    try:
        entries = json.loads(manifest.read_text())['components']
    except (OSError, ValueError, KeyError, TypeError):
        entries = []
    for entry in entries:
        path = ROOT / entry.get('patch', '')
        if path.is_file():
            patch_hashes[str(path.relative_to(ROOT))] = sha256(path)
    return {
        'commit': commit or 'unknown',
        'dirty': dirty,
        'manifest_sha256': sha256(manifest) if manifest.is_file() else '',
        'patch_set_sha256': hashlib.sha256(json.dumps(
            patch_hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    }


def gpu_family(gpu):
    vendor = (gpu.get('vendor_id') or '').lower()
    driver = (gpu.get('driver') or '').lower()
    if vendor == '0x1002' or driver in ('amdgpu', 'radeon'):
        return 'amd'
    if vendor == '0x8086' or driver in ('i915', 'xe'):
        return 'intel'
    if vendor == '0x10de' or driver in ('nvidia', 'nouveau'):
        return 'nvidia'
    return 'other'


def anonymous_host_id():
    values = []
    for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            value = Path(path).read_text().strip()
        except OSError:
            continue
        if value:
            values.append(value)
            break
    values.extend((platform.node(), platform.machine()))
    return hashlib.sha256(('darling-lol-qualification\0' + '\0'.join(values)).encode()).hexdigest()[:20]


def new_report(mode):
    facts = doctor.gather()
    return {
        'schema': SCHEMA,
        'tool': 'darling-lol qualification',
        'id': str(uuid.uuid4()),
        'created': now(),
        'updated': now(),
        'mode': mode,
        'host': {
            'id': anonymous_host_id(),
            'distro': facts['host']['distro'],
            'kernel': facts['host']['kernel'],
            'arch': facts['host']['arch'],
            'gpu_families': sorted(set(gpu_family(gpu) for gpu in facts['gpus'])),
            'gpus': facts['gpus'],
        },
        'repository': repo_state(),
        'phases': {},
    }


def load_report(path):
    document = json.loads(Path(path).read_text())
    if document.get('schema') != SCHEMA or document.get('tool') != 'darling-lol qualification':
        raise ValueError('%s is not a qualification report with schema %s' % (path, SCHEMA))
    return document


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report['updated'] = now()
    temporary = path.with_name(path.name + '.tmp-%d' % os.getpid())
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def evidence(paths):
    result = []
    for value in paths:
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError('evidence is not a regular file: %s' % path)
        result.append({'name': path.name, 'size': path.stat().st_size, 'sha256': sha256(path)})
    return result


def phase_record(status, source, commands=None, artifacts=None, started=None, message=''):
    return {
        'status': status,
        'source': source,
        'started': started or now(),
        'finished': now(),
        'commands': commands or [],
        'evidence': artifacts or [],
        'message': message,
    }


def run_phase(report, phase, output):
    commands = AUTOMATED[phase]
    log_path = output / 'logs' / (phase + '.log')
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = now()
    records = []
    status = 'pass'
    with open(log_path, 'w') as log:
        os.chmod(log_path, 0o600)
        for command in commands:
            shown = shlex.join(command)
            print('[%s] %s' % (phase, shown))
            log.write('$ %s\n' % shown)
            log.flush()
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    check=False)
            records.append({'argv': command, 'exit_code': result.returncode})
            if result.returncode:
                status = 'fail'
                break
    report['phases'][phase] = phase_record(
        status, 'automated', records, evidence([log_path]), started,
        'See %s' % log_path.name,
    )
    return status == 'pass'


def run(args):
    output = Path(args.output).expanduser().resolve()
    report_path = output / 'report.json'
    if report_path.exists():
        report = load_report(report_path)
        if report['mode'] != args.mode:
            raise ValueError('existing report mode is %s, not %s' % (report['mode'], args.mode))
    else:
        report = new_report(args.mode)
    order = ['source'] if args.mode == 'source' else ['source', 'preflight', 'build']
    through = args.through or order[-1]
    if through not in order:
        raise ValueError('--through %s is not automated for mode %s' % (through, args.mode))
    for phase in order:
        if report['phases'].get(phase, {}).get('status') == 'pass' and not args.rerun:
            print('[%s] already passed; use --rerun to repeat' % phase)
        elif not run_phase(report, phase, output):
            write_report(report_path, report)
            print('FAILED: %s; report: %s' % (phase, report_path), file=sys.stderr)
            return 1
        write_report(report_path, report)
        if phase == through:
            break
    print('PASS through %s; report: %s' % (through, report_path))
    return 0


def record(args):
    report_path = Path(args.report).expanduser().resolve()
    report = load_report(report_path)
    if args.phase in AUTOMATED and not args.allow_manual_automated:
        raise ValueError('%s is automated; use run or pass --allow-manual-automated' % args.phase)
    artifacts = evidence(args.evidence)
    if args.status == 'pass' and not artifacts:
        raise ValueError('a manual pass requires at least one --evidence file')
    report['phases'][args.phase] = phase_record(
        args.status, 'manual', artifacts=artifacts, message=args.message or '')
    if args.client_version:
        report['client_version'] = args.client_version
    write_report(report_path, report)
    print('%s: %s recorded in %s' % (args.phase, args.status, report_path))
    return 0


def policy_errors(policy, reports):
    errors = []
    passed = [report for report in reports
              if all(report.get('phases', {}).get(phase, {}).get('status') == 'pass'
                     for phase in policy['required_phases'])]
    if len(passed) < policy['minimum_runs']:
        errors.append('need %d complete runs; found %d' % (policy['minimum_runs'], len(passed)))
    ids = {report.get('host', {}).get('id') for report in passed}
    if len(ids - {None}) < policy['minimum_runs']:
        errors.append('complete runs must come from %d independent hosts' % policy['minimum_runs'])
    distros = {report.get('host', {}).get('distro') for report in passed}
    if len(distros - {None}) < policy['minimum_distros']:
        errors.append('need %d distributions; found %d' %
                      (policy['minimum_distros'], len(distros - {None})))
    modes = {report.get('mode') for report in passed}
    for mode in policy['required_modes']:
        if mode not in modes:
            errors.append('missing a complete %s-mode run' % mode)
    families = {family for report in passed for family in report.get('host', {}).get('gpu_families', [])}
    for group in policy['required_gpu_groups']:
        if not families.intersection(group):
            errors.append('missing GPU family from {%s}' % ', '.join(group))
    if policy.get('require_clean_repository'):
        dirty = [report.get('id', '<unknown>') for report in passed
                 if report.get('repository', {}).get('dirty') is not False]
        if dirty:
            errors.append('complete runs must use a clean repository: %s' % ', '.join(dirty))
    if policy.get('require_same_candidate') and passed:
        commits = {report.get('repository', {}).get('commit') for report in passed}
        patch_sets = {report.get('repository', {}).get('patch_set_sha256') for report in passed}
        if None in commits or len(commits) != 1:
            errors.append('complete runs do not identify the same commit')
        if None in patch_sets or len(patch_sets) != 1:
            errors.append('complete runs do not identify the same patch set')
    for report in reports:
        failed = sorted(phase for phase, result in report.get('phases', {}).items()
                        if result.get('status') == 'fail')
        if failed:
            errors.append('%s contains failed phase(s): %s' %
                          (report.get('id', '<unknown>'), ', '.join(failed)))
    return errors


def gate(args):
    policy = json.loads(Path(args.policy).read_text())
    reports = [load_report(path) for path in args.reports]
    errors = policy_errors(policy, reports)
    if errors:
        print('RELEASE GATE: FAIL')
        for error in errors:
            print('- ' + error)
        return 1
    print('RELEASE GATE: PASS (%d qualified runs)' % len(reports))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)

    runner = subparsers.add_parser('run', help='run safe automated qualification phases')
    runner.add_argument('--mode', choices=('source', 'native', 'nix'), required=True)
    runner.add_argument('--output', required=True)
    runner.add_argument('--through', choices=('source', 'preflight', 'build'))
    runner.add_argument('--rerun', action='store_true')
    runner.set_defaults(function=run)

    recorder = subparsers.add_parser('record', help='record one operator-observed phase')
    recorder.add_argument('--report', required=True)
    recorder.add_argument('--phase', choices=PHASES, required=True)
    recorder.add_argument('--status', choices=('pass', 'fail', 'skip'), required=True)
    recorder.add_argument('--evidence', action='append', default=[])
    recorder.add_argument('--message', help='short public note; never include account data')
    recorder.add_argument('--client-version')
    recorder.add_argument('--allow-manual-automated', action='store_true')
    recorder.set_defaults(function=record)

    checker = subparsers.add_parser('gate', help='evaluate reports against release policy')
    checker.add_argument('--policy', default=str(ROOT / 'qualification/release-policy.json'))
    checker.add_argument('reports', nargs='+')
    checker.set_defaults(function=gate)

    args = parser.parse_args(argv)
    try:
        return args.function(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
