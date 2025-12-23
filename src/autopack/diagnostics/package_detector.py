"""Package detection and dependency analysis.

Detects missing packages through static analysis and runtime validation.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Dict, Optional
import ast
import sys
import logging
import subprocess

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

    def __init__(self, project_root: Path):
        """Initialize package detector.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = project_root

    def detect_missing_packages(self, scope_paths: Optional[List[str]] = None) -> PackageDetectionResult:
        """Detect missing packages in the project.
        
        Args:
            scope_paths: Optional list of specific paths to analyze
            
        Returns:
            PackageDetectionResult with analysis results
        """
        missing_packages = []
        installed_packages = []
        stdlib_imports = []
        total_imports = 0
        files_analyzed = 0
        errors = []

        # Get Python files to analyze
        if scope_paths:
            python_files = []
            for path_str in scope_paths:
                path = self.project_root / path_str
                if path.is_file() and path.suffix == ".py":
                    python_files.append(path)
                elif path.is_dir():
                    python_files.extend(path.rglob("*.py"))
        else:
            python_files = list(self.project_root.rglob("*.py"))

        # Analyze each file
        for file_path in python_files:
            try:
                imports = self._extract_imports(file_path)
                files_analyzed += 1
                
                for import_name, import_stmt, line_no in imports:
                    total_imports += 1
                    
                    # Check if stdlib
                    if self._is_stdlib(import_name):
                        stdlib_imports.append(import_name)
                        continue
                    
                    # Check if installed
                    if self._is_installed(import_name):
                        installed_packages.append(import_name)
                        continue
                    
                    # Missing package
                    suggested_package = self.PACKAGE_MAPPINGS.get(import_name, import_name)
                    missing_packages.append(PackageRequirement(
                        name=import_name,
                        import_statement=import_stmt,
                        file_path=str(file_path.relative_to(self.project_root)),
                        line_number=line_no,
                        is_stdlib=False,
                        is_installed=False,
                        suggested_package=suggested_package
                    ))
                    
            except Exception as e:
                errors.append(f"Error analyzing {file_path}: {e}")
                logger.warning(f"Failed to analyze {file_path}: {e}")

        return PackageDetectionResult(
            missing_packages=missing_packages,
            installed_packages=list(set(installed_packages)),
            stdlib_imports=list(set(stdlib_imports)),
            total_imports=total_imports,
            files_analyzed=files_analyzed,
            errors=errors
        )

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
                    if node.module:
                        import_name = node.module.split(".")[0]
                        import_stmt = f"from {node.module} import ..."
                        imports.append((import_name, import_stmt, node.lineno))
                        
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
