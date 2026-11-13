# Explicit platform identity overrides

First-time setup (`scripts/install-runtime.sh` creating a new prefix) runs
`--provision --write` once, so each new prefix gets its own synthetic identity.
A prefix without saved identity files keeps the host-derived UUID and
`DARLING-` serial; launching never generates an override. Import mode uses
values supplied by the user. `--provision` generates synthetic identifiers; it
does not issue authentic Apple identities or change CPU, GPU, or security
metadata. The overrides are for application compatibility; they are not intended
to bypass anti-cheat, telemetry, licensing, or platform security controls.

> **Synthetic, local metadata.** These values are not Apple-issued identifiers,
> credentials or authentication tokens. Do not use them with Apple services or
> to impersonate real hardware. This repository does not pass them to Riot as
> authentication data; the values are exposed to guest applications through
> IOKit, and the official client's later handling of them is outside this
> repository's scope. See the
> [interoperability and compliance scope](INTEROPERABILITY.md).

Preview an OpenCore `config.plist`, a flat GenSMBIOS JSON file, or an existing
`darling-smbios.conf` without changing the selected prefix:

```sh
python3 tools/configure-darling-platform.py --prefix /absolute/prefix --import /path/to/config.plist
```

After reviewing the preview, shut down that prefix and explicitly save:

```sh
DPREFIX=/absolute/prefix python3 build/runtime/tools/stop-darling-runtime.py
python3 tools/configure-darling-platform.py --prefix /absolute/prefix --import /path/to/config.plist --write
```

The default prefix selection is `--prefix`, then `DPREFIX`, then saved
`build/config.json`, then `~/.darling`. Writing refuses a live prefix. The
configuration is activated when that prefix's iokitd starts again; it is an
immutable startup snapshot. An absent or invalid configuration preserves the
existing defaults. Invalid daemon-side configuration is reported once.

The file is `<prefix>/private/etc/darling-platform.plist`. It uses this schema:

```json
{
  "schema": 1,
  "properties": {
    "IOPlatformSerialNumber": "USER-SUPPLIED",
    "model": "UserSuppliedModel"
  }
}
```

### Hardware profiles

`--provision --hardware-profile macbookpro16,1|imac20,1` together with one of the
allowlisted `--os-profile` values makes every identity surface describe one real
Mac. Besides the IOKit platform properties above it writes
`private/etc/darling-runtime-identity.conf`, which every guest process reads, and
a matching `SystemVersion.plist`:

| Key | Consumer | MacBookPro16,1 value |
|---|---|---|
| `hw.model` | sysctl | `MacBookPro16,1` |
| `machdep.cpu.vendor`, `machdep.cpu.brand_string` | sysctl | `GenuineIntel`, `Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz` |
| `machdep.cpu.signature` | sysctl `machdep.cpu.signature`/`family`/`model`/`stepping` | `0x906ED` (6 / 158 / 13) |
| `hw.cpufamily` | sysctl | `0x0F817246` (`CPUFAMILY_INTEL_KABYLAKE`) |
| `hw.cpufrequency` | sysctl, system_profiler | `2400000000` |
| `cpu.threads_per_core` | sysctl `hw.physicalcpu*`, `machdep.cpu.core_count`, system_profiler | `2` |
| `kern.osproductversion`, `kern.osversion` | sysctl, `SystemVersion.plist` | `14.7`, `23H124` |
| `kern.hostname` | darlingserver sets it in the container's UTS namespace (`uname`, `gethostname`, `kern.hostname`) | `MacBook-Pro.local` |
| `gpu.integrated.*`, `gpu.discrete.*` | iokitd `IOPCIDevice` entries, Metal `MTLDevice.name`, system_profiler | Intel UHD Graphics 630 `8086:3E9B`, AMD Radeon Pro 5500M `1002:7340` |
| `home.isolated` | darlingserver: no `LinuxHome`, and `Desktop`, `Documents`, ... are prefix-local folders, not links into `/Volumes/SystemRoot` | `1` (`--host-home-links` writes `0`) |
| `host.hide` | libsystem_kernel (`guest_view.c`, `sysctl_net.c`, `execve.c`), mldr, libc `getenv` | `1` (`--show-host` writes `0`) |
| `cpu.emulate_cpuid` | libsystem_kernel `sigexc.c` | `1` (`--host-cpuid` writes `0`) |

