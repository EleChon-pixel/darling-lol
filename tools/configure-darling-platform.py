#!/usr/bin/env python3
"""Preview or explicitly save per-prefix IOKit platform overrides; defaults stay unchanged."""
import argparse
import json
import fcntl
import secrets
from contextlib import nullcontext
import os
from pathlib import Path
import plistlib
import pwd
import shlex
import tempfile
import uuid
import hashlib
from xml.parsers.expat import ExpatError

MAX_SIZE = 65536
BASE34 = '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ'
KNOWN_SERIAL = 'C02ZL0GVMD6N'
# Apple, Inc. OUIs (IEEE registry) for a generated ROM, which is also en0's address:
# a Mac's built-in network interface carries Apple's OUI.
APPLE_OUIS = ('3C22FB', 'F01898', 'A483E7', 'F8FFC2', 'ACBC32', '8C8590', '88665A', '147DDA')
KNOWN_UUID = '6F3B2A1E-8C4D-4E5F-9A7B-1D2C3E4F5A6B'
# Each profile is one real Mac configuration. Every value a guest can query
# (sysctl, IOKit, Metal, hostname) comes from the same profile so they agree.
# CPU fields are the published CPUID leaf-1 signature and XNU's constants for
# that microarchitecture (CPUFAMILY_INTEL_KABYLAKE covers Coffee/Comet Lake).
HARDWARE_PROFILES = {
    'macbookpro16,1': {
        'model': 'MacBookPro16,1',
        'manufacturer': 'Apple Inc.',
        'cpu_vendor': 'GenuineIntel',
        'cpu_brand': 'Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz',
        'cpu_signature': 0x906ED,      # family 6, model 158 (0x9E), stepping 13
        'cpu_family_id': 0x0F817246,
        'cpu_frequency': 2400000000,
        'threads_per_core': 2,
        # L1I, L1D, L2 (per core), L3 (shared) in bytes; CPUID leaf 4 and hw.l*cachesize.
        'caches': (32768, 32768, 262144, 16777216),
        'cpuid_max_leaf': 0x16,
        # IOPlatformExpertDevice board-id and target-type (the T2 board configuration).
        'board_id': 'Mac-E1008331FDC96864',
        'target_type': 'J152f',
        'hostname': 'MacBook-Pro.local',
        'gpu_integrated': ('Intel UHD Graphics 630', 0x8086, 0x3E9B),
        'gpu_discrete': ('AMD Radeon Pro 5500M', 0x1002, 0x7340),
        # 12-character serial layout: plant, year/half, week, unit, configuration.
        # The 2019 16-inch MacBook Pro shipped late 2019 ('Z') through 2020 ('C', 'D')
        # from the C02 plant with MD6x configuration codes.
        'serial_plants': ('C02',),
        'serial_halves': ('Z', 'C', 'D'),
        'serial_configs': ('MD6M', 'MD6N', 'MD6R', 'MD6T', 'MD6V', 'MD6W'),
    },
    'imac20,1': {
        'model': 'iMac20,1',
        'manufacturer': 'Apple Inc.',
        'cpu_vendor': 'GenuineIntel',
        'cpu_brand': 'Intel(R) Core(TM) i5-10500 CPU @ 3.10GHz',
        'cpu_signature': 0xA0653,      # family 6, model 165 (0xA5), stepping 3
        'cpu_family_id': 0x0F817246,
        'cpu_frequency': 3100000000,
        'threads_per_core': 2,
        'caches': (32768, 32768, 262144, 12582912),
        'cpuid_max_leaf': 0x16,
        'board_id': 'Mac-CFF7D910A743CAAF',
        'target_type': 'J185',
        'hostname': 'iMac.local',
        'gpu_integrated': ('Intel UHD Graphics 630', 0x8086, 0x9BC8),
        'gpu_discrete': ('AMD Radeon Pro 5300', 0x1002, 0x7340),
    },
    'macmini8,1': {
        'model': 'Macmini8,1',
        'manufacturer': 'Apple Inc.',
        'cpu_vendor': 'GenuineIntel',
        # Same Coffee Lake microarchitecture as the MacBookPro16,1's i9, so the family
        # id, leaf-7 feature mask and cache-leaf encoding carry over unchanged; only the
        # stepping (D->A), brand, frequency and L3 size differ. i7-8700B is the mini's
        # BGA part (note the B suffix), 6C/12T, 12 MB L3.
        'cpu_brand': 'Intel(R) Core(TM) i7-8700B CPU @ 3.20GHz',
        'cpu_signature': 0x906EA,      # family 6, model 158 (0x9E), stepping 10
        'cpu_family_id': 0x0F817246,
        'cpu_frequency': 3200000000,
        'threads_per_core': 2,
        'caches': (32768, 32768, 262144, 12582912),  # L3 12 MB (6-core part)
        'cpuid_max_leaf': 0x16,
        # board-id verified against AppleDB and Geekbench Macmini8,1 uploads (the
        # OpenCore docs' Mac-7BA5B2D9E42DDD94 is only a sample value, not this model).
        'board_id': 'Mac-7BA5B2DFE22DDD8C',
        'target_type': 'J174',         # 2018 Mac mini internal codename
        'hostname': 'Mac-mini.local',
        'en0_wired': True,             # a mini's en0 is built-in Ethernet, en1 is Wi-Fi
        'logical_cpus': 12,            # i7-8700B is 6C/12T; report that, not the host count
        'cpu_frequency_max': 4600000000,  # 4.6 GHz turbo, CPUID leaf 0x16 EBX
        # A Mac mini has only the integrated GPU; no discrete.
        'gpu_integrated': ('Intel UHD Graphics 630', 0x8086, 0x3E9B),
        # Serial format and the 25 model-config codes are from Acidanthera macserial's
        # Macmini8,1 table (ApplePlatformData example "C07XL9WEJYVX": plant C07, year X).
        'serial_plants': ('C07',),
        'serial_halves': ('X',),
        'serial_configs': ('JYVX', 'JYVW', 'JYVY', 'JYW0', 'L960', 'MCD6', 'M7FV', 'M7FT',
                           'M99Q', 'M99P', 'MJHL', 'MHGQ', 'LVVM', 'LVVN', 'MKTR', 'LVVL',
                           'LVVJ', 'LVVK', 'LHPC', 'M99N', 'L95X', 'L95Y', 'N6VR', 'PJH7', 'PJH8'),
    },
}
OS_PROFILES = {
    # Released Intel-compatible Apple version/build pairs.  The build is part
    # of the key so a product version can never silently drift to another
    # point release.
    'sonoma-14.7-23H124': {
        'ProductName': 'macOS',
        'ProductVersion': '14.7',
        'ProductUserVisibleVersion': '14.7',
        'ProductBuildVersion': '23H124',
        'FullVersionString': 'Version 14.7 (Build 23H124)',
    },
    'sonoma-14.6.1-23G93': {
        'ProductName': 'macOS',
        'ProductVersion': '14.6.1',
        'ProductUserVisibleVersion': '14.6.1',
        'ProductBuildVersion': '23G93',
        'FullVersionString': 'Version 14.6.1 (Build 23G93)',
    },
    'ventura-13.7-22H123': {
        'ProductName': 'macOS',
        'ProductVersion': '13.7',
        'ProductUserVisibleVersion': '13.7',
        'ProductBuildVersion': '22H123',
        'FullVersionString': 'Version 13.7 (Build 22H123)',
    },
}
RUNTIME_KEYS = ('hw.model', 'machdep.cpu.vendor', 'machdep.cpu.brand_string',
                'kern.osproductversion', 'kern.osversion')
