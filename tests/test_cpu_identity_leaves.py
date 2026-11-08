"""CPUID leaf 4/7 emulation, machdep feature strings and proc_listpids in xnu.patch."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

PATCH = Path(__file__).resolve().parents[1] / 'patches/xnu.patch'
SRC = 'darling/src/libsystem_kernel/emulation/src/'


def new_side(path):
    section = PATCH.read_text().split('diff --git a/%s ' % (SRC + path), 1)[1].split('\ndiff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line[:1] in ('+', ' ') and not line.startswith('+++'))


def function(source, name):
    start = source.index('static bool %s(' % name)
    end = source.index('\n}\n', start) + 3
    return source[start:end]


class CpuIdentityLeafTests(unittest.TestCase):
    def test_leaf7_masks_keep_only_skylake_family_client_features(self):
        sigexc = new_side('linux_premigration/signal/sigexc.c')
        masks = {name: int(value, 16) for name, value in
                 re.findall(r'#define CPUID7_(\w+)_KEEP 0x([0-9A-Fa-f]+)u', sigexc)}
        bits = lambda *n: sum(1 << i for i in n)
        self.assertEqual(masks['EBX'], bits(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 18, 19, 20, 23, 25))
        self.assertEqual(masks['ECX'], bits(30))
        self.assertEqual(masks['EDX'], bits(10, 13, 26, 27, 28, 29, 31))
        for absent in (29,):  # SHA
            self.assertFalse(masks['EBX'] & (1 << absent))
        for absent in (3, 5, 8, 9, 10, 27):  # PKU WAITPKG GFNI VAES VPCLMULQDQ MOVDIRI
            self.assertFalse(masks['ECX'] & (1 << absent))
        for absent in (14, 15):  # SERIALIZE, hybrid
            self.assertFalse(masks['EDX'] & (1 << absent))

    @unittest.skipUnless(shutil.which('cc'), 'C compiler required')
    def test_leaf4_entries_match_coffee_lake(self):
        entry = function(new_side('linux_premigration/signal/sigexc.c'), 'cpuid_cache_entry')
        program = r'''
#include <assert.h>
#include <stdbool.h>
struct cpuid_cache { unsigned int eax, ebx, ecx, edx; };
''' + entry + r'''
int main(void) {
    struct cpuid_cache c;
    /* i9-9980HK: 8 cores, 2 threads each, as read on a real Coffee Lake-H. */
    assert(cpuid_cache_entry(&c, 1, 1, 32768, 8, 2, 8, 0));
    assert(c.eax == 0x1C004121 && c.ebx == 0x01C0003F && c.ecx == 63 && c.edx == 0);
    assert(cpuid_cache_entry(&c, 2, 1, 32768, 8, 2, 8, 0));
    assert(c.eax == 0x1C004122 && c.ebx == 0x01C0003F && c.ecx == 63);
    assert(cpuid_cache_entry(&c, 3, 2, 262144, 4, 2, 8, 0));
    assert(c.eax == 0x1C004143 && c.ebx == 0x00C0003F && c.ecx == 1023);
    assert(cpuid_cache_entry(&c, 3, 3, 16777216, 16, 16, 8, 6));
    assert(c.eax == 0x1C03C163 && c.ebx == 0x03C0003F && c.ecx == 16383 && c.edx == 6);
    assert(!cpuid_cache_entry(&c, 1, 1, 0, 8, 2, 8, 0));
    assert(!cpuid_cache_entry(&c, 1, 1, 1000, 8, 2, 8, 0));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'check.c'
            source.write_text(program)
            result = subprocess.run(['cc', '-std=c11', '-O0', str(source), '-o', str(Path(folder) / 'check')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(Path(folder) / 'check')], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_feature_strings_read_leaf_1_and_exist_for_leaf_7(self):
        machdep = new_side('xnu_syscall/bsd/helper/misc/sysctl_machdep.c')
        self.assertIn('cpuid_regs(1, 0, regs);', machdep)
        self.assertNotIn('__cpuid(0,eax,ebx,ecx,edx);', machdep)
        for name in ('"leaf7_features"', '"extfeatures"'):
            self.assertIn(name, machdep)

    def test_hw_and_kern_identity_sysctls(self):
        hw = new_side('xnu_syscall/bsd/helper/misc/sysctl_hw.c')
        for name in ('cachelinesize', 'l1icachesize', 'l1dcachesize', 'l2cachesize', 'l3cachesize', 'tbfrequency'):
            self.assertIn('.name = "%s"' % name, hw)
        self.assertIn('value = 1000000000ULL', hw)
        kern = new_side('xnu_syscall/bsd/helper/misc/sysctl_kern.c')
        self.assertIn('.name = "uuid"', kern)
        self.assertIn('.name = "bootsessionuuid"', kern)

    def test_proc_listpids_is_implemented(self):
        proc_info = new_side('xnu_syscall/bsd/impl/misc/proc_info.c')
        self.assertIn('return _proc_listpids((uint32_t) pid, flavor, (int*) buffer, bufsize);', proc_info)
        self.assertIn('dserver_rpc_get_executable_path(pid', proc_info)


if __name__ == '__main__':
    unittest.main()
