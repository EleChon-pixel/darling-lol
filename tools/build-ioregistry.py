#!/usr/bin/env python3
"""Turn an `ioreg -l -w0` dump of a real Mac into iokitd's static registry data.

iokitd publishes the IOService plane of the selected hardware profile from this
data, and places its own live services (platform expert, power management, GPU,
displays, IOSurface) where the dump has them.

Nothing that identifies the machine the dump came from is kept: redacted values,
addresses, serial numbers, UUIDs, user and device names are dropped, and the
ones a Mac must have are filled in by iokitd from the prefix's runtime identity
(see IDENTITY below).

    build-ioregistry.py IOReg.txt --model Macmini8,1 --output IOStaticRegistryData.inc
"""
import argparse
import plistlib
import re
import sys
import zlib

ENTRY = re.compile(r'^([ |]*)\+-o (.+?)  <class ([^,>]+), id (0x[0-9a-f]+)')
PROPERTY = re.compile(r'^[ |]*"((?:[^"\\]|\\.)*)" = (.*)$')

# Larger values are driver state and statistics, not identity.
MAX_VALUE = 1500

# Run-time state, statistics and anything naming the dumped machine or its user.
DROP_KEYS = re.compile(
    r'^(IOKitDiagnostics|IOReportLegend.*|.*Statistics.*|CCIOReport.*|IOConsoleUsers|IOConsoleLocked'
    r'|IOConsoleSecurityInterest|BluetoothLocalName|BootSessionUUID|IOPlatformUUID|IOPlatformSerialNumber'
    r'|serial-number|system-id|.*[Ss]erial ?[Nn]umber.*|kUSBSerialNumberString|iSerialNumber|UUID|Domain UUID'
    r'|kUSBContainerID|IOMACAddress|local-mac-address|IONetworkData|IOActivePacketFilters|IOLinkStatus'
    r'|IOLinkSpeed|IOSelectedMedium|IOActiveMedium|.*Address.*|.*-sn|mDNS_Offload_Capable|IOBusyInterest|IOGeneralInterest'
    r'|IOAppPowerStateInterest|IOPriorityPowerStateInterest|IOPowerManagement|IODisplayEDID.*'
    r'|DisplayProductID|DisplayVendorID|IODisplayPrefsKey.*|IODisplayAttributes|IODisplayGUID'
    r'|startup-timing|IOMaximumMappedIOByteCount|Used Bytes|ssid.*|.*SSID.*|IO80211.*Locale.*'
    r'|IO80211CountryCode|IOUserClientCreator|IOUserClientDefaultLocking|PowerControlState'
    r'|HIDEventServiceProperties|Elements|Keyboard|Mouse|HIDPointerAccelerationTable.*)$')

# Entries below these are whatever the dumped machine had plugged in or mounted.
DROP_SUBTREES = {
    'AppleDisplay', 'AppleBacklightDisplay', 'IODisplayConnect',  # iokitd publishes the host's displays
    'IOHIDUserDevice',                                            # remote-desktop style virtual devices
}
# Thunderbolt and other secondary interfaces the guest's interface list has
# (libsystem_kernel sysctl_net.c mac_phantoms). Their addresses are derived from
# en0's exactly as there; an interface that list lacks is not published.
SECONDARY_INTERFACES = {'en2', 'en3', 'en4'}

# Entries iokitd already serves itself. The static entry gives the place and
# name; the live object stands there instead.
LIVE = {
    'IOPlatformExpertDevice': 'platform',
    'IOPMrootDomain': 'power',
    'IOSurfaceRoot': 'surface',
    'IntelAccelerator': 'accelerator',
}

