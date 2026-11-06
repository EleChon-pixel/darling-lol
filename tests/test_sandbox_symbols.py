"""Offline contracts for the sandbox symbols the Riot Client's Electron imports.

Electron Framework binds sandbox_extension_{issue_file,consume,release},
sandbox_check, sandbox_free_error and APP_SANDBOX_READ{,_WRITE} through
libSystem (libsystem_sandbox), and sandbox_{compile_string,create_params,
set_param,free_params,free_profile} through libsandbox.1.dylib. A symbol in
the wrong dylib is "Symbol not found" at load and takes the client down.
"""
import re
import unittest

from test_riot_client_142_remaining import added_lines, patch_section

PATCH = 'patches/darling.patch'
SYSTEM = 'src/sandbox/sandbox.c'
HEADER = 'src/sandbox/sandbox.h'
LIBSANDBOX = 'src/libsandbox/src/sandbox.c'


def new_side(section):
    """The post-patch text of every hunk: context plus added lines."""
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line[:1] in (' ', '+') and not line.startswith('+++'))


def defines(source, name):
    return re.search(r'^[\w\s\*]*\b' + name + r'\(', source, re.M) is not None


class SandboxSymbolPlacement(unittest.TestCase):
    def test_extension_family_lives_in_libsystem_sandbox(self):
        system = added_lines(patch_section(PATCH, SYSTEM))
        libsandbox = added_lines(patch_section(PATCH, LIBSANDBOX))
        for name in ('sandbox_extension_issue_file', 'sandbox_extension_issue_mach',
                     'sandbox_extension_consume', 'sandbox_extension_release'):
            self.assertTrue(defines(system, name), name)
            self.assertFalse(defines(libsandbox, name), name)

    def test_extension_family_has_apple_shapes(self):
        # Chromium frees the issued token and treats a consume handle <= 0 as failure.
        header = added_lines(patch_section(PATCH, HEADER))
        self.assertIn('char *sandbox_extension_issue_file(const char *extension_class, '
                      'const char *path, uint32_t flags);', header)
        self.assertIn('int64_t sandbox_extension_consume(const char *extension_token);', header)
        self.assertIn('int sandbox_extension_release(int64_t extension_handle);', header)
        system = added_lines(patch_section(PATCH, SYSTEM))
        self.assertIn('return strdup("darling-sandbox-extension");', system)

    def test_libsandbox_compile_and_params_family(self):
        libsandbox = new_side(patch_section(PATCH, LIBSANDBOX))
        for name in ('sandbox_compile_string', 'sandbox_apply', 'sandbox_free_profile',
                     'sandbox_create_params', 'sandbox_set_param', 'sandbox_free_params'):
            self.assertTrue(defines(libsandbox, name), name)
        # Seatbelt::Compile passes params second and reads ->data/->size.
        self.assertIn('void* sandbox_compile_string(const char *profile, void *params, '
                      'char **errorbuf)', libsandbox)
        self.assertIn('profile->size = strlen(copy);', libsandbox)
        self.assertIn('int sandbox_set_param(void *params, const char *key, const char *value)',
                      libsandbox)
        create = libsandbox.split('void* sandbox_create_params(void)', 1)[1].split('\n}', 1)[0]
        self.assertIn('return calloc(1, 64);', create)


if __name__ == '__main__':
    unittest.main()