# Written by current provisioning; older files without them stay valid and the
# runtime falls back to host-derived values for anything missing.
OPTIONAL_RUNTIME_KEYS = ('machdep.cpu.signature', 'hw.cpufamily', 'hw.cpufrequency',
                         'cpu.threads_per_core', 'kern.hostname',
                         'gpu.integrated.name', 'gpu.integrated.vendor', 'gpu.integrated.device',
                         'gpu.discrete.name', 'gpu.discrete.vendor', 'gpu.discrete.device',
                         'home.isolated', 'host.hide', 'cpu.emulate_cpuid',
                         'hw.l1icachesize', 'hw.l1dcachesize', 'hw.l2cachesize', 'hw.l3cachesize',
                         'cpu.cpuid_max_leaf', 'kern.uuid', 'net.en0.ether',
                         'hw.disk.serial', 'hw.disk.model', 'hw.disk.size',
                         'net.en0.wired', 'net.en1.ether', 'cpu.logical_count',
                         'hw.cpufrequency_max')
ALL_RUNTIME_KEYS = RUNTIME_KEYS + OPTIONAL_RUNTIME_KEYS
STRINGS = {'IOPlatformSerialNumber': 64, 'manufacturer': 128, 'model': 128,
           'product-name': 128, 'board-id': 128, 'mlb-serial-number': 64, 'target-type': 32}
