"""Resolve optional tools without relying on an interactive shell's PATH."""
from pathlib import Path
import shutil
import sys


def find_exiftool():
    """Honor PATH first, then standard macOS package-manager installations."""
    executable = shutil.which("exiftool")
    if executable:
        return str(Path(executable).resolve())
    if sys.platform == "darwin":
        for candidate in ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool",
                          "/opt/local/bin/exiftool"):
            executable = shutil.which(candidate)
            if executable:
                return str(Path(executable).resolve())
    if sys.platform == 'win32':
        from .platform_support import windows_data_directory
        candidates = [windows_data_directory()/'tools'/'exiftool.exe']
        if getattr(sys, 'frozen', False):
            candidates.insert(0, Path(sys.executable).parent/'tools'/'exiftool.exe')
        for candidate in candidates:
            executable = shutil.which(str(candidate))
            if executable:
                return str(Path(executable).resolve())
    return None


def read_exiftool(executable, path, arguments, *, binary=False):
    """Read one file, with explicit UTF-8 and no console flash on Windows.

    ExifTool recommends a UTF-8 argument file for Windows Unicode paths.
    stdin supplies it without a temporary filename or a shell. Windows does
    not allow CR/LF in filenames; reject them instead of parsing extra args.
    """
    import subprocess
    name = str(path)
    options = {'capture_output':True, 'check':True, 'timeout':20}
    command = [executable, *arguments]
    if sys.platform == 'win32':
        if '\n' in name or '\r' in name:
            raise ValueError('Invalid Windows photo path.')
        command += ['-charset', 'filename=utf8', '-@', '-']
        options.update(input=(name+'\n').encode('utf-8'), creationflags=0x08000000)
    else:
        command.append(name)
    result = subprocess.run(command, **options)
    if binary or isinstance(result.stdout, str):
        return result.stdout
    return result.stdout.decode('utf-8')
