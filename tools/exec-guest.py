#!/usr/bin/env python3
"""Run a command without the host file descriptors this launcher inherited (anything above stderr).

It also starts the guest from an allowlisted environment: only what Darling and the host
libraries it loads into guest processes need (display, audio, GPU driver and loader
variables) plus the variables a Mac session has. Everything else the desktop session,
shell, terminal or service manager exported stays on the host. RCLOL_FILTER_HOST_ENV=0
passes the host environment through unchanged; RCLOL_KEEP_HOST_ENV lists names to keep
anyway, separated by spaces or commas.
"""
import hashlib
import os
import sys

# Variables a Mac login session also has (SHELL and PATH are replaced below), and the
# Darling loader's own.
GUEST_NAMES = {
    'HOME', 'USER', 'LOGNAME', 'LANG', 'TZ', 'TMPDIR', 'SHELL', 'PATH',
    'DPREFIX', 'MAC_CHROMIUM_TMPDIR',
}
# Read on the host side of guest processes: X11, D-Bus, audio servers, the Vulkan/EGL/GL
# loaders and drivers (they search XDG_DATA_DIRS/XDG_CONFIG_DIRS), glibc and fontconfig in
# the Nix FHS environment, and gamemode's LD_PRELOAD.
HOST_LIBRARY_NAMES = {
    'DISPLAY', 'XAUTHORITY', 'XMODIFIERS', 'XDG_RUNTIME_DIR', 'XDG_DATA_DIRS',
    'XDG_CONFIG_DIRS', 'XDG_CONFIG_HOME', 'DBUS_SESSION_BUS_ADDRESS', 'LD_LIBRARY_PATH',
    'LD_PRELOAD', 'LOCALE_ARCHIVE', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH', 'EGL_PLATFORM',
    'DRI_PRIME', 'mesa_glthread',
}
HOST_LIBRARY_PREFIXES = (
    'LC_', 'MESA_', '__GL_', '__GLX_', '__NV_', '__VK_', 'VK_', '__EGL_', 'LIBGL_', 'PULSE_',
    'PIPEWIRE_', 'ALSA_', 'XCURSOR_', 'RADV_', 'ANV_', 'NV_',
    # Darling runtime and darling-lol knobs that guest-side frameworks read.
    'DARLING_', 'RCLOL_', 'DYLD_',
)
GUEST_SHELL = '/bin/zsh'
GUEST_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
BASE36 = '0123456789abcdefghijklmnopqrstuvwxyz'


def mac_temp_dir(environ):
    """The per-user temporary directory a Mac session has, /var/folders/xx/<id>/T/.

    The name is stable per prefix and user (as dirhelper's is per account). The
    directory (and its C/ sibling) is created in the prefix; None without a prefix.
    """
    prefix = environ.get('DPREFIX')
    if not prefix:
        return None
    digest = hashlib.sha256(('%s\0%s' % (os.path.realpath(prefix), environ.get('USER', ''))).encode()).digest()
    number = int.from_bytes(digest, 'big')
    letters = []
    for _ in range(24):
        number, digit = divmod(number, 36)
        letters.append(BASE36[digit])
    bucket, account = ''.join(letters[:2]), ''.join(letters[2:]) + '0000gn'
    guest = '/var/folders/%s/%s/' % (bucket, account)
    try:
        for leaf in ('T', 'C'):
            os.makedirs(os.path.join(prefix, 'var/folders', bucket, account, leaf), mode=0o700, exist_ok=True)
    except OSError:
        return None
    return guest + 'T/'


def allowed_variable(name):
    return name in GUEST_NAMES or name in HOST_LIBRARY_NAMES or name.startswith(HOST_LIBRARY_PREFIXES)


def filter_host_environment(environ):
    """Return the names removed from environ (a mutable mapping), honoring RCLOL_KEEP_HOST_ENV."""
    keep = set(environ.get('RCLOL_KEEP_HOST_ENV', '').replace(',', ' ').split())
    environ.pop('RCLOL_KEEP_HOST_ENV', None)
    environ.pop('RCLOL_FILTER_HOST_ENV', None)
    removed = sorted(name for name in environ if not allowed_variable(name) and name not in keep)
    for name in removed:
        del environ[name]
    # The host login shell (for example /bin/fish) does not exist in the guest.
    if 'SHELL' not in keep:
        environ['SHELL'] = GUEST_SHELL
    # A host PATH names Linux directories; the guest always has the Mac layout.
    if 'PATH' not in keep:
        environ['PATH'] = GUEST_PATH
    # A Mac session's TMPDIR is its per-user /var/folders directory, not /tmp.
    if 'TMPDIR' not in keep:
        temporary = mac_temp_dir(environ)
        if temporary:
            environ['TMPDIR'] = temporary
    return removed


def close_inherited_fds():
    """A terminal, IDE or service manager can leak descriptors; the guest must not inherit them."""
    try:
        names = os.listdir('/proc/self/fd')
    except OSError:
        os.closerange(3, 65536)
        return
    for name in names:
        if name.isdigit() and int(name) > 2:
            try:
                os.close(int(name))
            except OSError:
                pass  # the descriptor listdir used is already closed


def main(argv):
    if len(argv) < 2:
        sys.exit('usage: exec-guest.py COMMAND [ARGUMENT]...')
    if os.environ.get('RCLOL_FILTER_HOST_ENV', '1') != '0':
        filter_host_environment(os.environ)
    else:
        os.environ.pop('RCLOL_FILTER_HOST_ENV', None)
    close_inherited_fds()
    os.execvp(argv[1], argv[1:])


if __name__ == '__main__':
    main(sys.argv)