Logical CPU counts stay the host's, since the clients size worker pools from
them; physical counts follow the profile's SMT ratio. With a profile, a host
Intel GPU takes the integrated identity and any AMD or NVIDIA GPU the discrete
one; only names and IDs change, never the device that renders. `--new-serial`
replaces the saved serial with one laid out like that model's (plant `C02`,
late-2019/2020 year and week characters, an `MD6x` configuration code); without
it an existing serial is kept, so the identity stays stable across runs.

A stopped prefix is required, and changes take effect when its processes start
again.

### What applications see of the host

With `host.hide=1`, processes whose executable lives under `/Applications` or
`/Users` (Darling's own daemons and tools are exempt; they read the host for the
guest):

- **Paths.** Lookups that resolve into the host root or Linux `/proc` fail with
  `ENOENT`: `/proc`, `/Volumes/SystemRoot/...`, `/dev/../etc/...`. The exceptions are
  the host files Darling links into the guest (`/dev`, `/etc/localtime`,
  `/etc/resolv.conf` and its resolver target, `/etc/nsswitch.conf`,
  `/etc/machine-id`, `/usr/share/zoneinfo`), `/proc/self/fd` (behind `/dev/fd`),
  CoreVideo's `/proc/self/mem` writer and the host `xdg-open` LaunchServices runs.
  `/dev` and Darling's other links into the host stat and readlink as the files and
  directories they are on a Mac. Listings of `/` and `/Volumes` omit `proc`,
  `SystemRoot`, `DarlingEmulatedDrive` and Darling's prefix files; new links into
  the host root are refused. Only system calls made by guest code are checked
  (the wrappers sit in the BSD syscall table); libsystem_kernel's internal host
  reads are unaffected.
- **Mounts.** `getfsstat`/`statfs` report one APFS volume (`/dev/disk1s1` on `/`)
  and `devfs` on `/dev`.
- **Network interfaces.** `lo0`; Wi-Fi first, then wired NICs, as `en0`, `en1`, ...;
  VPN tunnels (Tailscale, WireGuard, tun) as `utunN`; bridges, container and VM
  interfaces are left out. `SIOCGIFMEDIA` maps the Mac names back.
- **Environment.** mldr leaves host-only variables (X11, Mesa/Vulkan/NVIDIA,
  audio, D-Bus, `XDG_*`, `LD_*`, fontconfig, `DARLING_*`, `RCLOL_*`, `__mldr_*`; the
  list is `include/common/host_env.h`) out of every guest process's `environ`.
  The host libraries in the process keep reading them from the Linux side, libc
  `getenv` still answers them for Darling's frameworks, and `execve` passes them on
  to children.

With `cpu.emulate_cpuid=1` each guest process enables Linux CPUID faulting. A
`CPUID` instruction then traps (about 2 µs instead of ~0.1 µs) and returns the
host's values with the identity leaves replaced: the leaf-1 signature, the hybrid
flag, leaf 0x16 frequencies, leaf 0x1A core type and the brand string. Feature
bits stay the host's. This needs a CPU and kernel with CPUID faulting
(`cpuid_fault` in `/proc/cpuinfo`); without it `CPUID` keeps reporting the host.


Supported properties:

| Property | Configuration value | IOKit value |
|---|---|---|
| `IOPlatformSerialNumber` | Printable ASCII string, 1–64 characters | NSString |
| `provisioning_UDID` | UUID string matching `IOPlatformUUID` | NSString |
| `IOPlatformUUID` | Nonzero UUID; normalized to uppercase | NSString |
| `manufacturer`, `model`, `product-name`, `board-id` | Printable ASCII string, 1–128 characters | NUL-terminated NSData |
| `mlb-serial-number` | Printable ASCII string, 1–64 characters | NUL-terminated NSData |
| `ROM` | Exactly 6 bytes; JSON accepts hexadecimal text | NSData |
| `system-id` | Exactly 16 bytes; JSON accepts hexadecimal text | NSData |

Supplying a model also supplies the matching product name unless one is
explicitly provided. Supplying a UUID derives its EFI little-endian `system-id`;
a conflicting explicit system ID is rejected. No other missing fields are
invented. These properties belong to the existing platform service; the tool
does not manufacture a firmware/NVRAM registry hierarchy.

