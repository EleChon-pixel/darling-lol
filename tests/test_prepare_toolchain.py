"""Local unversioned shims for distros that install only versioned LLVM tools."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/prepare-toolchain.py'


class ToolchainShimFixture(unittest.TestCase):
    def test_versioned_tools_get_local_unversioned_names(self):
        with tempfile.TemporaryDirectory(prefix='toolchain shim ') as folder:
            folder = Path(folder)
            binaries = folder / 'versioned'
            output = folder / 'shims'
            binaries.mkdir()
            for name in ('clang', 'clang++', 'ld.lld', 'llvm-config', 'llvm-objdump', 'llvm-nm'):
                path = binaries / (name + '-23')
                path.write_text('#!/bin/sh\nexit 0\n')
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(binaries), RCLOL_TOOLCHAIN_BIN=str(output))
            result = subprocess.run([sys.executable, str(SCRIPT)], env=env, text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ('clang', 'clang++', 'ld.lld', 'llvm-config', 'llvm-objdump', 'llvm-nm'):
                self.assertTrue((output / name).is_symlink(), name)
                self.assertEqual((output / name).resolve(), binaries / (name + '-23'))


if __name__ == '__main__':
    unittest.main()
