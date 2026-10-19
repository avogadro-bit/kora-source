"""Keep native release outputs separate when building both Mac architectures."""
import os
from pathlib import Path


def release_paths(root):
    variant = os.environ.get('KORA_BUILD_VARIANT', '')
    if variant not in ('', 'arm64', 'x86_64'):
        raise ValueError('KORA_BUILD_VARIANT must be arm64, x86_64, or unset')
    root = Path(root)
    build = root / 'build' / variant if variant else root / 'build'
    suffix = '-' + variant if variant else ''
    return build, root / 'dist' / ('macos' + suffix), root / 'dist' / ('release' + suffix)
