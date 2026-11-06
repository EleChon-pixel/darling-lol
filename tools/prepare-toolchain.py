#!/usr/bin/env python3
"""Expose versioned distro LLVM executables under names the build helpers use."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import llvm_tools

OUTPUT = Path(os.environ.get('RCLOL_TOOLCHAIN_BIN') or ROOT / 'build/toolchain/bin')
TOOLS = ('clang', 'clang++', 'ld.lld', 'llvm-config', 'llvm-objdump', 'llvm-nm')


def main():
    resolved = {name: llvm_tools.require(name) for name in TOOLS}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, source in resolved.items():
        target = OUTPUT / name
        temporary = OUTPUT / ('.%s.%d' % (name, os.getpid()))
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(Path(source).resolve())
        os.replace(temporary, target)
    print('Toolchain shims:', ', '.join('%s=%s' % item for item in resolved.items()))


if __name__ == '__main__':
    main()
