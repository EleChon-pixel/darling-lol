"""system_profiler hardware/software overviews, with stub guest commands; never starts Darling."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/darling-system_profiler.sh'

IOREG = '''+-o MacBookPro16,1  <class IOPlatformExpertDevice, id 0x100000110, registered, matched, active, busy 0 (0 ms), retain 30>
    {
      "IOPlatformSerialNumber" = "USER-SUPPLIED"
      "model" = <"MacBookPro16,1">
      "manufacturer" = <"Apple Inc.">
      "IOPlatformUUID" = "8E1F2A3B-4C5D-4E6F-8A7B-9C0D1E2F3A4B"
      "provisioning_UDID" = "8E1F2A3B-4C5D-4E6F-8A7B-9C0D1E2F3A4B"
      "ROM" = <0a1b2c3d4e5f>
    }
'''
SYSCTL = {
    'hw.physicalcpu': '8', 'hw.packages': '1', 'hw.memsize': str(32 << 30),
    'machdep.cpu.brand_string': 'AMD Ryzen 7 5800X 8-Core Processor & more',
    'hw.l2cachesize': str(512 << 10), 'hw.l3cachesize': str(32 << 20), 'hw.cpufrequency': '3800000000',
}


class SystemProfilerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.bin = Path(self.folder.name)
        self.stub('sysctl', 'import sys\nvalues = %r\nname = sys.argv[-1]\n'
                  'if name not in values: sys.exit(1)\nprint(values[name])' % SYSCTL)
        self.stub('sw_vers', 'import sys\nprint({"-productName": "macOS", "-productVersion": "11.7.4", '
                  '"-buildVersion": "20G1120"}[sys.argv[1]])')
        self.stub('uname', 'print("Darwin 20.6.0")')
        self.stub('hostname', 'print("darling")')
        self.stub('ioreg', 'import sys\nsys.stdout.write(%r)' % IOREG)

    def tearDown(self):
        self.folder.cleanup()

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!%s\n%s\n' % (sys.executable, body))
        path.chmod(0o755)

    def run_profiler(self, *args):
        env = {'PATH': '%s:%s' % (self.bin, os.environ['PATH']), 'USER': 'player'}
        return subprocess.run(['sh', str(SCRIPT), *args], env=env, check=True, capture_output=True, text=True).stdout

    def xml_items(self, data_type):
        report = plistlib.loads(self.run_profiler('-xml', data_type).encode())
        self.assertEqual(report[0]['_dataType'], data_type)
        return report[0]['_items'][0]

    def test_hardware_reports_iokit_identity_and_sysctl_values(self):
        item = self.xml_items('SPHardwareDataType')
        self.assertEqual(item, {
            '_name': 'hardware_overview', 'machine_name': 'MacBook Pro', 'machine_model': 'MacBookPro16,1',
            'cpu_type': 'AMD Ryzen 7 5800X 8-Core Processor & more', 'current_processor_speed': '3.8 GHz',
            'packages': 1, 'number_processors': 8, 'l2_cache_core': '512 KB', 'l3_cache': '32 MB',
            'physical_memory': '32 GB', 'serial_number': 'USER-SUPPLIED',
            'platform_UUID': '8E1F2A3B-4C5D-4E6F-8A7B-9C0D1E2F3A4B',
            'provisioning_UDID': '8E1F2A3B-4C5D-4E6F-8A7B-9C0D1E2F3A4B',
        })
        text = self.run_profiler('SPHardwareDataType')
        self.assertIn('      Serial Number (system): USER-SUPPLIED\n', text)
        self.assertIn('      Model Name: MacBook Pro\n', text)

    def test_missing_iokit_and_sysctl_values_are_omitted(self):
        self.stub('ioreg', 'import sys\nsys.exit(1)')
        self.stub('sysctl', 'import sys\nsys.exit(1)')
        self.assertEqual(self.xml_items('SPHardwareDataType'), {'_name': 'hardware_overview'})
        self.assertNotIn('Serial Number', self.run_profiler('SPHardwareDataType'))

    def test_software_overview(self):
        item = self.xml_items('SPSoftwareDataType')
        self.assertEqual(item, {
            '_name': 'os_overview', 'os_version': 'macOS 11.7.4 (20G1120)', 'kernel_version': 'Darwin 20.6.0',
            'boot_volume': 'Macintosh HD', 'boot_mode': 'normal_boot', 'local_host_name': 'darling',
            'user_name': 'player',
        })
        self.assertIn('      Boot Mode: Normal\n', self.run_profiler('SPSoftwareDataType'))

    def displays_with(self, identity):
        """SPDisplaysDataType for a host with an NVIDIA and an Intel card and this identity."""
        root = Path(self.folder.name) / 'root'
        for card, vendor, device in (('card0', '0x10de', '0x25a2'), ('card1', '0x8086', '0x46a6')):
            folder = root / 'host/sys/class/drm' / card / 'device'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'vendor').write_text(vendor + '\n')
            (folder / 'device').write_text(device + '\n')
        (root / 'identity.conf').write_text(identity)
        script = root / 'system_profiler'
        script.write_text(SCRIPT.read_text()
                          .replace('/Volumes/SystemRoot', str(root / 'host'))
                          .replace('/private/etc/darling-runtime-identity.conf', str(root / 'identity.conf')))
        env = {'PATH': '%s:%s' % (self.bin, os.environ['PATH']), 'USER': 'player'}
        return subprocess.run(['sh', str(script), 'SPDisplaysDataType'], env=env, check=True,
                              capture_output=True, text=True).stdout

    def test_a_profile_with_one_gpu_reports_one_gpu(self):
        mini = self.displays_with('hw.model=Macmini8,1\ngpu.integrated.name=Intel UHD Graphics 630\n'
                                  'gpu.integrated.vendor=0x8086\ngpu.integrated.device=0x3E9B\n')
        self.assertEqual(mini.count('Chipset Model:'), 1)
        self.assertIn('Chipset Model: Intel UHD Graphics 630', mini)
        self.assertIn('Device ID: 0x3e9b', mini)
        self.assertNotIn('AMD', mini)
        self.assertNotIn('NVIDIA', mini)
        laptop = self.displays_with('gpu.integrated.name=Intel UHD Graphics 630\n'
                                    'gpu.discrete.name=AMD Radeon Pro 5500M\n')
        self.assertEqual(laptop.count('Chipset Model:'), 2)
        self.assertIn('Chipset Model: AMD Radeon Pro 5500M', laptop)

    def test_listed_and_default_types(self):
        listed = self.run_profiler('-listDataTypes')
        self.assertIn('SPHardwareDataType', listed)
        self.assertIn('SPSoftwareDataType', listed)
        types = [entry['_dataType'] for entry in plistlib.loads(self.run_profiler('-xml').encode())]
        self.assertEqual(types[:2], ['SPHardwareDataType', 'SPSoftwareDataType'])


if __name__ == '__main__':
    unittest.main()
