"""The recorded IOKit plane keeps a Mac's shape and nothing of the recorded machine."""
import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_ioregistry', ROOT / 'tools/build-ioregistry.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

DUMP = '''+-o Root  <class IORegistryEntry, id 0x100000100, retain 20>
  | {
  |   "IOConsoleUsers" = ({"kCGSSessionUserNameKey"="someone"})
  | }
  |
  +-o Macmini8,1  <class IOPlatformExpertDevice, id 0x100000114, registered, matched, active, busy 0 (1 ms), retain 45>
    | {
    |   "IOPlatformSerialNumber" = "C07REALSERIAL"
    |   "manufacturer" = <"Apple Inc.">
    | }
    |
    +-o AppleACPIPlatformExpert  <class AppleACPIPlatformExpert, id 0x100000115, registered, matched, active, busy 0 (1 ms), retain 40>
    | | {
    | |   "IOClass" = "AppleACPIPlatformExpert"
    | |   "reg" = <00**00>
    | |   "counts" = {"a"=1,"b"=(Yes,No,"x")}
    | |   "note" = "talks to 00:11:22:aa:bb:cc"
    | | }
    | |
    | +-o IOPMrootDomain  <class IOPMrootDomain, id 0x100000118, registered, matched, active, busy 0 (0 ms), retain 60>
    | +-o GIGE@0  <class IOPCIDevice, id 0x100000200, registered, matched, active, busy 0 (0 ms), retain 9>
    | | | {
    | | |   "vendor-id" = <e4140000>
    | | |   "local-mac-address" = <001122334455>
    | | | }
    | | |
    | | +-o BCM5701Enet  <class BCM5701Enet, id 0x100000201, registered, matched, active, busy 0 (0 ms), retain 9>
    | |   | {
    | |   |   "IOMACAddress" = <001122334455>
    | |   | }
    | |   |
    | |   +-o en0  <class IOEthernetAVBInterface, id 0x100000202, registered, matched, active, busy 0 (0 ms), retain 9>
    | |       {
    | |         "BSD Name" = "en0"
    | |         "IOMACAddress" = <001122334455>
    | |       }
    | |
    | +-o TBIP  <class AppleThunderboltIPPort, id 0x100000210, registered, matched, active, busy 0 (0 ms), retain 9>
    | | +-o en2  <class IOEthernetInterface, id 0x100000211, registered, matched, active, busy 0 (0 ms), retain 9>
    | |     {
    | |       "BSD Name" = "en2"
    | |     }
    | |
    | +-o NCM  <class AppleUSBNCMData, id 0x100000220, registered, matched, active, busy 0 (0 ms), retain 9>
    | | +-o en6  <class IOEthernetInterface, id 0x100000221, registered, matched, active, busy 0 (0 ms), retain 9>
    | |     {
    | |       "BSD Name" = "en6"
    | |     }
    | |
    | +-o ANS2  <class IONVMeBlockStorageDevice, id 0x100000230, registered, matched, active, busy 0 (0 ms), retain 9>
    |     {
    |       "Device Characteristics" = {"Serial Number"="REALDISKSERIAL","Medium Type"="Solid State"}
    |     }
    |
    +-o IOResources  <class IOResources, id 0x100000119, registered, matched, active, busy 0 (0 ms), retain 80>
      +-o display0  <class IODisplayConnect, id 0x100000300, registered, matched, active, busy 0 (0 ms), retain 9>
        +-o AppleDisplay  <class AppleDisplay, id 0x100000301, registered, matched, active, busy 0 (0 ms), retain 9>
'''


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dump = Path(self.tmp.name) / 'IOReg.txt'
        dump.write_text(DUMP)
        self.data, self.stats = tool.build(tool.read_dump(dump), 'Macmini8,1')
        self.entries = {entry['n']: entry for entry in self.data['entries']}

    def test_tree_shape_and_values(self):
        self.assertEqual(self.data['model'], 'Macmini8,1')
        self.assertNotIn('Root', self.entries)
        self.assertEqual(self.entries['Macmini8,1']['p'], -1)
        names = [entry['n'] for entry in self.data['entries']]
        expert = self.entries['AppleACPIPlatformExpert']
        self.assertEqual(names[expert['p']], 'Macmini8,1')
        self.assertEqual(names[self.entries['en0']['p']], 'BCM5701Enet')
        self.assertEqual(expert['P']['counts'], {'a': 1, 'b': [True, False, 'x']})
        self.assertEqual(self.entries['GIGE@0']['P']['vendor-id'], bytes.fromhex('e4140000'))
        self.assertEqual(self.entries['en0']['s'][0], 'IOEthernetInterface')

    def test_nothing_of_the_recorded_machine_is_kept(self):
        blob = repr(self.data)
        for secret in ('C07REALSERIAL', 'REALDISKSERIAL', 'someone', '001122334455',
                       b'\\x00\\x11"3DU'.decode(), '00:11:22:aa:bb:cc'):
            self.assertNotIn(secret, blob)
        self.assertNotIn('reg', self.entries['AppleACPIPlatformExpert']['P'])  # redacted value
        self.assertEqual(self.entries['ANS2']['P']['Device Characteristics'], {'Medium Type': 'Solid State'})

    def test_live_services_and_displays_are_left_to_iokitd(self):
        self.assertEqual(self.entries['Macmini8,1'].get('l'), 'platform')
        self.assertEqual(self.entries['Macmini8,1']['P'], {})
        self.assertEqual(self.entries['IOPMrootDomain'].get('l'), 'power')
        self.assertNotIn('display0', self.entries)
        self.assertNotIn('AppleDisplay', self.entries)

    def test_identity_fills_addresses_and_serials(self):
        self.assertEqual(self.entries['en0']['I'], {'IOMACAddress': ['net.en0.ether', 'mac']})
        self.assertEqual(self.entries['BCM5701Enet']['I'], {'IOMACAddress': ['net.en0.ether', 'mac']})
        self.assertEqual(self.entries['GIGE@0']['I'], {'local-mac-address': ['net.en0.ether', 'mac']})
        self.assertEqual(self.entries['ANS2']['I']['Device Characteristics/Serial Number'],
                         ['hw.disk.serial', 'string'])

    def test_secondary_interfaces_follow_the_guest_interface_list(self):
        derived = {'IOMACAddress': ['net.en0.ether', 'mac~en2']}
        self.assertEqual(self.entries['en2']['I'], derived)
        self.assertEqual(self.entries['TBIP']['I'], derived)
        self.assertNotIn('en6', self.entries)   # the guest has no en6
        self.assertIn('NCM', self.entries)

    def test_emitted_data_round_trips(self):
        output = Path(self.tmp.name) / 'data.inc'
        raw, packed = tool.emit(self.data, output)
        text = output.read_text()
        self.assertIn(f'kStaticRegistrySize = {raw}UL', text)
        body = text[text.index('{') + 1:text.rindex('}')]
        blob = bytes(int(value) for value in body.replace('\n', '').split(',') if value)
        self.assertEqual(len(blob), packed)
        self.assertEqual(plistlib.loads(zlib.decompress(blob)), self.data)

    def test_values(self):
        self.assertEqual(tool.parse_value('<"a","b">'), b'a\0b\0')
        self.assertEqual(tool.parse_value('18446744073709551615'), -1)
        self.assertEqual(tool.parse_value('{"k"=<00ff>,"l"=()}'), {'k': b'\x00\xff', 'l': []})
        with self.assertRaises(tool.Unparsed):
            tool.parse_value('SMCPolledInterface is not serializable')


if __name__ == '__main__':
    unittest.main()
