"""
Contract tests for PatchPolicy enforcement.

Tests the policy validation logic independently of GovernedApplyPath,
ensuring correct enforcement of:
- Protected path restrictions
- Allowed path overrides
- Scope constraints
- Internal mode behavior
- Path normalization (Windows/POSIX)
"""


from autopack.patching.policy import PatchPolicy, ValidationResult


def test_protected_path_rejection():
    """Protected paths should be blocked."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/", "config/"],
        allowed_paths=[],
        scope_paths=None,
        internal_mode=False,
    )

    result = policy.validate_paths(["src/autopack/main.py"])
    assert not result.valid
    assert len(result.violations) == 1
    assert "Protected path: src/autopack/main.py" in result.violations
    assert "src/autopack/main.py" in result.blocked_files


def test_allowed_path_acceptance():
    """Allowed paths should override protection."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=["src/autopack/research/"],
        scope_paths=None,
        internal_mode=False,
    )

    # Protected path should be blocked
    result = policy.validate_paths(["src/autopack/main.py"])
    assert not result.valid

    # Allowed path should pass
    result = policy.validate_paths(["src/autopack/research/gatherer.py"])
    assert result.valid
    assert len(result.violations) == 0


def test_scope_constraint_enforcement():
    """Only files within scope should be allowed."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=["src/autopack/research/"],
        scope_paths=["src/project/module.py", "tests/"],
        internal_mode=False,
    )

    # File within scope should pass
    result = policy.validate_paths(["src/project/module.py"])
    assert result.valid

    # Directory prefix within scope should pass
    result = policy.validate_paths(["tests/test_foo.py"])
    assert result.valid

    # File outside scope should fail
    result = policy.validate_paths(["src/other/file.py"])
    assert not result.valid
    assert "Outside scope: src/other/file.py" in result.violations


def test_internal_mode_bypasses_restrictions():
    """Internal mode flag is stored but actual bypass logic is in GovernedApplyPath.

    The PatchPolicy object stores internal_mode for future use, but the actual
    unlocking of src/autopack/ happens in GovernedApplyPath.__init__ by filtering
    the protected_paths list before passing it to PatchPolicy.
    """
    # In internal mode, GovernedApplyPath would filter protected_paths before creating policy
    policy_internal = PatchPolicy(
        protected_paths=[  # src/autopack/ removed by GovernedApplyPath
            "src/autopack/config.py",  # Critical paths remain
            ".git/",
        ],
        allowed_paths=["src/autopack/research/"],
        scope_paths=None,
        internal_mode=True,
    )

    # Core autopack files (not in critical list) would now pass
    result = policy_internal.validate_paths(["src/autopack/llm_service.py"])
    assert result.valid

    # Critical paths still protected
    result = policy_internal.validate_paths(["src/autopack/config.py"])
    assert not result.valid


def test_wildcard_patterns_in_path_lists():
    """Path matching uses prefix matching, not wildcards."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=["src/autopack/research/"],
        scope_paths=None,
        internal_mode=False,
    )

    # Prefix matching should work
    result = policy.validate_paths(["src/autopack/research/subfolder/file.py"])
    assert result.valid


def test_case_sensitivity_handling():
    """Path matching should be case-sensitive."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=[],
        scope_paths=None,
        internal_mode=False,
    )

    # Exact case should match
    result = policy.validate_paths(["src/autopack/main.py"])
    assert not result.valid

    # Different case should not match (case-sensitive)
    result = policy.validate_paths(["src/Autopack/main.py"])
    assert result.valid  # Not protected due to case difference


def test_is_path_protected():
    """Test individual path protection checks."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/", ".git/"],
        allowed_paths=["src/autopack/research/"],
        scope_paths=None,
        internal_mode=False,
    )

    # Protected paths
    assert policy.is_path_protected("src/autopack/main.py")
    assert policy.is_path_protected(".git/config")

    # Allowed path (overrides protection)
    assert not policy.is_path_protected("src/autopack/research/file.py")

    # Unprotected paths
    assert not policy.is_path_protected("src/project/file.py")
    assert not policy.is_path_protected("README.md")


