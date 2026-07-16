import unittest

from verify_packaging_toolchain import ToolchainError, verify_versions


class VerifyPackagingToolchainTest(unittest.TestCase):
    def contract(self):
        return {
            "schema_version": 1,
            "python": "3.12.10",
            "zlib_build": "1.2.13",
            "zlib_runtime": "1.2.13",
            "gnu_tar": "1.35",
            "zstd": "1.5.5",
        }

    def test_exact_toolchain_passes(self):
        value = self.contract()
        verify_versions(value, dict(value))

    def test_any_version_drift_fails(self):
        expected = self.contract()
        actual = dict(expected, zstd="1.5.6")
        with self.assertRaises(ToolchainError):
            verify_versions(expected, actual)


if __name__ == "__main__":
    unittest.main()