For OpenCore, the importer reads `PlatformInfo/Generic` (or a standalone Generic
dictionary): `SystemProductName`, `SystemSerialNumber`, `SystemUUID`, `MLB`,
and `ROM`. It ignores unrelated boot and security settings. GenSMBIOS aliases
include `Type`, `Serial`, `Board Serial`, and `SmUUID`. Legacy `SMBIOS_*` identity
keys are accepted from `.conf`; parsing never executes shell expressions.

Existing configured fields survive a partial import. A new explicit UUID
replaces its previously derived system ID. `--set KEY=VALUE` can update an
individual field. Unknown schema versions, unsupported properties, malformed
values, and duplicate JSON fields are rejected.

Writes are atomic with mode 0600. Repeating the same write changes nothing. The
first previous configuration is kept as
`darling-platform.plist.before-platform-change`, also with mode 0600. Importing
an older `.conf` never edits that source. Symlinks escaping the prefix are
rejected. To restore the original defaults, remove the override file while the
prefix is stopped, then restart it.

### The recorded IOKit registry

With the `macmini8,1` profile, iokitd publishes the IOService plane of a real
Macmini8,1 instead of a handful of entries: the ACPI and PCI tree, SMC, USB, HID,
storage, network, audio, Thunderbolt and framebuffer entries with their properties
(about 610 entries). iokitd's own services stand where that Mac has them: the
platform expert is named after the model, `IOPMrootDomain` is below
`AppleACPIPlatformExpert`, `IOSurfaceRoot` below `IOResources`, the GPU accelerator
below `IGPU@2`, and the host's displays below the framebuffers as `display0`.

The data is `src/IOStaticRegistryData.inc` in `patches/iokitd.patch`, made by
`tools/build-ioregistry.py` from an `ioreg -l -w0` dump. The one in the tree comes
from the public Macmini8,1 dump in khronokernel/DarwinDumped (macOS 10.14.5). The
tool keeps nothing that identifies the recorded machine: redacted values, hardware
addresses, serial numbers, UUIDs, user and Bluetooth names and driver statistics are
dropped. Addresses and the SSD serial and model are filled in from the prefix's
runtime identity (`net.en0.ether`, `net.en1.ether`, `hw.disk.*`); `en2` to `en4` get
the same derived addresses the interface list reports.

Limits: the entries answer lookups and matching but cannot be opened (no SMC keys,
no HID reports), the shape is that of macOS 10.14 rather than 14, and interfaces the
guest's interface list lacks (`en5`, `en6`) are left out. Other profiles keep the
earlier flat layout.

## Opt-in provisioning

Preview a fresh or repaired identity without writing anything:

```sh
python3 tools/configure-darling-platform.py --prefix /absolute/prefix --provision
```

Stop the prefix, then save the identity and prefix metadata:

```sh
DPREFIX=/absolute/prefix python3 build/runtime/tools/stop-darling-runtime.py
python3 tools/configure-darling-platform.py --prefix /absolute/prefix --provision --write
```

Launch Darling normally afterwards. This requires the updated iokitd from this
PR; the config tool alone cannot update an older running daemon. Besides
first-time setup above, provisioning runs automatically in one other case:
after installing, `scripts/update.sh` runs
`configure-darling-platform.py --replace-known-defaults --write`, which
provisions the prefix only if its saved identity still contains the shared
serial or UUID below. Prefixes without saved identity files, or whose saved
values are all custom, are left byte-for-byte unchanged.

Missing serials use 12 characters and missing MLBs use 17 characters, sampled
with Python's `secrets` module from `0123456789ABCDEFGHJKLMNPQRSTUVWXYZ` (Base-34).
These are synthetic strings, with no Apple model, factory, date or checksum
validation, allocation, or guarantee of acceptance by Apple services. Missing
UUIDs use RFC4122 v4; `system-id` contains the UUID's 16 little-endian bytes.
For this project `provisioning_UDID` is the uppercase platform UUID alias, not
a separate Apple provisioning credential or a claim about hardware UDIDs.

Missing ROMs default to six random bytes with the local/unicast bits set. You
can explicitly supply a three-byte OUI using `--rom-oui AA:BB:CC` (replace the
example with your chosen unicast OUI). It only affects a missing ROM. An OUI
does not make a generated identity Apple-issued.

