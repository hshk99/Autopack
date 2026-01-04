"""Edge case tests for package detector"""

import pytest

from autopack.diagnostics.package_detector import PackageDetector
from tests.autopack.diagnostics.fixtures.package_scenarios import (
    EDGE_CASE_SCENARIOS,
    NO_PACKAGES_SCENARIOS,
)


class TestPackageDetectorEdgeCases:
    """Edge case tests for PackageDetector"""

    def test_empty_requirements_file(self, temp_project_dir):
        """Test handling of empty requirements.txt"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert len(packages) == 0

    def test_comments_only_requirements(self, temp_project_dir):
        """Test requirements file with only comments"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """# This is a comment
# Another comment

# More comments
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert len(packages) == 0

    def test_comments_and_whitespace(self, temp_project_dir):
        """Test requirements with comments and excessive whitespace"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """# This is a comment
requests==2.28.0

# Another comment
numpy  # inline comment


pandas>=1.0.0  # trailing comment
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages
        assert len(packages) == 3

    def test_git_urls(self, temp_project_dir):
        """Test handling of git URLs in requirements"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """git+https://github.com/user/repo.git@v1.0#egg=mypackage
git+ssh://git@github.com/user/another.git#egg=anotherpackage
requests==2.28.0
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should extract package names from egg= parameter
        assert "mypackage" in packages
        assert "anotherpackage" in packages
        assert "requests" in packages

    def test_editable_installs(self, temp_project_dir):
        """Test handling of editable installs with -e flag"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            "-e ./local-package\n-e git+https://github.com/user/repo.git#egg=remote-pkg\nrequests\n"
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should extract package from git URL with egg=
        assert "remote-pkg" in packages
        assert "requests" in packages

    def test_complex_version_specifiers(self, temp_project_dir):
        """Test various complex version specifiers"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """package1>=1.0.0,<2.0.0
package2~=1.4.2
package3===1.0.0
package4!=1.5.0
package5>=1.0.0,!=1.2.0,<2.0.0
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "package1" in packages
        assert "package2" in packages
        assert "package3" in packages
        assert "package4" in packages
        assert "package5" in packages

    def test_extras(self, temp_project_dir):
        """Test packages with extras"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("requests[security,socks]\ndjango[argon2]>=3.0\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should extract base package name without extras
        assert "requests" in packages
        assert "django" in packages
        # Extras should not be separate packages
        assert "security" not in packages
        assert "socks" not in packages
        assert "argon2" not in packages

    def test_environment_markers(self, temp_project_dir):
        """Test packages with environment markers"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """requests==2.28.0
pywin32>=1.0; sys_platform == 'win32'
uvloop; platform_system != 'Windows'
colorama; os_name == 'nt'
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect all packages regardless of environment markers
        assert "requests" in packages
        assert "pywin32" in packages
        assert "uvloop" in packages
        assert "colorama" in packages

    def test_malformed_lines(self, temp_project_dir):
        """Test handling of malformed lines in requirements"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """requests==2.28.0
===invalid===
numpy
@@@malformed@@@
pandas>=1.0.0
!!!
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should skip malformed lines but detect valid ones
        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages
        # Malformed entries should not be included
        assert "invalid" not in packages
        assert "malformed" not in packages

    def test_url_dependencies(self, temp_project_dir):
        """Test handling of URL-based dependencies"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """https://github.com/user/repo/archive/master.zip
https://files.pythonhosted.org/packages/.../package-1.0.tar.gz
requests==2.28.0
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect regular packages, URLs might be skipped or extracted
        assert "requests" in packages

    def test_options_and_flags(self, temp_project_dir):
        """Test handling of pip options and flags"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """--index-url https://pypi.org/simple