# Values filled in from /private/etc/darling-runtime-identity.conf.
# (entry name pattern, class pattern) -> {property: (identity key, kind)}
IDENTITY = [
    (r'^BCM5701Enet$|^en0$', r'.*', {'IOMACAddress': ('net.en0.ether', 'mac')}),
    (r'^AppleBCMWLANCore$|^en1$', r'.*', {'IOMACAddress': ('net.en1.ether', 'mac')}),
    (r'^GIGE@0$', r'^IOPCIDevice$', {'local-mac-address': ('net.en0.ether', 'mac')}),
    (r'^ARPT@0$', r'^IOPCIDevice$', {'local-mac-address': ('net.en1.ether', 'mac')}),
    (r'.*', r'^IONVMeBlockStorageDevice$|^AppleANS2Controller$', {
        'Serial Number': ('hw.disk.serial', 'string'), 'Model Number': ('hw.disk.model', 'string')}),
    (r'.*', r'^IONVMeBlockStorageDevice$', {
        'Device Characteristics/Serial Number': ('hw.disk.serial', 'string'),
        'Device Characteristics/Product Name': ('hw.disk.model', 'string')}),
]

# IOKit class ancestry of the classes code matches on. ioreg does not print it.
SUPERCLASSES = {
    'IOPCIDevice': ['IOService'],
    'IOACPIPlatformDevice': ['IOPlatformDevice', 'IOService'],
    'IOPlatformDevice': ['IOService'],
    'AppleSMC': ['IOACPIPlatformDevice', 'IOService'],
    'AppleACPIPlatformExpert': ['IOACPIPlatformExpert', 'IODTPlatformExpert', 'IOPlatformExpert', 'IOService'],
    'IOUSBHostDevice': ['IOUSBDevice', 'IOService'],
    'IOUSBHostInterface': ['IOUSBInterface', 'IOService'],
    'AppleUSBXHCISPT': ['AppleUSBXHCIPCI', 'AppleUSBXHCI', 'AppleUSBHostController', 'IOUSBHostController', 'IOService'],
    'AppleUSBXHCITR': ['AppleUSBXHCIPCI', 'AppleUSBXHCI', 'AppleUSBHostController', 'IOUSBHostController', 'IOService'],
    'AppleUSBVHCIBCE': ['AppleUSBVHCI', 'AppleUSBHostController', 'IOUSBHostController', 'IOService'],
    'IOHIDInterface': ['IOService'],
    'AppleUserHIDDevice': ['IOHIDDevice', 'IOService'],
    'IOHIDUserDevice': ['IOHIDDevice', 'IOService'],
    'AppleHIDTransportHIDDevice': ['IOHIDDevice', 'IOService'],
    'AppleUserUSBHostHIDDevice': ['IOHIDDevice', 'IOService'],
    'IOUSBHostHIDDevice': ['IOHIDDevice', 'IOService'],
    'AppleEmbeddedKeyboard': ['IOHIDEventDriver', 'IOHIDEventService', 'IOHIDDevice', 'IOService'],
    'IOMedia': ['IOStorage', 'IOService'],
    'IOBlockStorageDriver': ['IOStorage', 'IOService'],
    'IOGUIDPartitionScheme': ['IOPartitionScheme', 'IOStorage', 'IOService'],
    'AppleAPFSContainerScheme': ['IOPartitionScheme', 'IOStorage', 'IOService'],
    'AppleAPFSContainer': ['IOService'],
    'AppleAPFSVolume': ['AppleAPFSMedia', 'IOMedia', 'IOStorage', 'IOService'],
    'AppleAPFSMedia': ['IOMedia', 'IOStorage', 'IOService'],
    'IONVMeBlockStorageDevice': ['IOBlockStorageDevice', 'IOService'],
    'AppleANS2Controller': ['AppleANS2NVMeController', 'IONVMeController', 'IOService'],
    'BCM5701Enet': ['IOEthernetController', 'IONetworkController', 'IOService'],
    'IOEthernetAVBInterface': ['IOEthernetInterface', 'IONetworkInterface', 'IOService'],
    'AppleBCMWLANCore': ['IO80211Controller', 'IOEthernetController', 'IONetworkController', 'IOService'],
    'IOEthernetInterface': ['IONetworkInterface', 'IOService'],
    'IO80211Interface': ['IOEthernetInterface', 'IONetworkInterface', 'IOService'],
    'AppleThunderboltIPPort': ['IOEthernetController', 'IONetworkController', 'IOService'],
    'AppleIntelFramebuffer': ['IOFramebuffer', 'IOGraphicsDevice', 'IOService'],
    'IntelAccelerator': ['IOAccelerator', 'IOGraphicsAccelerator2', 'IOService'],
    'AppleHDAController': ['IOAudioDevice', 'IOService'],
    'AppleHDADriver': ['IOAudioDevice', 'IOService'],
    'AppleHDAEngineOutput': ['IOAudioEngine', 'IOService'],
    'AppleHDAEngineInput': ['IOAudioEngine', 'IOService'],
    'IOPCI2PCIBridge': ['IOPCIBridge', 'IOService'],
    'AppleACPIPCI': ['IOPCIBridge', 'IOService'],
    'AppleKeyStore': ['IOService'],
    'IOBluetoothHCIController': ['IOService'],
    'BroadcomBluetoothHostController': ['IOBluetoothHostController', 'IOService'],
    'IOResources': ['IOService'],
}


