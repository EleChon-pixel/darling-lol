"""Admin trust settings without ocspd: the Security.framework fallback in security.patch."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PATCH = Path(__file__).resolve().parents[1] / 'patches/security.patch'


def new_side(path):
    """The patched file's text as the patch shows it: context and added lines, in order."""
    section = PATCH.read_text().split('diff --git a/%s ' % path, 1)[1].split('\ndiff --git ', 1)[0]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line[:1] in ('+', ' ') and not line.startswith('+++'))


class TrustSettingsFallbackTests(unittest.TestCase):
    def test_flush_writes_without_authd(self):
        source = new_side('OSX/libsecurity_keychain/lib/TrustSettings.cpp')
        self.assertIn('ocspdTrustSettingsWrite(mDomain, noAuth, cssmXmlData)', source)
        self.assertIn('mDirty = false;', source)

    def test_rpc_failures_fall_back_to_the_file(self):
        source = new_side('OSX/libsecurity_ocspd/client/ocspdClient.cpp')
        self.assertEqual(source.count('return dcTrustSettingsRead(alloc, domain, trustSettings);'), 2)
        self.assertEqual(source.count('return dcTrustSettingsWrite(domain, trustSettings);'), 2)

    @unittest.skipUnless(shutil.which('c++'), 'C++ compiler required')
    def test_admin_file_round_trip(self):
        source = new_side('OSX/libsecurity_ocspd/client/ocspdClient.cpp')
        helpers = source.split('#ifdef DARLING\n', 1)[1].split('\n#endif\n', 1)[0]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Library').mkdir()
            helpers = helpers.replace('"/Library/Security', '"%s/Library/Security' % root)
            program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <errno.h>
typedef int32_t OSStatus;
typedef uint8_t uint8;
typedef uint32_t SecTrustSettingsDomain;
enum { kSecTrustSettingsDomainUser = 0, kSecTrustSettingsDomainAdmin = 1 };
enum { errSecSuccess = 0, errSecIO = -36, errSecParam = -50,
       errSecInternalComponent = -2070, errSecNoTrustSettings = -25263 };
struct CSSM_DATA { size_t Length; uint8 *Data; };
struct Allocator {
    void *malloc(size_t n) { return ::malloc(n); }
    void free(void *p) { ::free(p); }
};
''' + helpers + r'''
#define FILE_PATH DC_ADMIN_TRUST_SETTINGS
int main(void) {
    Allocator alloc;
    CSSM_DATA out = {0, NULL};
    assert(dcTrustSettingsRead(alloc, kSecTrustSettingsDomainAdmin, out) == errSecNoTrustSettings);

    const char plist[] = "<plist><dict/></plist>";
    CSSM_DATA in = {sizeof(plist) - 1, (uint8 *)plist};
    assert(dcTrustSettingsWrite(kSecTrustSettingsDomainAdmin, in) == errSecSuccess);
    struct stat sb;
    assert(stat(FILE_PATH, &sb) == 0 && (sb.st_mode & 0777) == 0644);
    assert(dcTrustSettingsRead(alloc, kSecTrustSettingsDomainAdmin, out) == errSecSuccess);
    assert(out.Length == in.Length && memcmp(out.Data, plist, in.Length) == 0);
    alloc.free(out.Data);

    /* no temporary files are left behind */
    DIR *dir = opendir(DC_TRUST_SETTINGS_DIR);
    int entries = 0;
    for (struct dirent *e; (e = readdir(dir)); )
        entries += e->d_name[0] != '.' || strncmp(e->d_name, ".Admin", 6) == 0;
    closedir(dir);
    assert(entries == 1);

    /* per-user settings do not exist without ocspd */
    assert(dcTrustSettingsWrite(kSecTrustSettingsDomainUser, in) == errSecInternalComponent);
    assert(dcTrustSettingsRead(alloc, kSecTrustSettingsDomainUser, out) == errSecNoTrustSettings);

    /* an empty record deletes the settings, also when there are none */
    CSSM_DATA empty = {0, NULL};
    assert(dcTrustSettingsWrite(kSecTrustSettingsDomainAdmin, empty) == errSecSuccess);
    assert(stat(FILE_PATH, &sb) != 0);
    assert(dcTrustSettingsWrite(kSecTrustSettingsDomainAdmin, empty) == errSecSuccess);
    assert(dcTrustSettingsRead(alloc, kSecTrustSettingsDomainAdmin, out) == errSecNoTrustSettings);
    return 0;
}
'''
            (root / 'check.cpp').write_text(program)
            result = subprocess.run(['c++', '-std=c++17', '-O0', str(root / 'check.cpp'), '-o', str(root / 'check')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root / 'check')], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
