"""The com.apple.netsrc kernel control: connectable by any process, answering in XNU's layout."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EMULATION = 'darling/src/libsystem_kernel/emulation/'


def new_side(path):
    section = (ROOT / 'patches/xnu.patch').read_text().split('diff --git a/%s ' % path, 1)[1].split('\ndiff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line[:1] in ('+', ' ') and not line.startswith('+++'))


class NetsrcTests(unittest.TestCase):
    def test_netsrc_connects_and_other_controls_refuse(self):
        connect = new_side(EMULATION + 'src/xnu_syscall/bsd/impl/network/connect.c')
        self.assertIn('== DARLING_NETSRC_CTL_ID)\n\t\t\treturn darling_netsrc_connect(fd);\n\t\treturn -EPERM;', connect)
        # The id the CTLIOCGINFO table gives com.apple.netsrc (sixth entry).
        ioctl = new_side(EMULATION + 'src/xnu_syscall/bsd/impl/ioctl/ioctl.c')
        names = [line.strip().strip('",') for line in ioctl.split('kernel_controls[][40] = {', 1)[1].split('};', 1)[0].splitlines()
                 if line.strip()]
        self.assertEqual(names.index('com.apple.netsrc') + 1, 6)
        self.assertIn('#define DARLING_NETSRC_CTL_ID 6', new_side(EMULATION + 'include/xnu_syscall/bsd/impl/network/netsrc.h'))

    def test_requests_are_answered_in_xnu_layout(self):
        netsrc = new_side(EMULATION + 'src/xnu_syscall/bsd/impl/network/netsrc.c')
        for define in ('#define NETSRC_REQ_SIZE 36', '#define NETSRC_REPV1_SIZE 40', '#define NETSRC_REPV2_SIZE 56',
                       '#define NETSRC_FLAG_ROUTEABLE 0x20'):
            self.assertIn(define, netsrc)
        # XNU's default address-selection policy, loopback and IPv4-mapped rows.
        self.assertIn('128, 50, 0 },', netsrc)
        self.assertIn('96, 35, 4 },', netsrc)
        sendto = new_side(EMULATION + 'src/xnu_syscall/bsd/impl/network/sendto.c')
        self.assertIn('darling_netsrc_socket(fd))\n\t\treturn darling_netsrc_send(fd, buffer, length);', sendto)
        self.assertIn('src/xnu_syscall/bsd/impl/network/netsrc.c', new_side(EMULATION + 'CMakeLists.txt'))


if __name__ == '__main__':
    unittest.main()
