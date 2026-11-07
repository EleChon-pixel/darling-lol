"""Provisioning contracts using disposable prefixes and runtime metadata."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/configure-darling-platform.py'
spec = importlib.util.spec_from_file_location('provisioning', SCRIPT)
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)


class ProvisioningChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'prefix with spaces'
        self.runtime = self.root / 'runtime with spaces'
        self.version = self.runtime / 'System/Library/CoreServices/SystemVersion.plist'
        self.version.parent.mkdir(parents=True)
        self.metadata = {'ProductName': 'Darling', 'ProductVersion': '11.7.4', 'ProductBuildVersion': 'Darling-test'}
        self.version.write_bytes(plistlib.dumps(self.metadata))
        self.command = [sys.executable, str(SCRIPT), '--prefix', str(self.prefix),
                        '--provision', '--runtime-root', str(self.runtime)]

    def run_cli(self, *args):
        result = subprocess.run([*self.command, *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_generated_shapes_uuid_byte_order_and_prefix_independence(self):
        values = [platform.provision({}) for _ in range(20)]
        for value in values:
            for key, length in [('IOPlatformSerialNumber', 12), ('mlb-serial-number', 17)]:
                self.assertEqual(len(value[key]), length)
                self.assertTrue(set(value[key]) <= set(platform.BASE34))
            parsed = uuid.UUID(value['IOPlatformUUID'])
            self.assertEqual(parsed.version, 4)
            self.assertEqual(parsed.variant, uuid.RFC_4122)
            self.assertEqual(value['system-id'], parsed.bytes_le)
            self.assertEqual(value['provisioning_UDID'], str(parsed).upper())
            self.assertEqual(len(value['ROM']), 6)
            self.assertEqual(value['ROM'][0] & 3, 2)
        self.assertEqual(len({v['IOPlatformUUID'] for v in values}), len(values))

    def test_preview_does_not_create_prefix(self):
        preview = json.loads(self.run_cli().stdout)
        self.assertIn('provisioning_UDID', preview['properties'])
        self.assertFalse(self.prefix.exists())

    def test_write_four_files_idempotent_and_importable(self):
        self.run_cli('--write')
        canonical = platform.destination(self.prefix)
        legacy = self.prefix / 'private/etc/darling-smbios.conf'
        version = self.prefix / 'System/Library/CoreServices/SystemVersion.plist'
        runtime_identity = self.prefix / 'private/etc/darling-runtime-identity.conf'
        self.assertEqual(platform.load(canonical), platform.load(legacy))
        self.assertEqual(version.read_bytes(), self.version.read_bytes())
        values = platform.load_runtime_identity(runtime_identity)
        self.assertEqual(values['hw.model'], 'MacBookPro16,1')
        self.assertEqual(values['kern.osproductversion'], self.metadata['ProductVersion'])
        self.assertEqual(values['kern.osversion'], self.metadata['ProductBuildVersion'])
        files = [canonical, legacy, runtime_identity, version]
        snapshot = [(f.read_bytes(), f.stat().st_mtime_ns) for f in files]
        self.assertIn('unchanged', self.run_cli('--write').stdout)
        self.assertEqual(snapshot, [(f.read_bytes(), f.stat().st_mtime_ns) for f in files])
        for f in [canonical, legacy, runtime_identity]:
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)

    def test_named_hardware_and_os_profiles_are_consistent(self):
        result = self.run_cli('--hardware-profile', 'imac20,1', '--os-profile',
                              'sonoma-14.7-23H124', '--cpu-brand-string',
                              'Fixture CPU 3.10GHz', '--write')
        self.assertIn('saved', result.stdout)
        properties = platform.load(platform.destination(self.prefix))
        self.assertEqual(properties['model'], 'iMac20,1')
        self.assertEqual(properties['product-name'], 'iMac20,1')
        self.assertEqual(properties['manufacturer'], 'Apple Inc.')
        runtime = platform.load_runtime_identity(
            self.prefix / 'private/etc/darling-runtime-identity.conf')
        self.assertEqual(runtime, {
            'hw.model': 'iMac20,1',
            'machdep.cpu.vendor': 'GenuineIntel',
            'machdep.cpu.brand_string': 'Fixture CPU 3.10GHz',
            'kern.osproductversion': '14.7',
            'kern.osversion': '23H124',
            'machdep.cpu.signature': '0xA0653',
            'hw.cpufamily': '0x0F817246',
            'hw.cpufrequency': '3100000000',
            'cpu.threads_per_core': '2',
            'kern.hostname': 'iMac.local',
            'gpu.integrated.name': 'Intel UHD Graphics 630',
            'gpu.integrated.vendor': '0x8086',
            'gpu.integrated.device': '0x9BC8',
            'gpu.discrete.name': 'AMD Radeon Pro 5300',
            'gpu.discrete.vendor': '0x1002',
            'gpu.discrete.device': '0x7340',
            'home.isolated': '1',
        })
        version = plistlib.loads((self.prefix /
            'System/Library/CoreServices/SystemVersion.plist').read_bytes())
        self.assertEqual(version['ProductVersion'], runtime['kern.osproductversion'])
        self.assertEqual(version['ProductBuildVersion'], runtime['kern.osversion'])
        self.assertEqual(version['FullVersionString'], 'Version 14.7 (Build 23H124)')

    def test_profile_serial_has_model_layout(self):
        import re
        for _ in range(50):
            serial = platform.profile_serial(platform.HARDWARE_PROFILES['macbookpro16,1'])
            self.assertRegex(serial, r'^C02[ZCD][1-9CDFGHJKLMNPQRTVWXY][0-9A-HJ-NP-Z]{3}MD6[MNRTVW]$')
        self.assertIsNone(platform.profile_serial(platform.HARDWARE_PROFILES['imac20,1']))
        saved = platform.provision({'IOPlatformSerialNumber': 'CH0N16UAJ1SR'}, None, 'macbookpro16,1')
        self.assertEqual(saved['IOPlatformSerialNumber'], 'CH0N16UAJ1SR')
        fresh = platform.provision({'IOPlatformSerialNumber': 'CH0N16UAJ1SR'}, None, 'macbookpro16,1', True)
        self.assertTrue(re.match(r'^C02.{5}MD6.$', fresh['IOPlatformSerialNumber']))

    def test_runtime_identity_accepts_files_without_optional_keys(self):
        core = {'hw.model': 'MacBookPro16,1', 'machdep.cpu.vendor': 'GenuineIntel',
                'machdep.cpu.brand_string': 'Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz',
                'kern.osproductversion': '14.7', 'kern.osversion': '23H124'}
        self.assertEqual(platform.load_runtime_identity_bytes(platform.encode_runtime_identity(core)), core)
        with self.assertRaises(ValueError):
            platform.load_runtime_identity_bytes(b'hw.model=X\n')
        with self.assertRaises(ValueError):
            platform.encode_runtime_identity({**core, 'kern.bogus': '1'})

    def test_runtime_profile_validation_fails_before_writes(self):
        for brand in ('bad\nbrand', 'bad=brand', 'x' * 129):
            result = subprocess.run([*self.command, '--hardware-profile', 'macbookpro16,1',
                                     '--cpu-brand-string', brand, '--write'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(platform.destination(self.prefix).exists())

    def test_known_defaults_replaced_and_custom_values_preserved(self):
        legacy = self.prefix / 'private/etc/darling-smbios.conf'
        legacy.parent.mkdir(parents=True)
        original = (f'SMBIOS_SERIAL_NUMBER={platform.KNOWN_SERIAL}\n'
                    f'SMBIOS_PLATFORM_UUID={platform.KNOWN_UUID}\n'
                    'SMBIOS_MLB=CUSTOM-BOARD\nSMBIOS_MODEL=CustomModel\nSMBIOS_ROM=001122334455\n').encode()
        legacy.write_bytes(original)
        self.run_cli('--write')
        result = platform.load(platform.destination(self.prefix))
        self.assertNotEqual(result['IOPlatformSerialNumber'], platform.KNOWN_SERIAL)
        self.assertNotEqual(result['IOPlatformUUID'], platform.KNOWN_UUID)
        self.assertEqual(result['mlb-serial-number'], 'CUSTOM-BOARD')
        self.assertEqual(result['model'], 'CustomModel')
        self.assertEqual(result['ROM'], bytes.fromhex('001122334455'))
        self.assertEqual(legacy.with_name(legacy.name+'.before-platform-change').read_bytes(), original)
        before = result.copy()
        self.run_cli('--write')
        self.assertEqual(platform.load(platform.destination(self.prefix)), before)

    def test_custom_canonical_identity_wins_over_legacy_defaults(self):
        custom = platform.provision({})
        platform.save(self.prefix, custom)
        legacy = self.prefix / 'private/etc/darling-smbios.conf'
        legacy.write_text(f'SMBIOS_SERIAL_NUMBER={platform.KNOWN_SERIAL}\nSMBIOS_PLATFORM_UUID={platform.KNOWN_UUID}\n')
        self.run_cli('--write')
        self.assertEqual(platform.load(platform.destination(self.prefix)), custom)

    def test_explicit_oui_and_existing_rom(self):
        value = platform.provision({}, bytes.fromhex('001122'))
        self.assertEqual(value['ROM'][:3], bytes.fromhex('001122'))
        self.assertEqual(platform.provision(value, bytes.fromhex('AABBCC')), value)
        for oui in ['1234', '011122', 'garbage']:
            result = subprocess.run([*self.command, '--rom-oui', oui, '--write'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(platform.destination(self.prefix).exists())

    def test_version_source_required_before_identity_written(self):
        for raw in [b'not a plist', plistlib.dumps({'ProductVersion': '99.0'})]:
            self.version.write_bytes(raw)
            result = subprocess.run([*self.command, '--write'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(platform.destination(self.prefix).exists())
            self.assertFalse((self.prefix / 'private/etc/darling-smbios.conf').exists())
        self.version.unlink()
        result = subprocess.run([*self.command, '--write'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)

    def test_system_version_backup_and_symlink_preflight(self):
        target = self.prefix / 'System/Library/CoreServices/SystemVersion.plist'
        target.parent.mkdir(parents=True)
        original = plistlib.dumps({'ProductVersion': 'old'})
        target.write_bytes(original)
        self.run_cli('--write')
        self.assertEqual(target.with_name(target.name+'.before-platform-change').read_bytes(), original)
        self.assertEqual(plistlib.loads(target.read_bytes()), self.metadata)
        target.unlink()
        target.symlink_to(self.version)
        before = platform.destination(self.prefix).read_bytes()
        result = subprocess.run([*self.command, '--set', 'model=Changed', '--write'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(platform.destination(self.prefix).read_bytes(), before)

    def test_live_prefix_is_not_changed(self):
        self.prefix.mkdir()
        (self.prefix / '.init.pid').write_text(str(os.getpid()))
        result = subprocess.run([*self.command, '--write'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(platform.destination(self.prefix).exists())

    def test_concurrent_writers_share_one_identity(self):
        workers = [subprocess.Popen([*self.command, '--write'], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True) for _ in range(4)]
        for worker in workers:
            output, error = worker.communicate(timeout=15)
            self.assertEqual(worker.returncode, 0, error)
        canonical = platform.destination(self.prefix)
        self.assertEqual(platform.load(canonical), platform.load(self.prefix / 'private/etc/darling-smbios.conf'))
        self.assertFalse(canonical.with_name(canonical.name+'.before-platform-change').exists())

    def test_custom_system_id_is_preserved_and_udid_mismatch_rejected(self):
        value = platform.provision({})
        self.assertEqual(platform.provision({'provisioning_UDID': value['provisioning_UDID']})['IOPlatformUUID'], value['IOPlatformUUID'])
        supplied = {'system-id': value['system-id']}
        self.assertEqual(platform.provision(supplied)['IOPlatformUUID'], value['IOPlatformUUID'])
        with self.assertRaises(ValueError):
            platform.validate({'IOPlatformUUID': value['IOPlatformUUID'], 'provisioning_UDID': str(uuid.uuid4())})

    def test_replace_known_defaults_only_touches_shared_identities(self):
        replace = [sys.executable, str(SCRIPT), '--prefix', str(self.prefix), '--runtime-root',
                   str(self.runtime), '--replace-known-defaults', '--write']
        # A prefix without identity files is not created or provisioned.
        result = subprocess.run(replace, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.prefix.exists())
        # A custom identity stays byte-for-byte unchanged.
        custom = {'IOPlatformSerialNumber': 'MY-SERIAL', 'model': 'CustomModel'}
        platform.save(self.prefix, custom)
        canonical = platform.destination(self.prefix)
        before = canonical.read_bytes()
        result = subprocess.run(replace, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(canonical.read_bytes(), before)
        self.assertFalse((self.prefix / 'private/etc/darling-smbios.conf').exists())
        # The shared values are replaced; custom fields survive and a rerun is stable.
        platform.save(self.prefix, {**custom, 'IOPlatformSerialNumber': platform.KNOWN_SERIAL,
                                    'IOPlatformUUID': platform.KNOWN_UUID})
        result = subprocess.run(replace, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = platform.load(canonical)
        self.assertNotEqual(value['IOPlatformSerialNumber'], platform.KNOWN_SERIAL)
        self.assertNotEqual(value['IOPlatformUUID'], platform.KNOWN_UUID)
        self.assertFalse(platform.has_known_defaults(value))
        self.assertEqual(value['model'], 'CustomModel')
        self.assertNotIn('board-id', value)
        self.assertNotIn('manufacturer', value)
        self.assertEqual(platform.load(self.prefix / 'private/etc/darling-smbios.conf'), value)
        after = canonical.read_bytes()
        subprocess.run(replace, capture_output=True, text=True, check=True)
        self.assertEqual(canonical.read_bytes(), after)

    def test_standalone_fields_derived_from_known_uuid_are_replaced(self):
        known_id = uuid.UUID(platform.KNOWN_UUID).bytes_le
        for supplied in [{'system-id': known_id}, {'provisioning_UDID': platform.KNOWN_UUID}]:
            value = platform.provision(supplied)
            self.assertNotEqual(value['IOPlatformUUID'], platform.KNOWN_UUID)
            self.assertNotEqual(value['system-id'], known_id)