def test_is_path_allowed():
    """Test individual allowed path checks."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=["src/autopack/research/", "config/models.yaml"],
        scope_paths=None,
        internal_mode=False,
    )

    # Allowed paths
    assert policy.is_path_allowed("src/autopack/research/file.py")
    assert policy.is_path_allowed("config/models.yaml")

    # Not allowed
    assert not policy.is_path_allowed("src/autopack/main.py")
    assert not policy.is_path_allowed("README.md")


def test_is_within_scope():
    """Test individual scope checks."""
    # No scope configured - everything in scope
    policy_no_scope = PatchPolicy(
        protected_paths=[],
        allowed_paths=[],
        scope_paths=None,
        internal_mode=False,
    )
    assert policy_no_scope.is_within_scope("any/file.py")

    # With scope configured
    policy = PatchPolicy(
        protected_paths=[],
        allowed_paths=[],
        scope_paths=["src/project/", "tests/test_foo.py"],
        internal_mode=False,
    )

    # Within scope
    assert policy.is_within_scope("src/project/module.py")
    assert policy.is_within_scope("tests/test_foo.py")

    # Outside scope
    assert not policy.is_within_scope("src/other/file.py")
    assert not policy.is_within_scope("tests/test_bar.py")


def test_path_normalization_windows_style():
    """Scope enforcement must handle Windows-style backslashes."""
    policy = PatchPolicy(
        protected_paths=[],
        allowed_paths=[],
        scope_paths=["src\\project\\module.py", "tests\\"],
        internal_mode=False,
    )

    # POSIX-style paths in patches should match Windows-style scope
    result = policy.validate_paths(["src/project/module.py"])
    assert result.valid

    result = policy.validate_paths(["tests/test_foo.py"])
    assert result.valid

    result = policy.validate_paths(["other/file.py"])
    assert not result.valid


def test_path_normalization_leading_dot_slash():
    """Scope enforcement must handle leading ./ prefixes."""
    policy = PatchPolicy(
        protected_paths=[],
        allowed_paths=[],
        scope_paths=["./src/project/module.py", "./tests/"],
        internal_mode=False,
    )

    # Paths without leading ./ should match
    result = policy.validate_paths(["src/project/module.py"])
    assert result.valid

    result = policy.validate_paths(["tests/test_foo.py"])
    assert result.valid


def test_multiple_violations():
    """Multiple policy violations should all be reported."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=[],
        scope_paths=["src/project/"],
        internal_mode=False,
    )

    result = policy.validate_paths([
        "src/autopack/main.py",  # Protected AND outside scope
        "src/other/file.py",      # Outside scope
        "src/project/ok.py",      # OK
    ])

    assert not result.valid
    # src/autopack/main.py violates both protected path and scope
    # src/other/file.py violates scope
    assert len(result.violations) == 3
    assert "Protected path: src/autopack/main.py" in result.violations
    assert "Outside scope: src/autopack/main.py" in result.violations
    assert "Outside scope: src/other/file.py" in result.violations
    assert len(result.blocked_files) == 2  # Only 2 unique files blocked


def test_validation_result_boolean_context():
    """ValidationResult should be usable in boolean context."""
    valid_result = ValidationResult(valid=True, violations=[], blocked_files=[])
    assert valid_result  # Should be truthy

    invalid_result = ValidationResult(valid=False, violations=["error"], blocked_files=["file.py"])
    assert not invalid_result  # Should be falsy


def test_empty_file_list():
    """Empty file list should pass validation."""
    policy = PatchPolicy(
        protected_paths=["src/autopack/"],
        allowed_paths=[],
        scope_paths=None,
        internal_mode=False,
    )

    result = policy.validate_paths([])
    assert result.valid
    assert len(result.violations) == 0


def test_scope_directory_prefix_vs_file():
    """Scope should distinguish between directory prefixes and exact files."""
    policy = PatchPolicy(
        protected_paths=[],
        allowed_paths=[],
        scope_paths=["src/project/", "tests/test_specific.py"],
        internal_mode=False,
    )

    # Directory prefix - any file under it should match
    result = policy.validate_paths(["src/project/subdir/file.py"])
    assert result.valid

    # Exact file match
    result = policy.validate_paths(["tests/test_specific.py"])
    assert result.valid

    # Similar file name but not exact match
    result = policy.validate_paths(["tests/test_specific_other.py"])
    assert not result.valid


def test_protected_and_allowed_both_apply():
    """When a path is both protected and allowed, allowed should win."""
    policy = PatchPolicy(
        protected_paths=["src/"],
        allowed_paths=["src/exceptions/"],
        scope_paths=None,
        internal_mode=False,
    )

    # Protected but not allowed
    result = policy.validate_paths(["src/main.py"])
    assert not result.valid

    # Protected but allowed wins
    result = policy.validate_paths(["src/exceptions/custom.py"])
    assert result.valid