BYTES = {'ROM': 6, 'system-id': 16}
ALIASES = {
    'SystemProductName': 'model', 'Type': 'model', 'SMBIOS_MODEL': 'model',
    'SMBIOS_PRODUCT_NAME': 'product-name', 'SMBIOS_MANUFACTURER': 'manufacturer',
    'SMBIOS_BOARD_ID': 'board-id', 'SMBIOS_TARGET_TYPE': 'target-type',
    'SystemSerialNumber': 'IOPlatformSerialNumber',
    'Serial': 'IOPlatformSerialNumber', 'SMBIOS_SERIAL_NUMBER': 'IOPlatformSerialNumber',
    'SystemUUID': 'IOPlatformUUID', 'SmUUID': 'IOPlatformUUID', 'SMBIOS_PLATFORM_UUID': 'IOPlatformUUID',
    'MLB': 'mlb-serial-number', 'Board Serial': 'mlb-serial-number', 'SMBIOS_MLB': 'mlb-serial-number',
    'SMBIOS_ROM': 'ROM', 'SMBIOS_SYSTEM_ID': 'system-id',
    'SMBIOS_PROVISIONING_UDID': 'provisioning_UDID',
}


def validate(properties):
    if not isinstance(properties, dict) or len(properties) > 12:
        raise ValueError('properties must be a dictionary of supported identity fields')
    result = {}
    for key, value in properties.items():
        if key in STRINGS:
            if not isinstance(value, str) or not 1 <= len(value) <= STRINGS[key] or any(not 32 <= ord(c) <= 126 for c in value):
                raise ValueError('Invalid printable string for ' + key)
        elif key in ('IOPlatformUUID', 'provisioning_UDID'):
            if not isinstance(value, str):
                raise ValueError(key + ' must be a UUID string')
            parsed = uuid.UUID(value)
            if not parsed.int:
                raise ValueError(key + ' must not be zero')
            value = str(parsed).upper()
        elif key in BYTES:
            if isinstance(value, str):
                value = bytes.fromhex(value.replace(':', '').replace('-', ''))
            if not isinstance(value, bytes) or len(value) != BYTES[key]:
                raise ValueError(key + ' has an invalid byte length')
        else:
            raise ValueError('Unsupported identity field: ' + str(key))
        result[key] = value
    if 'model' in result:
        result.setdefault('product-name', result['model'])
    if 'IOPlatformUUID' in result:
        system_id = uuid.UUID(result['IOPlatformUUID']).bytes_le
        if 'system-id' in result and result['system-id'] != system_id:
            raise ValueError('system-id does not match IOPlatformUUID')
        result['system-id'] = system_id
        if result.get('provisioning_UDID', result['IOPlatformUUID']) != result['IOPlatformUUID']:
            raise ValueError('provisioning_UDID must match IOPlatformUUID')
    return result


def load(source):
    with Path(source).open("rb") as stream:
        raw = stream.read(MAX_SIZE + 1)
    if len(raw) > MAX_SIZE:
        raise ValueError('Identity input exceeds 64 KiB')
    if str(source).endswith('.conf'):
        payload = {}
        for line in raw.decode().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep:
                raise ValueError('Malformed legacy identity line')
            values = shlex.split(value, comments=True)
            if len(values) != 1 or key.strip() in payload:
                raise ValueError('Malformed or duplicate legacy identity field')
            payload[key.strip()] = values[0]
    else:
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError('Duplicate JSON identity field: ' + key)
                result[key] = value
            return result
        if raw.lstrip()[:1] in (b'{', b'['):
            payload = json.loads(raw, object_pairs_hook=unique_keys)
        else:
            payload = plistlib.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError('Identity input must be a dictionary')
    if 'schema' in payload:
        if set(payload) != {'schema', 'properties'} or type(payload['schema']) is not int or payload['schema'] != 1:
            raise ValueError('Unsupported platform identity schema')
        return validate(payload['properties'])
    if 'PlatformInfo' in payload:
        payload = payload['PlatformInfo'].get('Generic') if isinstance(payload['PlatformInfo'], dict) else None
    elif 'Generic' in payload:
        payload = payload['Generic']
    if not isinstance(payload, dict):
        raise ValueError('Missing OpenCore PlatformInfo/Generic dictionary')
    result = {}
    for key, value in payload.items():
        name = ALIASES.get(key, key)
        if name not in {*STRINGS, *BYTES, 'IOPlatformUUID', 'provisioning_UDID'}:
            continue # OpenCore includes unrelated boot, firmware and CPU settings.
        if name in result and result[name] != value:
            raise ValueError('Conflicting imports for ' + name)
        result[name] = value
    if not result:
        raise ValueError('No supported identity fields found')
    return validate(result)