INTERFACE_CLASSES = {'IOEthernetInterface', 'IOEthernetAVBInterface', 'IO80211Interface'}
PUBLISHED_INTERFACES = {'en0', 'en1'} | SECONDARY_INTERFACES


def bsd_name(entry):
    return entry['raw'].get('BSD Name', '').strip('"')


HARDWARE_ADDRESS = re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b')


class Unparsed(Exception):
    pass


def parse_value(text):
    """One ioreg value -> a plist value. Raises Unparsed for shapes ioreg cannot round-trip."""
    value, rest = _value(text.strip())
    if rest.strip():
        raise Unparsed(text)
    return value


def _string(text):
    assert text[0] == '"'
    out, i = [], 1
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            out.append(text[i + 1])
            i += 2
        elif text[i] == '"':
            return ''.join(out), text[i + 1:]
        else:
            out.append(text[i])
            i += 1
    raise Unparsed(text)


def _value(text):
    if not text:
        raise Unparsed(text)
    if text[0] == '"':
        return _string(text)
    if text[0] == '<':
        end = _data_end(text)
        body, rest = text[1:end], text[end + 1:]
        if body.startswith('"'):
            parts = []
            while body:
                part, body = _string(body)
                parts.append(part.encode() + b'\0')
                body = body.lstrip(',')
            return b''.join(parts), rest
        if not re.fullmatch(r'[0-9a-fA-F]*', body) or len(body) % 2:
            raise Unparsed(text)
        return bytes.fromhex(body), rest
    if text[0] in '{(':
        closing = '}' if text[0] == '{' else ')'
        items, rest = [], text[1:]
        while True:
            rest = rest.lstrip()
            if rest.startswith(closing):
                rest = rest[1:]
                break
            if text[0] == '{':
                key, rest = _string(rest)
                if not rest.startswith('='):
                    raise Unparsed(text)
                item, rest = _value(rest[1:])
                items.append((key, item))
            else:
                item, rest = _value(rest)
                items.append(item)
            rest = rest.lstrip()
            if rest.startswith(','):
                rest = rest[1:]
        return (dict(items) if text[0] == '{' else items), rest
    word = re.match(r'(Yes|No)\b', text)
    if word:
        return word.group(1) == 'Yes', text[word.end():]
    number = re.match(r'-?\d+', text)
    if number:
        value = int(number.group(0))
        if not -2**63 <= value < 2**64:
            raise Unparsed(text)
        # plistlib writes only signed 64-bit integers; wrap the few larger ones.
        return (value - 2**64 if value >= 2**63 else value), text[number.end():]
    raise Unparsed(text)


def _data_end(text):
    quoted = False
    for i, char in enumerate(text):
        if char == '"' and text[i - 1] != '\\':
            quoted = not quoted
        elif char == '>' and not quoted:
            return i
    raise Unparsed(text)