Provisioning replaces the known shared serial `C02ZL0GVMD6N` and UUID
`6F3B2A1E-8C4D-4E5F-9A7B-1D2C3E4F5A6B`, along with the latter's derived fields
(including a standalone `system-id` or `provisioning_UDID` derived from it).
It preserves other existing custom values, including imported serials and UUIDs
that do not follow the generated formats. A standalone custom `system-id` is
preserved by deriving its UUID instead of generating a different one. Model,
board and manufacturer values are only set when supplied by the user.

The command reads an existing prefix `darling-smbios.conf` for migration, then
applies the canonical plist, an explicit import, and `--set` values in that
order. It writes:

- `private/etc/darling-platform.plist`: canonical runtime overrides.
- `private/etc/darling-smbios.conf`: matching shell-quoted `SMBIOS_*` values,
  including `SMBIOS_PROVISIONING_UDID`; unrelated legacy settings are not exported.
- `System/Library/CoreServices/SystemVersion.plist`: an exact copy of the selected
  runtime's metadata, not a fabricated macOS release. The runtime root defaults
  to the saved SDK path or `/usr/local/libexec/darling`; override with
  `--runtime-root /path/to/runtime`.

A valid runtime version file is required. The command checks all destinations
before changing identity files, rejects live prefixes and escaping symlinks,
backs up each previous file once with `.before-platform-change`, and replaces
each file atomically. The set of three files is not a single transaction: the
canonical identity is saved first so rerunning after interruption completes
provisioning with the same identity. Concurrent CLI writers serialize through
a per-prefix lock. Repeated writes preserve identifiers and unchanged files.
Previewing a fresh identity generates a sample; only `--write` makes it stable.
To restore host-derived defaults after provisioning, remove both identity files
while stopped, so a later provisioning run cannot reimport the legacy copy.

## system_profiler

The prefix's `/usr/sbin/system_profiler` (installed by
`tools/install-darling-system-profiler.py`) answers `SPHardwareDataType` and
`SPSoftwareDataType` from the running guest: model, serial number, platform UUID
and provisioning UDID from IOKit's `IOPlatformExpertDevice` (via `ioreg`), CPU,
cache and memory from `sysctl`, and the OS version from `sw_vers` and `uname`. It
keeps no identity of its own, so it reports the same values as IOKit, including any
override saved by this tool. A field the guest does not provide is left out.
`python3 -m unittest tests.test_system_profiler` checks the output with stub
commands.

`SPDisplaysDataType` reads the host DRM cards. With `DARLING_METAL_MAC_GPU_NAME`
set (the launcher default), an AMD or NVIDIA host card is reported as the
`MacBookPro16,1` discrete GPU: `AMD Radeon Pro 5500M`, vendor `0x1002`, device
`0x7340`, bus PCIe and VRAM from `DARLING_METAL_VRAM_MB` (4096 by default; a
value that is not a positive decimal keeps the default). An Intel card is
reported as `Intel UHD Graphics 630` on bus Built-In with shared memory, as
`MTLDevice.name` does. This keeps the display report consistent with Metal;
without the variable the host card is reported as-is.

iokitd publishes the GPUs in the IOKit registry too, from the same host DRM
cards: an `IOPCIDevice` (`IGPU` for Intel, `GFX0` for AMD or NVIDIA) under the
platform device, with `vendor-id`, `device-id`, `revision-id` and `class-code`,
and an accelerator child (`IntelAccelerator`,
`AMDRadeonX6000_AMDNavi14GraphicsAccelerator` or `nvAccelerator`, all
conforming to `IOAccelerator`). An Intel or AMD card carries the same
`MacBookPro16,1` identity as `MTLDevice.name`; an NVIDIA card keeps its own
vendor and device IDs, as Metal keeps its own name. At most one integrated and
one discrete GPU are published. The accelerator's registry entry ID is the
`MTLDevice.registryID` of a device from that vendor (`0x100000427` integrated,
`0x100000439` discrete), so `IORegistryEntryIDMatching(device.registryID)`
finds it and its parent's PCI IDs, as Dawn and ANGLE expect. iokitd does not
see `DARLING_METAL_MAC_GPU_NAME`, so with the variable unset Metal reports the
host's name while IOKit keeps the Mac identity.
