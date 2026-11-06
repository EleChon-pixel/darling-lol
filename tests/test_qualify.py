"""Qualification reports, manual evidence and release policy."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/qualify.py'
SPEC = importlib.util.spec_from_file_location('qualify', SCRIPT)
qualify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualify)


def report(identifier, host, distro, mode, families, phases=None):
    return {
        'schema': qualify.SCHEMA,
        'tool': 'darling-lol qualification',
        'id': identifier,
        'mode': mode,
        'host': {'id': host, 'distro': distro, 'gpu_families': families},
        'repository': {'commit': 'a' * 40, 'dirty': False, 'patch_set_sha256': 'b' * 64},
        'phases': phases or {},
    }


class ReportTests(unittest.TestCase):
    def test_write_is_private_and_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'nested/report.json'
            document = report('one', 'host-a', 'Test Linux', 'source', ['amd'])
            qualify.write_report(path, document)
            self.assertEqual(qualify.load_report(path)['id'], 'one')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_evidence_records_hash_not_private_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'private-name.log'
            path.write_text('result\n')
            item = qualify.evidence([path])[0]
            self.assertEqual(item['name'], 'private-name.log')
            self.assertNotIn(folder, json.dumps(item))
            self.assertEqual(len(item['sha256']), 64)

    def test_manual_pass_requires_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            qualify.write_report(path, report('one', 'host-a', 'Test', 'native', ['amd']))
            args = mock.Mock(report=path, phase='client_startup', status='pass', evidence=[],
                             message='', client_version=None, allow_manual_automated=False)
            with self.assertRaisesRegex(ValueError, 'requires at least one'):
                qualify.record(args)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = {
            'minimum_runs': 2,
            'minimum_distros': 2,
            'require_clean_repository': True,
            'require_same_candidate': True,
            'required_modes': ['native', 'nix'],
            'required_gpu_groups': [['amd'], ['intel', 'nvidia']],
            'required_phases': ['source', 'build', 'client_startup'],
        }
        passed = {phase: {'status': 'pass'} for phase in self.policy['required_phases']}
        self.first = report('one', 'host-a', 'Fedora', 'native', ['amd'], passed)
        self.second = report('two', 'host-b', 'Arch', 'nix', ['nvidia'], passed)

    def test_complete_diverse_reports_pass(self):
        self.assertEqual(qualify.policy_errors(self.policy, [self.first, self.second]), [])

    def test_same_host_and_missing_phase_fail(self):
        self.second['host']['id'] = 'host-a'
        self.second['phases'].pop('build')
        errors = qualify.policy_errors(self.policy, [self.first, self.second])
        self.assertTrue(any('complete runs' in error for error in errors))
        self.assertTrue(any('independent hosts' in error for error in errors))

    def test_any_failed_phase_blocks_release(self):
        self.first['phases']['rendering'] = {'status': 'fail'}
        errors = qualify.policy_errors(self.policy, [self.first, self.second])
        self.assertTrue(any('failed phase' in error for error in errors))

    def test_dirty_or_different_candidate_fails(self):
        self.first['repository']['dirty'] = True
        self.second['repository']['commit'] = 'c' * 40
        errors = qualify.policy_errors(self.policy, [self.first, self.second])
        self.assertTrue(any('clean repository' in error for error in errors))
        self.assertTrue(any('same commit' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