--extra-index-url https://custom.pypi.org/simple
--trusted-host custom.pypi.org
requests==2.28.0
-i https://another.index.org/simple
numpy
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should skip option lines and detect packages
        assert "requests" in packages
        assert "numpy" in packages
        # Options should not be treated as packages
        assert len([p for p in packages if "index" in p.lower()]) == 0

    def test_constraints_file(self, temp_project_dir):
        """Test handling of constraints file reference"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("-c constraints.txt\nrequests\nnumpy\n")

        constraints_file = temp_project_dir / "constraints.txt"
        constraints_file.write_text("requests==2.28.0\nnumpy==1.20.0\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from main requirements
        assert "requests" in packages
        assert "numpy" in packages

    def test_unicode_and_special_characters(self, temp_project_dir):
        """Test handling of unicode and special characters"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text(
            """# Comment with unicode: 你好
requests==2.28.0  # Comment with emoji: 🚀
numpy
""",
            encoding="utf-8",
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "numpy" in packages

    def test_very_long_lines(self, temp_project_dir):
        """Test handling of very long lines"""
        req_file = temp_project_dir / "requirements.txt"
        long_comment = "# " + "x" * 10000
        req_file.write_text(f"{long_comment}\nrequests\nnumpy\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "numpy" in packages

    def test_mixed_line_endings(self, temp_project_dir):
        """Test handling of mixed line endings (CRLF and LF)"""
        req_file = temp_project_dir / "requirements.txt"
        # Mix of \r\n and \n
        content = "requests==2.28.0\r\nnumpy\npandas\r\n"
        req_file.write_bytes(content.encode())

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages

    @pytest.mark.parametrize("scenario", EDGE_CASE_SCENARIOS, ids=lambda s: s.name)
    def test_edge_case_scenarios(self, scenario, create_scenario):
        """Test all edge case scenarios"""
        project_dir = create_scenario(scenario)

        detector = PackageDetector()
        packages = detector.detect_packages(str(project_dir))

        detected = set(packages)
        expected = set(scenario.expected_packages)

        assert detected == expected, (
            f"Scenario '{scenario.name}' failed: "
            f"expected {expected}, got {detected}. "
            f"Missing: {expected - detected}, Extra: {detected - expected}"
        )

    @pytest.mark.parametrize("scenario", NO_PACKAGES_SCENARIOS, ids=lambda s: s.name)
    def test_no_packages_scenarios(self, scenario, create_scenario):
        """Test scenarios where no packages should be detected"""
        project_dir = create_scenario(scenario)

        detector = PackageDetector()
        packages = detector.detect_packages(str(project_dir))

        assert len(packages) == 0, f"Expected no packages but got: {packages}"

    def test_corrupted_toml_file(self, temp_project_dir):
        """Test handling of corrupted TOML file"""
        pyproject = temp_project_dir / "pyproject.toml"
        pyproject.write_text(
            """[tool.poetry
this is not valid toml
[[[broken
"""
        )

        detector = PackageDetector()
        # Should not crash, just return empty or skip the file
        packages = detector.detect_packages(str(temp_project_dir))

        # Should handle gracefully
        assert isinstance(packages, list)

    def test_corrupted_setup_py(self, temp_project_dir):
        """Test handling of corrupted setup.py"""
        setup_file = temp_project_dir / "setup.py"
        setup_file.write_text(
            """from setuptools import setup

setup(
    name='test',
    install_requires=[
        'flask',
        # Missing closing bracket
)
"""
        )

        detector = PackageDetector()
        # Should not crash
        packages = detector.detect_packages(str(temp_project_dir))

        assert isinstance(packages, list)

    def test_permission_denied(self, temp_project_dir):
        """Test handling of permission denied errors"""
        import os
        import stat

        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("requests\n")

        # Make file unreadable (skip on Windows where this doesn't work the same)
        if os.name != "nt":
            os.chmod(req_file, 0o000)

            try:
                detector = PackageDetector()
                packages = detector.detect_packages(str(temp_project_dir))

                # Should handle gracefully
                assert isinstance(packages, list)
            finally:
                # Restore permissions for cleanup
                os.chmod(req_file, stat.S_IRUSR | stat.S_IWUSR)

    def test_symlink_handling(self, temp_project_dir):
        """Test handling of symlinked files"""
        import os

        # Create actual requirements file
        actual_req = temp_project_dir / "actual_requirements.txt"
        actual_req.write_text("requests\nnumpy\n")

        # Create symlink (skip on Windows if not supported)
        symlink_req = temp_project_dir / "requirements.txt"
        try:
            os.symlink(actual_req, symlink_req)

            detector = PackageDetector()
            packages = detector.detect_packages(str(temp_project_dir))

            assert "requests" in packages
            assert "numpy" in packages
        except (OSError, NotImplementedError):
            # Symlinks not supported on this platform
            pytest.skip("Symlinks not supported on this platform")