def checked_path(prefix, relative):
    prefix = Path(prefix).expanduser()
    if not prefix.is_absolute():
        raise ValueError('Prefix must be absolute')
    path = prefix / relative
    if path.is_symlink() or not path.resolve().is_relative_to(prefix.resolve()):
        raise ValueError('Identity destination must remain inside the selected prefix')
    return path


def validate_runtime_string(name, value, limit=128):
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise ValueError(name + ' must be a non-empty string of at most %d characters' % limit)
    if any(not 32 <= ord(c) <= 126 or c in '=\r\n' for c in value):
        raise ValueError(name + ' must contain printable ASCII without equals or newlines')
    return value


def runtime_identity(properties, metadata, hardware_profile=None, cpu_brand_string=None,
                     host_home_links=False, show_host=False, host_cpuid=False):
    selected = HARDWARE_PROFILES.get(hardware_profile) if hardware_profile else None
    if selected is None:
        selected = next((profile for profile in HARDWARE_PROFILES.values()
                         if profile['model'] == properties.get('model')), HARDWARE_PROFILES['macbookpro16,1'])
    values = {
        'hw.model': properties.get('model', selected['model']),
        'machdep.cpu.vendor': selected['cpu_vendor'],
        'machdep.cpu.brand_string': cpu_brand_string or selected['cpu_brand'],
        'kern.osproductversion': metadata['ProductVersion'],
        'kern.osversion': metadata['ProductBuildVersion'],
        'machdep.cpu.signature': '0x%X' % selected['cpu_signature'],
        'hw.cpufamily': '0x%08X' % selected['cpu_family_id'],
        'hw.cpufrequency': str(selected['cpu_frequency']),
        'cpu.threads_per_core': str(selected['threads_per_core']),
        'kern.hostname': selected['hostname'],
        # kern.uuid is the kernel's LC_UUID, shared by every Mac on one build; derived
        # from the build so it stays fixed for an OS profile.
        'kern.uuid': str(uuid.uuid5(uuid.NAMESPACE_URL,
                                    'darling-lol:xnu:' + metadata['ProductBuildVersion'])).upper(),
    }
    if 'caches' in selected:
        for key, size in zip(('hw.l1icachesize', 'hw.l1dcachesize', 'hw.l2cachesize', 'hw.l3cachesize'),
                             selected['caches']):
            values[key] = str(size)
        values['cpu.cpuid_max_leaf'] = '0x%X' % selected['cpuid_max_leaf']
    for slot in ('integrated', 'discrete'):
        gpu = selected.get('gpu_' + slot)
        if not gpu:
            continue  # e.g. a Mac mini has no discrete GPU
        name, vendor, device = gpu
        values['gpu.%s.name' % slot] = name
        values['gpu.%s.vendor' % slot] = '0x%04X' % vendor
        values['gpu.%s.device' % slot] = '0x%04X' % device
    # darlingserver links the host home and XDG folders into /Users/<name> unless the
    # home is isolated; a Mac has no LinuxHome and no folders pointing at a host root.
    values['home.isolated'] = '0' if host_home_links else '1'
    # Applications see no /proc, /Volumes/SystemRoot, Linux mounts, Linux interface names
    # or host-library environment variables (libsystem_kernel guest_view.c, mldr).
    values['host.hide'] = '0' if show_host else '1'
    # CPUID instructions report the profile's CPU (libsystem_kernel sigexc.c).
    values['cpu.emulate_cpuid'] = '0' if host_cpuid else '1'
    # en0 reports the machine's ROM as its address, as on a Mac, instead of the host
    # adapter's (libsystem_kernel sysctl_net.c; needs host.hide).
    rom = properties.get('ROM')
    if isinstance(rom, (bytes, bytearray)) and len(rom) == 6 and not rom[0] & 1:
        values['net.en0.ether'] = ':'.join('%02x' % byte for byte in rom)
    # The internal SSD's serial and model, for the IONVMeController IOKit reads for a
    # hardware ID. The serial is derived from the platform UUID so it is stable per
    # prefix without storing another identifier; the model and size are an Apple SSD's.
    platform_uuid = properties.get('IOPlatformUUID')
    if platform_uuid:
        digest = hashlib.sha256(('darling-lol:disk:' + platform_uuid).encode()).digest()
        serial = ''.join(BASE34[byte % len(BASE34)] for byte in digest[:12])
        values['hw.disk.serial'] = serial
        values['hw.disk.model'] = 'APPLE SSD AP0512Q'
        values['hw.disk.size'] = '500277790720'
    # A desktop Mac's en0 is built-in Ethernet (not Wi-Fi); it also has a separate
    # Wi-Fi interface (en1) with its own Apple-OUI address, derived from the platform
    # UUID so it is stable and distinct from en0's ROM address.
    if selected.get('logical_cpus'):
        values['cpu.logical_count'] = str(selected['logical_cpus'])
    if selected.get('cpu_frequency_max'):
        values['hw.cpufrequency_max'] = str(selected['cpu_frequency_max'])
    if selected.get('en0_wired'):
        values['net.en0.wired'] = '1'
        if platform_uuid:
            d = hashlib.sha256(('darling-lol:en1:' + platform_uuid).encode()).digest()
            oui = bytes.fromhex(APPLE_OUIS[d[0] % len(APPLE_OUIS)])
            values['net.en1.ether'] = ':'.join('%02x' % b for b in (oui + d[1:4]))
    for key in values:
        validate_runtime_string(key, values[key])
    return values


