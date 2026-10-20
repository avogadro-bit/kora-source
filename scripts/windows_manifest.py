"""Let ExifTool's Windows launcher find its Perl runtime under any folder name.

The launcher (`exiftool.exe`, CC0) locates and loads `exiftool_files\\perl5*.dll`
with ANSI Windows APIs. Under a code page such as 1252, a folder named KŌRA is
seen as KORA and Perl is not found. An activeCodePage UTF-8 manifest (Windows 10
1903 and later) makes those APIs use UTF-8 for this one process.
"""
from pathlib import Path
import struct
import xml.etree.ElementTree as ElementTree

RT_MANIFEST, MANIFEST_ID = 24, 1
ASSEMBLY_V3 = 'urn:schemas-microsoft-com:asm.v3'
WINDOWS_SETTINGS_2019 = 'http://schemas.microsoft.com/SMI/2019/WindowsSettings'
# ExifTool 13.59's own manifest sets only longPathAware, which this keeps.
UTF8_MANIFEST = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
<application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
        <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
        <activeCodePage xmlns="http://schemas.microsoft.com/SMI/2019/WindowsSettings">UTF-8</activeCodePage>
    </windowsSettings>
</application>
</assembly>
'''


def manifest_resources(path):
    """(language, bytes) of each RT_MANIFEST #1 entry, read without loading the PE."""
    data = Path(path).read_bytes()
    try:
        pe = struct.unpack_from('<I', data, 60)[0]
        if data[:2] != b'MZ' or data[pe:pe + 4] != b'PE\0\0':
            raise ValueError(f'Not a PE executable: {path}')
        sections, optional_size = struct.unpack_from('<H12xH', data, pe + 6)
        optional = pe + 24
        directories = optional + {0x10b: 96, 0x20b: 112}[struct.unpack_from('<H', data, optional)[0]]
        count = struct.unpack_from('<I', data, directories - 4)[0]
        resources = struct.unpack_from('<I', data, directories + 16)[0] if count > 2 else 0
        if not resources:
            return []
        # (virtual size, virtual address, raw size, raw offset) of each section
        spans = [struct.unpack_from('<8xIIII', data, optional + optional_size + 40 * index)
                 for index in range(sections)]

        def offset(rva):
            for virtual_size, address, raw_size, raw in spans:
                if address <= rva < address + max(virtual_size, raw_size):
                    return raw + rva - address
            raise ValueError(f'Resource outside the sections of {path}')

        root = offset(resources)

        def entries(directory, wanted=None):
            named, ids = struct.unpack_from('<HH', data, root + directory + 12)
            for index in range(named + ids):
                name, target = struct.unpack_from('<II', data, root + directory + 16 + 8 * index)
                if wanted is None or name == wanted:
                    yield name, target & 0x7fffffff

        found = []
        for _, names in entries(0, RT_MANIFEST):
            for _, languages in entries(names, MANIFEST_ID):
                for language, entry in entries(languages):
                    address, size = struct.unpack_from('<II', data, root + entry)
                    manifest = data[offset(address):offset(address) + size]
                    if len(manifest) != size:
                        raise ValueError(f'Truncated manifest in {path}')
                    found.append((language, manifest))
        return found
    except (struct.error, KeyError) as exc:
        raise ValueError(f'Invalid PE resources: {path}') from exc


def read_manifest(path):
    """The application manifest, or None when there is not exactly one."""
    resources = manifest_resources(path)
    return resources[0][1] if len(resources) == 1 else None


def has_utf8_code_page(manifest):
    if not manifest:
        return False
    try:
        assembly = ElementTree.fromstring(manifest)
    except ElementTree.ParseError:
        return False
    settings = assembly.findall(f'{{{ASSEMBLY_V3}}}application/{{{ASSEMBLY_V3}}}windowsSettings/'
                                f'{{{WINDOWS_SETTINGS_2019}}}activeCodePage')
    return any((setting.text or '').strip() == 'UTF-8' for setting in settings)


def replace_manifest(path, manifest, language):
    """Rewrite RT_MANIFEST #1 in place with the Windows resource API."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel32.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD,
                                         ctypes.c_char_p, wintypes.DWORD]
    kernel32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    update = kernel32.BeginUpdateResourceW(str(path), False)
    if not update:
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.UpdateResourceW(update, RT_MANIFEST, MANIFEST_ID, language, manifest, len(manifest)):
        error = ctypes.get_last_error()
        kernel32.EndUpdateResourceW(update, True)
        raise ctypes.WinError(error)
    if not kernel32.EndUpdateResourceW(update, False):
        raise ctypes.WinError(ctypes.get_last_error())


def embed_utf8_manifest(path):
    """Give a Windows executable UTF8_MANIFEST, refusing to drop any of its settings."""
    resources = manifest_resources(path)
    if len(resources) != 1:
        raise SystemExit(f'Expected one application manifest in {path}, found {len(resources)}')
    language, current = resources[0]
    dropped = ({element.tag for element in ElementTree.fromstring(current).iter()}
               - {element.tag for element in ElementTree.fromstring(UTF8_MANIFEST).iter()})
    if dropped:
        raise SystemExit(f'The UTF-8 manifest would drop {sorted(dropped)} from {path}')
    replace_manifest(path, UTF8_MANIFEST, language)
    if read_manifest(path) != UTF8_MANIFEST:
        raise SystemExit(f'The UTF-8 manifest was not written to {path}')
    return language
