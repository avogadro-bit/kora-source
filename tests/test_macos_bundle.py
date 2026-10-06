import unittest
from unittest.mock import patch

from scripts.audit_macos_bundle import deployment_targets, inspect_binary, version


class MacBundleTests(unittest.TestCase):
    def test_deployment_target_does_not_use_sdk_or_linker_version(self):
        commands = '''Load command 9
      cmd LC_BUILD_VERSION
 platform MACOS
    minos 11.0
      sdk 26.5
   ntools 1
     tool LD
  version 1267.0
'''
        self.assertEqual(deployment_targets(commands), ['11.0'])

    def test_legacy_and_multiple_architectures(self):
        commands = '''Load command 2
 cmd LC_VERSION_MIN_MACOSX
 version 10.15
 sdk 15.0
Load command 9
 cmd LC_BUILD_VERSION
 minos 14.0
 sdk 26.5
'''
        self.assertEqual(deployment_targets(commands), ['10.15', '14.0'])
        self.assertEqual(version('14'), version('14.0.0'))

    def test_rejects_missing_target(self):
        with self.assertRaisesRegex(ValueError, 'no macOS deployment target'):
            deployment_targets('Load command 1\n cmd LC_UUID\n')

    def test_rejects_newer_runtime_and_machine_specific_libraries(self):
        commands = '''Load command 0
 cmd LC_BUILD_VERSION
 minos 26.0
 sdk 26.5
Load command 1
 cmd LC_LOAD_DYLIB
 name /opt/homebrew/lib/libssl.dylib (offset 24)
Load command 2
 cmd LC_LOAD_DYLIB
 name /System/Library/Frameworks/AppKit.framework/AppKit (offset 24)
'''
        with patch('scripts.audit_macos_bundle.subprocess.check_output', side_effect=[commands, 'arm64\n']):
            result = inspect_binary('Python', '14.0', 'arm64')
        self.assertEqual(len(result['problems']), 2)
        self.assertIn('requires macOS 26.0', result['problems'][0])

    def test_rejects_wrong_architecture(self):
        with patch('scripts.audit_macos_bundle.subprocess.check_output', side_effect=[
                'Load command 1\n cmd LC_BUILD_VERSION\n minos 11.0\n', 'x86_64\n']):
            result = inspect_binary('Python', '14.0', 'arm64')
        self.assertEqual(result['problems'], ['missing arm64 architecture'])