def encode_runtime_identity(values):
    if not set(RUNTIME_KEYS) <= set(values) <= set(ALL_RUNTIME_KEYS):
        raise ValueError('Runtime identity requires the core keys and only supported optional keys')
    lines = ['# Per-prefix runtime identity; generated by configure-darling-platform.py.']
    lines.extend(key + '=' + validate_runtime_string(key, values[key])
                 for key in ALL_RUNTIME_KEYS if key in values)
    return ('\n'.join(lines) + '\n').encode()


def load_runtime_identity_bytes(raw):
    if len(raw) > MAX_SIZE:
        raise ValueError('Runtime identity exceeds 64 KiB')
    result = {}
    for line in raw.decode('ascii').splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or key in result or key not in ALL_RUNTIME_KEYS:
            raise ValueError('Malformed, duplicate, or unsupported runtime identity field')
        result[key] = validate_runtime_string(key, value)
    if not set(RUNTIME_KEYS) <= set(result):
        raise ValueError('Runtime identity is incomplete')
    return result


def load_runtime_identity(path):
    return load_runtime_identity_bytes(Path(path).read_bytes())


def destination(prefix):
    return checked_path(prefix, 'private/etc/darling-platform.plist')


def ensure_stopped(prefix):
    marker = Path(prefix) / '.init.pid'
    if marker.exists():
        text = marker.read_text().strip()
        if not text.isdecimal() or int(text) <= 1:
            raise ValueError('Invalid .init.pid; verify the selected prefix is stopped before writing')
        try:
            os.kill(int(text), 0)
        except ProcessLookupError:
            return
        raise ValueError('Shut down the selected Darling prefix before writing platform identity')


