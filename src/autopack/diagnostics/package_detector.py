"""Package detection and dependency analysis.

Detects missing packages through static analysis and runtime validation.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple, Iterable
import ast
import logging
import re
import tomllib

logger = logging.getLogger(__name__)


@dataclass
class PackageRequirement:
    """Represents a package requirement detected in code."""
    name: str
    import_statement: str
    file_path: str
    line_number: int
    is_stdlib: bool
    is_installed: bool
    suggested_package: Optional[str] = None


@dataclass
class PackageDetectionResult:
    """Result of package detection analysis."""
    missing_packages: List[PackageRequirement]
    installed_packages: List[str]
    stdlib_imports: List[str]
    total_imports: int
    files_analyzed: int
    errors: List[str]

    @property
    def has_missing_packages(self) -> bool:
        """Check if any packages are missing."""
        return len(self.missing_packages) > 0

    @property
    def missing_package_names(self) -> Set[str]:
        """Get unique set of missing package names."""
        return {req.suggested_package or req.name for req in self.missing_packages}

    @property
    def coverage_percentage(self) -> float:
        """Calculate percentage of imports that are satisfied."""
        if self.total_imports == 0:
            return 100.0
        satisfied = len(self.installed_packages) + len(self.stdlib_imports)
        return (satisfied / self.total_imports) * 100.0


class PackageDetector:
    """Detects missing packages through static analysis and runtime validation."""

    # Common package name mappings (import name -> package name)
    PACKAGE_MAPPINGS = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "yaml": "PyYAML",
        "jose": "python-jose",
        "multipart": "python-multipart",
        "telegram": "python-telegram-bot",
        "magic": "python-magic",
        "dateutil": "python-dateutil",
        "OpenSSL": "pyOpenSSL",
        "nacl": "PyNaCl",
    }

    # Python standard library modules (comprehensive list)
    STDLIB_MODULES = {
        "__future__",
        "_thread",
        "abc",
        "aifc",
        "argparse",
        "array",
        "ast",
        "asynchat",
        "asyncio",
        "asyncore",
        "atexit",
        "audioop",
        "base64",
        "bdb",
        "binascii",
        "binhex",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cgi",
        "cgitb",
        "chunk",
        "cmath",
        "cmd",
        "code",
        "codecs",
        "codeop",
        "collections",
        "colorsys",
        "compileall",
        "concurrent",
        "configparser",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "cProfile",
        "crypt",
        "csv",
        "ctypes",
        "curses",
        "dataclasses",
        "datetime",
        "dbm",
        "decimal",
        "difflib",
        "dis",
        "distutils",
        "doctest",
        "email",
        "encodings",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "formatter",
        "fractions",
        "ftplib",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "graphlib",
        "grp",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "imaplib",
        "imghdr",
        "imp",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "lib2to3",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "mailbox",
        "mailcap",
        "marshal",
        "math",
        "mimetypes",
        "mmap",
        "modulefinder",
        "msilib",
        "msvcrt",
        "multiprocessing",
        "netrc",
        "nis",
        "nntplib",
        "numbers",
        "operator",
        "optparse",
        "os",
        "ossaudiodev",
        "parser",
        "pathlib",
        "pdb",
        "pickle",
        "pickletools",
        "pipes",
        "pkgutil",
        "platform",
        "plistlib",
        "poplib",
        "posix",
        "posixpath",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "pyclbr",
        "pydoc",
        "queue",
        "quopri",
        "random",
        "re",
        "readline",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "smtpd",
        "smtplib",
        "sndhdr",
        "socket",
        "socketserver",
        "spwd",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "sunau",
        "symbol",
        "symtable",
        "sys",
        "sysconfig",
        "syslog",
        "tabnanny",
        "tarfile",
        "telnetlib",
        "tempfile",
        "termios",
        "test",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "turtle",
        "turtledemo",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uu",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "winreg",
        "winsound",
        "wsgiref",
        "xdrlib",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
    }

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize package detector.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = project_root or Path.cwd()

    # ---------------------------------------------------------------------------------------------
    # Package-file detection API (requirements/pyproject/setup/Pipfile) used by tests
    # ---------------------------------------------------------------------------------------------

    def detect_packages(self, project_dir: str) -> List[str]:
        """Detect declared packages for a project directory by scanning common files."""
        root = Path(project_dir)
        if not root.exists():
            return []

        packages: Set[str] = set()
        visited: Set[Path] = set()

        # requirements*.txt (including nested)
        for req_file in root.rglob("requirements*.txt"):
            packages.update(self._parse_requirements_file(req_file, visited=visited))

        # common include files referenced by -r (base.txt/dev.txt), also scan for *.txt at root
        # only if they are explicitly included, handled by _parse_requirements_file recursion.

        # pyproject.toml (Poetry + PEP 621)
        for pyproject in root.rglob("pyproject.toml"):
            packages.update(self._parse_pyproject_toml(pyproject))

        # setup.py / setup.cfg
        for setup_py in root.rglob("setup.py"):
            packages.update(self._parse_setup_py(setup_py))
        for setup_cfg in root.rglob("setup.cfg"):
            packages.update(self._parse_setup_cfg(setup_cfg))

        # Pipfile
        for pipfile in root.rglob("Pipfile"):
            packages.update(self._parse_pipfile(pipfile))

        # Conda environment files
        for env_file in list(root.rglob("environment.yml")) + list(root.rglob("environment.yaml")):
            packages.update(self._parse_conda_environment(env_file, visited=visited))

        packages.discard("python")
        return sorted({p.lower() for p in packages if p})

    def _parse_requirements_file(self, path: Path, visited: Set[Path]) -> Set[str]:
        path = path.resolve()
        if path in visited or not path.exists():
            return set()
        visited.add(path)

        pkgs: Set[str] = set()
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # strip inline comments
            if " #" in line:
                line = line.split(" #", 1)[0].strip()
            if line.startswith("#"):
                continue

            # include other files
            if line.startswith("-r ") or line.startswith("--requirement "):
                inc = line.split(None, 1)[1].strip()
                inc_path = (path.parent / inc).resolve()
                pkgs.update(self._parse_requirements_file(inc_path, visited=visited))
                continue
            if line.startswith("-c ") or line.startswith("--constraint "):
                # constraints file can also include packages; treat like include for detection.
                inc = line.split(None, 1)[1].strip()
                inc_path = (path.parent / inc).resolve()
                pkgs.update(self._parse_requirements_file(inc_path, visited=visited))
                continue

            # editable installs
            if line.startswith("-e ") or line.startswith("--editable "):
                line = line.split(None, 1)[1].strip()

            pkg = self._extract_package_name_from_requirement(line)
            if pkg:
                pkgs.add(pkg)

        return pkgs

    def _extract_package_name_from_requirement(self, line: str) -> Optional[str]:
        # git urls with egg
        if "#egg=" in line:
            return line.split("#egg=", 1)[1].strip().lower() or None

        # options / unsupported lines
        if line.startswith("-") or line.startswith("@@@") or line.startswith("==="):
            return None

        # environment markers
        if ";" in line:
            line = line.split(";", 1)[0].strip()

        # url deps (ignore unless egg present)
        if "://" in line:
            return None

        # extras
        if "[" in line:
            line = line.split("[", 1)[0].strip()

        # strip version specifiers
        for sep in ["===", "==", ">=", "<=", "~=", "!=", ">", "<"]:
            if sep in line:
                line = line.split(sep, 1)[0].strip()
        # strip direct references like "pkg @ https://..."
        if " @" in line:
            line = line.split(" @", 1)[0].strip()

        if not line:
            return None
        # basic validation: must start with alnum
        if not line[0].isalnum():
            return None
        return line.lower()

    def _parse_pyproject_toml(self, path: Path) -> Set[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        pkgs: Set[str] = set()

        # Prefer tomllib for correctness; fall back to simple parsing for malformed fixtures.
        try:
            data = tomllib.loads(text)
        except Exception:
            data = {}

        # Poetry (including groups):
        # - [tool.poetry.dependencies]
        # - [tool.poetry.dev-dependencies] (legacy)
        # - [tool.poetry.group.<name>.dependencies]
        tool = data.get("tool", {}) if isinstance(data, dict) else {}
        poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
        if isinstance(poetry, dict):
            deps = poetry.get("dependencies", {})
            if isinstance(deps, dict):
                for name in deps.keys():
                    if name and str(name).lower() != "python":
                        pkgs.add(str(name).lower())

            dev_deps = poetry.get("dev-dependencies", {})
            if isinstance(dev_deps, dict):
                for name in dev_deps.keys():
                    if name and str(name).lower() != "python":
                        pkgs.add(str(name).lower())

            groups = poetry.get("group", {})
            if isinstance(groups, dict):
                for _, group_cfg in groups.items():
                    if not isinstance(group_cfg, dict):
                        continue
                    group_deps = group_cfg.get("dependencies", {})
                    if isinstance(group_deps, dict):
                        for name in group_deps.keys():
                            if name and str(name).lower() != "python":
                                pkgs.add(str(name).lower())

        # PEP 621:
        project = data.get("project", {}) if isinstance(data, dict) else {}
        if isinstance(project, dict):
            deps_list = project.get("dependencies", [])
            if isinstance(deps_list, list):
                for item in deps_list:
                    if not isinstance(item, str):
                        continue
                    pkg = self._extract_package_name_from_requirement(item)
                    if pkg:
                        pkgs.add(pkg)

            optional = project.get("optional-dependencies", {})
            if isinstance(optional, dict):
                for _, opt_list in optional.items():
                    if not isinstance(opt_list, list):
                        continue
                    for item in opt_list:
                        if not isinstance(item, str):
                            continue
                        pkg = self._extract_package_name_from_requirement(item)
                        if pkg:
                            pkgs.add(pkg)

        # Fallback: for malformed TOML, keep a very conservative scan of requirement-looking strings.
        if not pkgs and text:
            for m in re.findall(r'"([^"]+)"', text):
                pkg = self._extract_package_name_from_requirement(m)
                if pkg:
                    pkgs.add(pkg)

        return pkgs

    def _parse_setup_py(self, path: Path) -> Set[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        pkgs: Set[str] = set()
        # Grab quoted strings inside install_requires and extras_require blocks (simple test fixtures)
        for m in re.findall(r"install_requires\s*=\s*\[([^\]]*)\]", text, flags=re.DOTALL):
            pkgs.update(self._parse_quoted_list(m))
        for m in re.findall(r"extras_require\s*=\s*\{([^}]*)\}", text, flags=re.DOTALL):
            # Avoid treating extras group names (e.g. "dev") as packages.
            # Parse only values (list literals or string literals) in the dict.
            for list_block in re.findall(r":\s*\[([^\]]*)\]", m, flags=re.DOTALL):
                pkgs.update(self._parse_quoted_list(list_block))
            for str_val in re.findall(r":\s*['\"]([^'\"]+)['\"]", m):
                pkg = self._extract_package_name_from_requirement(str_val)
                if pkg:
                    pkgs.add(pkg)
        return pkgs

    def _parse_setup_cfg(self, path: Path) -> Set[str]:
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")
        pkgs: Set[str] = set()

        if cfg.has_option("options", "install_requires"):
            pkgs.update(self._parse_lines_as_requirements(cfg.get("options", "install_requires")))

        # extras
        if cfg.has_section("options.extras_require"):
            for _, v in cfg.items("options.extras_require"):
                pkgs.update(self._parse_lines_as_requirements(v))

        return pkgs

    def _parse_pipfile(self, path: Path) -> Set[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        pkgs: Set[str] = set()
        section = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line
                continue
            if section in ("[packages]", "[dev-packages]") and "=" in line:
                name = line.split("=", 1)[0].strip().strip('"').strip("'")
                if name:
                    pkgs.add(name.lower())
        return pkgs

    def _parse_conda_environment(self, path: Path, visited: Set[Path]) -> Set[str]:
        # Minimal YAML-ish parsing to avoid a hard dependency on PyYAML for tests.
        text = path.read_text(encoding="utf-8", errors="ignore")
        pkgs: Set[str] = set()
        in_deps = False
        in_pip = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("dependencies:"):
                in_deps = True
                in_pip = False
                continue
            if not in_deps:
                continue
            if line.startswith("- pip:"):
                in_pip = True
                continue
            if line.startswith("- "):
                item = line[2:].strip()
                if in_pip:
                    pkg = self._extract_package_name_from_requirement(item)
                    if pkg:
                        pkgs.add(pkg)
                else:
                    # conda dep like "python=3.11" or "pandas>=1.3.0" or "numpy"
                    pkg = self._extract_package_name_from_requirement(item)
                    if pkg and pkg.lower() != "python":
                        pkgs.add(pkg.lower())
        return pkgs

    def _parse_quoted_list(self, block: str) -> Set[str]:
        pkgs: Set[str] = set()
        for s in re.findall(r"['\"]([^'\"]+)['\"]", block):
            pkg = self._extract_package_name_from_requirement(s)
            if pkg:
                pkgs.add(pkg)
        return pkgs

    def _parse_lines_as_requirements(self, block: str) -> Set[str]:
        pkgs: Set[str] = set()
        for raw in block.splitlines():
            pkg = self._extract_package_name_from_requirement(raw.strip())
            if pkg:
                pkgs.add(pkg)
        return pkgs

    # ---------------------------------------------------------------------------------------------
    # Import-based missing-package detection API (used by tests/autopack/diagnostics/test_package_detector.py)
    # ---------------------------------------------------------------------------------------------

    def _is_stdlib_module(self, module_name: str) -> bool:
        return self._is_stdlib(module_name)

    def check_import(self, module_name: str) -> Tuple[bool, Optional[str]]:
        if self._is_stdlib_module(module_name):
            return True, None
        if self._is_installed(module_name):
            return True, None
        return False, self.PACKAGE_MAPPINGS.get(module_name, module_name)

    def _create_requirement(self, module_name: str, import_stmt: str, file_path: Path, line_number: int) -> PackageRequirement:
        is_stdlib = self._is_stdlib_module(module_name)
        is_installed = True if is_stdlib else self._is_installed(module_name)
        suggested = None
        if not is_stdlib and not is_installed:
            suggested = self.PACKAGE_MAPPINGS.get(module_name, module_name)
        return PackageRequirement(
            name=module_name,
            import_statement=import_stmt,
            file_path=str(file_path),
            line_number=line_number,
            is_stdlib=is_stdlib,
            is_installed=is_installed,
            suggested_package=suggested,
        )

    def _analyze_file(self, file_path: Path) -> List[PackageRequirement]:
        imports = self._extract_imports(file_path)
        return [self._create_requirement(name, stmt, file_path, line_no) for name, stmt, line_no in imports]

    def analyze_files(self, files: Iterable[Path]) -> PackageDetectionResult:
        missing: List[PackageRequirement] = []
        installed: List[str] = []
        stdlib: List[str] = []
        errors: List[str] = []
        total_imports = 0
        files_analyzed = 0

        for f in files:
            if not Path(f).exists():
                errors.append(f"File not found: {f}")
                continue
            reqs = self._analyze_file(Path(f))
            files_analyzed += 1
            total_imports += len(reqs)
            for r in reqs:
                if r.is_stdlib:
                    stdlib.append(r.name)
                elif r.is_installed:
                    installed.append(r.name)
                else:
                    missing.append(r)

        return PackageDetectionResult(
            missing_packages=missing,
            installed_packages=installed,
            stdlib_imports=stdlib,
            total_imports=total_imports,
            files_analyzed=files_analyzed,
            errors=errors,
        )

    def analyze_directory(self, exclude_patterns: Optional[List[str]] = None) -> PackageDetectionResult:
        exclude_patterns = exclude_patterns or []
        python_files = list(self.project_root.rglob("*.py"))
        if exclude_patterns:
            filtered: List[Path] = []
            for p in python_files:
                rel = str(p.relative_to(self.project_root)).replace("\\", "/")
                if any(Path(rel).match(pattern) for pattern in exclude_patterns):
                    continue
                filtered.append(p)
            python_files = filtered
        return self.analyze_files(python_files)

    def get_missing_packages_summary(self, result: PackageDetectionResult) -> str:
        if not result.missing_packages:
            return "All required packages are installed ✅"

        # group by package name
        grouped: Dict[str, List[PackageRequirement]] = {}
        for req in result.missing_packages:
            name = (req.suggested_package or req.name).lower()
            grouped.setdefault(name, []).append(req)

        lines: List[str] = ["Missing packages detected:"]
        for name in sorted(grouped.keys()):
            reqs = grouped[name]
            count = len(reqs)
            lines.append(f"- {name} ({count} location(s))")
            if count > 1:
                shown = reqs[:3]
                for r in shown:
                    lines.append(f"  - {r.file_path}:{r.line_number}")
                if count > 3:
                    lines.append(f"  - and {count - 3} more")
        lines.append("")
        lines.append("Install with:")
        lines.append(f"pip install {' '.join(sorted(grouped.keys()))}")
        return "\n".join(lines)

    def _extract_imports(self, file_path: Path) -> List[tuple]:
        """Extract import statements from a Python file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            List of (import_name, import_statement, line_number) tuples
        """
        imports = []
        
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_name = alias.name.split(".")[0]
                        import_stmt = f"import {alias.name}"
                        imports.append((import_name, import_stmt, node.lineno))
                        
                elif isinstance(node, ast.ImportFrom):
                    # Skip relative imports (e.g. from . import x, from ..pkg import y)
                    if getattr(node, "level", 0):
                        continue
                    if node.module:
                        import_name = node.module.split(".")[0]
                        import_stmt = f"from {node.module} import ..."
                        imports.append((import_name, import_stmt, node.lineno))
                        
        except SyntaxError:
            # Tests expect syntax errors to be handled gracefully.
            return []
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            
        return imports

    def _is_stdlib(self, module_name: str) -> bool:
        """Check if a module is part of the standard library.
        
        Args:
            module_name: Name of the module
            
        Returns:
            True if module is in stdlib
        """
        return module_name in self.STDLIB_MODULES

    def _is_installed(self, module_name: str) -> bool:
        """Check if a module is installed.
        
        Args:
            module_name: Name of the module
            
        Returns:
            True if module is installed
        """
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    def get_install_command(self, result: PackageDetectionResult) -> Optional[str]:
        """Generate pip install command for missing packages.
        
        Args:
            result: Package detection result
            
        Returns:
            pip install command or None if no packages missing
        """
        if not result.missing_packages:
            return None
            
        packages = sorted(result.missing_package_names)
        return f"pip install {' '.join(packages)}"

    def validate_requirements_file(self, requirements_path: Path) -> Dict[str, bool]:
        """Validate that all packages in requirements.txt are installed.
        
        Args:
            requirements_path: Path to requirements.txt
            
        Returns:
            Dict mapping package names to installation status
        """
        validation = {}
        
        if not requirements_path.exists():
            return validation
            
        try:
            content = requirements_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                # Extract package name (before ==, >=, etc.)
                package_name = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
                validation[package_name] = self._is_installed(package_name)
                
        except Exception as e:
            logger.warning(f"Failed to validate requirements file: {e}")
            
        return validation


# -------------------------------------------------------------------------------------------------
# Module-level convenience API expected by unit tests
# -------------------------------------------------------------------------------------------------


def detect_missing_packages(
    paths: Optional[List[Path]] = None,
    directory: Optional[Path] = None,
) -> PackageDetectionResult:
    """Detect missing packages from imports in files or a directory."""
    if paths:
        root = directory or (paths[0].parent if paths else Path.cwd())
        detector = PackageDetector(project_root=root)
        return detector.analyze_files(paths)
    detector = PackageDetector(project_root=directory or Path.cwd())
    return detector.analyze_directory()