def scrub(value):
    """Apply DROP_KEYS inside nested dictionaries too."""
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items() if not DROP_KEYS.match(key)}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str) and HARDWARE_ADDRESS.search(value):
        raise Unparsed(value)
    return value


def read_dump(path):
    entries = []
    with open(path, errors='replace') as handle:
        lines = handle.read().split('\n')
    for line in lines:
        match = ENTRY.match(line)
        if match:
            entries.append({'depth': len(match.group(1)) // 2, 'name': match.group(2),
                            'class': match.group(3), 'id': int(match.group(4), 16), 'raw': {}})
            continue
        match = PROPERTY.match(line)
        if match and entries:
            entries[-1]['raw'][match.group(1)] = match.group(2)
    return entries


def build(entries, model):
    out, stack, skip_below = [], [], None
    stats = {'entries': 0, 'properties': 0, 'dropped': 0, 'unparsed': 0}
    for entry in entries:
        depth = entry['depth']
        if skip_below is not None:
            if depth > skip_below:
                continue
            skip_below = None
        if depth == 0:
            continue  # the registry root is iokitd's own
        if (entry['class'] in DROP_SUBTREES or '*' in entry['name']
                or (entry['class'] in INTERFACE_CLASSES and bsd_name(entry) not in PUBLISHED_INTERFACES)):
            skip_below = depth
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1] if stack else -1
        properties = {}
        for key, raw in entry['raw'].items():
            if '*' in raw or len(raw) > MAX_VALUE or DROP_KEYS.match(key):
                stats['dropped'] += 1
                continue
            try:
                properties[key] = scrub(parse_value(raw))
            except (Unparsed, AssertionError, IndexError):
                stats['unparsed'] += 1
        record = {'n': entry['name'], 'c': entry['class'], 'i': entry['id'], 'p': parent, 'P': properties}
        chain = SUPERCLASSES.get(entry['class'])
        if chain:
            record['s'] = chain
        if entry['class'] in LIVE:
            record['l'] = LIVE[entry['class']]
            record['P'] = {}
        identity = {}
        for name, cls, fields in IDENTITY:
            if re.search(name, entry['name']) and re.search(cls, entry['class']):
                identity.update({key: list(value) for key, value in fields.items()})
        if entry['class'] in INTERFACE_CLASSES and bsd_name(entry) in SECONDARY_INTERFACES:
            identity['IOMACAddress'] = ['net.en0.ether', 'mac~' + bsd_name(entry)]
            if parent >= 0:  # its controller reports the same address
                out[parent].setdefault('I', {})['IOMACAddress'] = identity['IOMACAddress']
        if identity:
            record['I'] = identity
        stack.append((depth, len(out)))
        out.append(record)
        stats['entries'] += 1
        stats['properties'] += len(record['P'])
    return {'model': model, 'entries': out}, stats


def emit(data, output):
    blob = plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=True)
    packed = zlib.compress(blob, 9)
    lines = ['// Generated by tools/build-ioregistry.py; do not edit.',
             f'// {len(data["entries"])} IOService entries of a {data["model"]}, zlib-compressed XML property list.',
             f'static const unsigned long kStaticRegistrySize = {len(blob)}UL;',
             'static const unsigned char kStaticRegistryData[] = {']
    for offset in range(0, len(packed), 24):
        lines.append(','.join(str(byte) for byte in packed[offset:offset + 24]) + ',')
    lines.append('};')
    with open(output, 'w') as handle:
        handle.write('\n'.join(lines) + '\n')
    return len(blob), len(packed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('dump')
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    data, stats = build(read_dump(args.dump), args.model)
    raw, packed = emit(data, args.output)
    print(f'{stats["entries"]} entries, {stats["properties"]} properties '
          f'({stats["dropped"]} dropped, {stats["unparsed"]} unparsed); '
          f'{raw} bytes, {packed} compressed', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
