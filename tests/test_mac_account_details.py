"""Interfaces, platform target-type, account records and TMPDIR of the Mac identity."""
from pathlib import Path
import importlib.util
import os
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def new_side(patch, path):
    section = (ROOT / patch).read_text().split('diff --git a/%s ' % path, 1)[1].split('\ndiff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line[:1] in ('+', ' ') and not line.startswith('+++'))


def tool(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MacAccountDetailTests(unittest.TestCase):
    def test_interface_list_has_every_macbook_pro_interface(self):
        net = new_side('patches/xnu.patch',
                       'darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_net.c')
        for name in ('gif0', 'stf0', 'anpi0', 'anpi1', 'en1', 'en2', 'en3', 'en4', 'ap1', 'awdl0',
                     'llw0', 'bridge0', 'utun0'):
            self.assertIn('{ "%s", ' % name, net)
        self.assertIn('emit_phantoms(old, oldlen, &old_ptr, &total_len, &shown', net)

    def test_iokitd_accepts_and_defaults_target_type(self):
        self.assertIn('[key isEqual:@"target-type"]', new_side('patches/iokitd.patch', 'src/PlatformIdentity.h'))
        self.assertIn('@"target-type": dataForString(@"J152f")',
                      new_side('patches/iokitd.patch', 'src/IOPlatformExpertDevice.mm'))

    def test_profiles_carry_board_id_and_target_type(self):
        platform = tool('configure-darling-platform')
        for profile in platform.HARDWARE_PROFILES.values():
            self.assertTrue(profile['board_id'].startswith('Mac-'))
            self.assertTrue(profile['target_type'].startswith('J') or profile['target_type'] == 'Mac')
        # Recorded from a real Macmini8,1 (ioreg): target-type is "Mac", not the board codename.
        self.assertEqual(platform.HARDWARE_PROFILES['macmini8,1']['target_type'], 'Mac')
        self.assertEqual(platform.HARDWARE_PROFILES['macmini8,1']['disk'], ('APPLE SSD AP0512M', 500277792768))
        self.assertEqual(platform.validate({'target-type': 'J152f'}), {'target-type': 'J152f'})

    def test_darling_user_records_become_mac_accounts(self):
        platform = tool('configure-darling-platform')
        with tempfile.TemporaryDirectory() as folder:
            etc = Path(folder) / 'private/etc'
            etc.mkdir(parents=True)
            (etc / 'passwd').write_text('root:*:0:0:System Administrator:/var/root:/bin/sh\n'
                                        'nobody-here:*:1000:1000:Darling User:/Users/nobody-here:/bin/bash\n')
            (etc / 'master.passwd').write_text('root:*:0:0::0:0:System Administrator:/var/root:/bin/sh\n'
                                               'nobody-here:*:1000:1000::0:0:Darling User:/Users/nobody-here:/bin/bash\n')
            files = platform.mac_account_files(Path(folder))
            passwd = files['private/etc/passwd'].decode().splitlines()
            self.assertEqual(passwd[0], 'root:*:0:0:System Administrator:/var/root:/bin/sh')
            self.assertEqual(passwd[1], 'nobody-here:*:1000:1000:nobody-here:/Users/nobody-here:/bin/zsh')
            master = files['private/etc/master.passwd'].decode().splitlines()
            self.assertEqual(master[1], 'nobody-here:*:1000:1000::0:0:nobody-here:/Users/nobody-here:/bin/zsh')
            for relative, data in files.items():
                (Path(folder) / relative).write_bytes(data)
            self.assertEqual(platform.mac_account_files(Path(folder)), {})

    def test_new_prefixes_get_zsh(self):
        darling = new_side('patches/darling.patch', 'src/startup/darling.c')
        self.assertIn(':/Users/%s:/bin/zsh\\n"', darling)
        self.assertNotIn('Darling User:/Users/%s:/bin/bash', darling)

    def test_guest_tmpdir_is_a_var_folders_directory(self):
        guest = tool('exec-guest')
        with tempfile.TemporaryDirectory() as folder:
            environ = {'DPREFIX': folder, 'USER': 'someone', 'TMPDIR': '/tmp'}
            guest.filter_host_environment(environ)
            parts = environ['TMPDIR'].split('/')
            self.assertEqual(parts[:3], ['', 'var', 'folders'])
            self.assertEqual((len(parts[3]), len(parts[4]), parts[5], parts[6]), (2, 28, 'T', ''))
            self.assertTrue(parts[4].endswith('0000gn'))
            self.assertTrue(os.path.isdir(folder + environ['TMPDIR']))
            again = {'DPREFIX': folder, 'USER': 'someone'}
            guest.filter_host_environment(again)
            self.assertEqual(again['TMPDIR'], environ['TMPDIR'])
            kept = {'DPREFIX': folder, 'TMPDIR': '/x', 'RCLOL_KEEP_HOST_ENV': 'TMPDIR'}
            guest.filter_host_environment(kept)
            self.assertEqual(kept['TMPDIR'], '/x')


if __name__ == '__main__':
    unittest.main()