def atomic_write(path, data):
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + '.before-platform-change')
        if not backup.exists():
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(path.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
    fd, temporary = tempfile.mkstemp(prefix='.darling-platform-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def save(prefix, properties):
    path = destination(prefix)
    ensure_stopped(prefix)
    encoded = plistlib.dumps({'schema': 1, 'properties': validate(properties)}, sort_keys=True)
    checked_path(prefix, 'private/etc/darling-platform.plist.before-platform-change')
    if path.exists():
        load(path)  # refuse to silently overwrite an unknown schema
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write(destination(prefix), encoded)


def has_known_defaults(properties):
    """True when an identity still carries the shared serial, UUID, or a field derived from that UUID."""
    return (properties.get('IOPlatformSerialNumber') == KNOWN_SERIAL
            or str(properties.get('IOPlatformUUID', '')).upper() == KNOWN_UUID
            or str(properties.get('provisioning_UDID', '')).upper() == KNOWN_UUID
            or properties.get('system-id') == uuid.UUID(KNOWN_UUID).bytes_le)


SERIAL_WEEKS = '123456789CDFGHJKLMNPQRTVWXY'  # Apple's week-of-half alphabet


def profile_serial(profile):
    """A serial with the layout real units of this model carry, or None if unknown."""
    if not profile or 'serial_configs' not in profile:
        return None
    return (secrets.choice(profile['serial_plants']) + secrets.choice(profile['serial_halves']) +
            secrets.choice(SERIAL_WEEKS) + ''.join(secrets.choice(BASE34) for _ in range(3)) +
            secrets.choice(profile['serial_configs']))


def provision(properties, rom_oui=None, hardware_profile=None, new_serial=False):
    """Fill missing identifiers, replacing only the two known shared defaults."""
    result = validate(properties)
    if new_serial:
        result.pop('IOPlatformSerialNumber', None)
    if result.get('IOPlatformSerialNumber') == KNOWN_SERIAL:
        result.pop('IOPlatformSerialNumber')
    if (result.get('IOPlatformUUID', '').upper() == KNOWN_UUID
            or result.get('provisioning_UDID', '').upper() == KNOWN_UUID
            or result.get('system-id') == uuid.UUID(KNOWN_UUID).bytes_le):
        result.pop('IOPlatformUUID', None)
        result.pop('system-id', None)
        result.pop('provisioning_UDID', None)
    if 'IOPlatformSerialNumber' not in result:
        serial = profile_serial(HARDWARE_PROFILES.get(hardware_profile))
        if serial:
            result['IOPlatformSerialNumber'] = serial
    for key, length in [('IOPlatformSerialNumber', 12), ('mlb-serial-number', 17)]:
        if key not in result:
            result[key] = ''.join(secrets.choice(BASE34) for _ in range(length))
    if 'IOPlatformUUID' not in result:
        # Preserve a custom standalone EFI system ID during legacy migration.
        result['IOPlatformUUID'] = (result['provisioning_UDID'] if 'provisioning_UDID' in result else
            str(uuid.UUID(bytes_le=result['system-id']) if 'system-id' in result else uuid.uuid4()).upper())
    result.setdefault('provisioning_UDID', result['IOPlatformUUID'])
    # Earlier provisioning generated a locally administered ROM, which no Mac has.
    if 'ROM' in result and result['ROM'][0] & 2 and rom_oui is None:
        result.pop('ROM')
    if 'ROM' not in result:
        oui = rom_oui if rom_oui is not None else bytes.fromhex(secrets.choice(APPLE_OUIS))
        result['ROM'] = oui + secrets.token_bytes(3)
    return validate(result)


def provisioning_files(prefix, properties, runtime_root, hardware_profile=None,
                       os_profile=None, cpu_brand_string=None, host_home_links=False,
                       show_host=False, host_cpuid=False):
    """Preflight every file before making any identity changes."""
    version = Path(runtime_root) / 'System/Library/CoreServices/SystemVersion.plist'
    if os_profile:
        metadata = dict(OS_PROFILES[os_profile])
        raw = plistlib.dumps(metadata, sort_keys=True)
    else:
        with version.open('rb') as stream:
            raw = stream.read(MAX_SIZE + 1)
        if len(raw) > MAX_SIZE:
            raise ValueError('Runtime SystemVersion.plist exceeds 64 KiB')
        metadata = plistlib.loads(raw)
    if not isinstance(metadata, dict) or any(not isinstance(metadata.get(key), str) or not metadata[key]
            for key in ('ProductName', 'ProductVersion', 'ProductBuildVersion')):
        raise ValueError('Runtime SystemVersion.plist is missing version metadata')
    reverse = {value: key for key, value in ALIASES.items() if key.startswith('SMBIOS_')}
    lines = ['# Synthetic per-prefix identity; generated by configure-darling-platform.py.']
    for key, value in sorted(properties.items()):
        value = value.hex().upper() if isinstance(value, bytes) else value
        lines.append(reverse[key] + '=' + shlex.quote(value))
    files = {
        'private/etc/darling-smbios.conf': ('\n'.join(lines) + '\n').encode(),
        'private/etc/darling-runtime-identity.conf': encode_runtime_identity(
            runtime_identity(properties, metadata, hardware_profile, cpu_brand_string,
                             host_home_links, show_host, host_cpuid)),
        'System/Library/CoreServices/SystemVersion.plist': raw,
        'private/etc/darling-platform.plist': plistlib.dumps({'schema': 1, 'properties': properties}, sort_keys=True),
    }
    for relative in files:
        path = checked_path(prefix, relative)
        checked_path(prefix, relative + '.before-platform-change')
        if path.exists():
            if relative.endswith('darling-platform.plist'):
                load(path)
            elif relative.endswith('.conf'):
                if relative.endswith('runtime-identity.conf'):
                    load_runtime_identity(path)
                else:
                    load(path)
            else:
                if not isinstance(plistlib.loads(path.read_bytes()), dict):
                    raise ValueError('Existing SystemVersion.plist is invalid')
    return files


def save_provisioning(prefix, properties, runtime_root, hardware_profile=None,
                      os_profile=None, cpu_brand_string=None, host_home_links=False,
                      show_host=False, host_cpuid=False):
    ensure_stopped(prefix)
    files = provisioning_files(prefix, properties, runtime_root, hardware_profile,
                               os_profile, cpu_brand_string, host_home_links, show_host, host_cpuid)
    # Save the canonical identity first: an interrupted run reuses it on retry.
    order = ['private/etc/darling-platform.plist', 'private/etc/darling-smbios.conf',
             'private/etc/darling-runtime-identity.conf',
             'System/Library/CoreServices/SystemVersion.plist']
    changed = False
    for relative in order:
        changed = atomic_write(checked_path(prefix, relative), files[relative]) or changed
    for relative, data in mac_account_files(prefix).items():
        changed = atomic_write(checked_path(prefix, relative), data) or changed
    return changed


def mac_account_full_name(login):
    """The account's full name as a Mac shows it: the host's first GECOS field, else the login."""
    try:
        gecos = pwd.getpwnam(login).pw_gecos
    except KeyError:
        gecos = ''
    name = gecos.split(',', 1)[0].strip()
    if not name or any(not 32 <= ord(c) <= 126 or c == ':' for c in name):
        name = login
    return name


def mac_account_files(prefix):
    """passwd/master.passwd with Darling's generated user records made Mac-like.

    Darling writes the user as "Darling User" with /bin/bash; a Mac account carries the
    person's full name and zsh. Only lines Darling generated are changed.
    """
    result = {}
    for relative, gecos_field in (('private/etc/passwd', 4), ('private/etc/master.passwd', 7)):
        path = checked_path(prefix, relative)
        if not path.exists():
            continue
        text = path.read_text()
        lines = []
        for line in text.split('\n'):
            fields = line.split(':')
            if (len(fields) > gecos_field + 2 and fields[gecos_field] == 'Darling User'
                    and fields[-1] == '/bin/bash' and fields[0] != 'root'):
                fields[gecos_field] = mac_account_full_name(fields[0])
                fields[-1] = '/bin/zsh'
                line = ':'.join(fields)
            lines.append(line)
        updated = '\n'.join(lines)
        if updated != text:
            result[relative] = updated.encode()
    return result


def prefix_lock(prefix):
    ensure_stopped(prefix)
    path = checked_path(prefix, 'private/etc/.darling-platform.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    stream = os.fdopen(fd, 'r+')
    fcntl.flock(stream, fcntl.LOCK_EX)
    return stream


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--import', dest='source', type=Path, help='OpenCore plist, GenSMBIOS JSON, legacy .conf, or schema-1 plist/JSON')
    parser.add_argument('--set', action='append', default=[], metavar='KEY=VALUE')
    parser.add_argument('--provision', action='store_true', help='Generate missing synthetic identifiers and provision prefix metadata')
    parser.add_argument('--runtime-root', type=Path, help='Runtime supplying SystemVersion.plist (default: saved SDK or /usr/local/libexec/darling)')
    parser.add_argument('--hardware-profile', choices=sorted(HARDWARE_PROFILES),
                        help='Select a validated Mac model and matching sysctl CPU identity')
    parser.add_argument('--os-profile', choices=sorted(OS_PROFILES),
                        help='Select a released macOS ProductVersion/ProductBuildVersion pair')
    parser.add_argument('--cpu-brand-string', help='Override only machdep.cpu.brand_string (printable ASCII)')
    parser.add_argument('--new-serial', action='store_true',
                        help='Replace the saved serial with one laid out like the selected hardware profile\'s')
    parser.add_argument('--show-host', action='store_true',
                        help='Let applications see /proc, /Volumes/SystemRoot, Linux mounts, interface names and host-library variables')
    parser.add_argument('--host-cpuid', action='store_true',
                        help='Leave CPUID instructions reporting the host CPU (no CPUID faulting)')
    parser.add_argument('--host-home-links', action='store_true',
                        help='Keep Darling\'s LinuxHome and Desktop/Documents/... links to the host home')
    parser.add_argument('--rom-oui', help='Explicit three-byte unicast OUI for a missing ROM; default is one of Apple\'s')
    parser.add_argument('--replace-known-defaults', action='store_true',
                        help='Provision only if the prefix identity still has the shared serial or UUID; otherwise change nothing')
    parser.add_argument('--write', action='store_true', help='Write validated overrides to a stopped prefix (otherwise preview only)')
    args = parser.parse_args(argv)
    if args.replace_known_defaults:
        if args.source or args.set:
            parser.error('--replace-known-defaults cannot be combined with --import or --set')
        args.provision = True
    if (args.hardware_profile or args.os_profile or args.cpu_brand_string or args.host_home_links
            or args.new_serial or args.show_host or args.host_cpuid) and not args.provision:
        parser.error('runtime identity profiles require --provision')
    config = Path(__file__).resolve().parents[1] / 'build/config.json'
    saved = json.loads(config.read_text()) if config.exists() else {}
    prefix = args.prefix or Path(os.environ.get('DPREFIX') or saved.get('prefix', str(Path.home() / '.darling')))
    try:
        prefix = prefix.expanduser()
        rom_oui = None
        if args.rom_oui:
            if not args.provision:
                raise ValueError('--rom-oui requires --provision')
            rom_oui = bytes.fromhex(args.rom_oui.replace(':', '').replace('-', ''))
            if len(rom_oui) != 3 or rom_oui[0] & 1:
                raise ValueError('--rom-oui requires exactly three unicast bytes')
        identity_files = [checked_path(prefix, 'private/etc/darling-smbios.conf'), destination(prefix)]
        if args.replace_known_defaults and not any(path.exists() for path in identity_files):
            print('No saved platform identity; nothing to replace.')
            return 0
        with prefix_lock(prefix) if args.write else nullcontext():
            path = destination(prefix)
            properties = {}
            if args.replace_known_defaults and not any(
                    path.exists() and has_known_defaults(load(path)) for path in identity_files):
                print('Platform identity has no shared defaults; nothing changed.')
                return 0
            if args.provision:
                legacy = identity_files[0]
                if legacy.exists():
                    properties.update(load(legacy))
            if path.exists():
                incoming = load(path)
                if 'IOPlatformUUID' in incoming:
                    properties.pop('system-id', None)
                    properties.pop('provisioning_UDID', None)
                properties.update(incoming)
            if args.source:
                incoming = load(args.source)
                if 'IOPlatformUUID' in incoming:
                    properties.pop('system-id', None)
                    properties.pop('provisioning_UDID', None)
                properties.update(incoming)
            if args.hardware_profile:
                hardware = HARDWARE_PROFILES[args.hardware_profile]
                properties['model'] = hardware['model']
                properties['product-name'] = hardware['model']
                properties['manufacturer'] = hardware['manufacturer']
                properties['board-id'] = hardware['board_id']
                properties['target-type'] = hardware['target_type']
            for assignment in args.set:
                key, sep, value = assignment.partition('=')
                if not sep:
                    raise ValueError('--set requires KEY=VALUE')
                if key == 'IOPlatformUUID':
                    properties.pop('system-id', None)
                    properties.pop('provisioning_UDID', None)
                if key == 'model': properties.pop('product-name', None)
                properties[key] = value
            runtime_root = args.runtime_root or Path(saved.get('sdk', '/usr/local/libexec/darling'))
            if args.provision:
                properties = provision(properties, rom_oui, args.hardware_profile, args.new_serial)
                files = provisioning_files(prefix, properties, runtime_root, args.hardware_profile,
                                           args.os_profile, args.cpu_brand_string, args.host_home_links,
                                           args.show_host, args.host_cpuid)
            else:
                properties = validate(properties)
            if args.write:
                changed = (save_provisioning(prefix, properties, runtime_root, args.hardware_profile,
                                             args.os_profile, args.cpu_brand_string, args.host_home_links,
                                             args.show_host, args.host_cpuid)
                           if args.provision else save(prefix, properties))
                print('Platform identity ' + ('saved' if changed else 'unchanged') + '; restart iokitd to apply.')
            else:
                preview = {'schema': 1, 'properties': properties}
                if args.provision:
                    preview['runtimeIdentity'] = load_runtime_identity_bytes(
                        files['private/etc/darling-runtime-identity.conf'])
                    preview['systemVersion'] = plistlib.loads(
                        files['System/Library/CoreServices/SystemVersion.plist'])
                print(json.dumps(preview, default=lambda value: value.hex().upper(), indent=2))
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException, ExpatError) as error:
        parser.exit(1, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
