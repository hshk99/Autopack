"""Unit tests for outbound egress validation and SSRF guardrails.

Phase 5: Outbound egress allowlist / SSRF guardrails
Tests for validate_outbound_host and log_outbound_request functions.
"""

import pytest

from autopack.config import settings
from autopack.exceptions import ValidationError
from autopack.utils.egress import log_outbound_request, validate_outbound_host


class TestValidateOutboundHost:
    """Tests for validate_outbound_host function."""

    def test_localhost_always_allowed(self):
        """Localhost and loopback addresses should always be allowed."""
        # Should not raise
        validate_outbound_host("http://localhost:8080/api")
        validate_outbound_host("http://127.0.0.1:8080/api")
        validate_outbound_host("http://127.0.0.100:8080/api")
        validate_outbound_host("http://[::1]:8080/api")

    def test_no_allowlist_permits_all(self, monkeypatch):
        """When no allowlist is configured, all hosts should be allowed."""
        # Clear the allowlist
        monkeypatch.setattr(settings, "allowed_external_hosts", [])

        # Should not raise for any external host
        validate_outbound_host("https://api.anthropic.com/v1/messages")
        validate_outbound_host("https://api.openai.com/v1/chat")
        validate_outbound_host("https://example.com/api")

    def test_allowlist_permits_listed_hosts(self, monkeypatch):
        """Hosts in the allowlist should be permitted."""
        monkeypatch.setattr(
            settings,
            "allowed_external_hosts",
            ["api.anthropic.com", "api.openai.com"],
        )

        # Should not raise for allowed hosts
        validate_outbound_host("https://api.anthropic.com/v1/messages")
        validate_outbound_host("https://api.openai.com/v1/chat")

    def test_allowlist_blocks_unlisted_hosts(self, monkeypatch):
        """Hosts not in the allowlist should be blocked."""
        monkeypatch.setattr(
            settings,
            "allowed_external_hosts",
            ["api.anthropic.com", "api.openai.com"],
        )

        # Should raise ValidationError for disallowed hosts
        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("https://malicious.com/steal-data")

        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("https://example.com/api")

    def test_wildcard_domain_matching(self, monkeypatch):
        """Wildcard patterns like *.domain.com should match subdomains."""
        monkeypatch.setattr(
            settings,
            "allowed_external_hosts",
            ["*.anthropic.com", "api.openai.com"],
        )

        # Should permit hosts matching wildcard pattern
        validate_outbound_host("https://api.anthropic.com/v1/messages")
        validate_outbound_host("https://models.anthropic.com/list")
        validate_outbound_host("https://deep.nested.anthropic.com/test")

        # Should still permit exact matches
        validate_outbound_host("https://api.openai.com/v1/chat")

        # Should block hosts not matching any pattern
        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("https://malicious.anthropic.co/steal")

        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("https://example.com/api")

    def test_cidr_notation_matching(self, monkeypatch):
        """CIDR notation like 192.168.0.0/16 should match IP ranges."""
        monkeypatch.setattr(
            settings,
            "allowed_external_hosts",
            ["192.168.0.0/16", "10.0.0.0/8", "api.anthropic.com"],
        )

        # Should permit IPs within CIDR ranges
        validate_outbound_host("http://192.168.1.1:8080/api")
        validate_outbound_host("http://192.168.255.255:9000/health")
        validate_outbound_host("http://10.0.0.1/service")
        validate_outbound_host("http://10.255.255.255/data")

        # Should block IPs outside CIDR ranges
        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("http://192.169.1.1/api")

        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("http://11.0.0.1/api")

        # Should still support domain names in allowlist
        validate_outbound_host("https://api.anthropic.com/v1/messages")

    def test_cidr_ipv6_matching(self, monkeypatch):
        """CIDR notation should also work with IPv6 addresses."""
        monkeypatch.setattr(
            settings,
            "allowed_external_hosts",
            ["2001:db8::/32"],
        )

        # Should permit IPs within IPv6 CIDR range
        validate_outbound_host("http://[2001:db8::1]:8080/api")
        validate_outbound_host("http://[2001:db8:ffff:ffff:ffff:ffff:ffff:ffff]/health")

        # Should block IPs outside range
        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("http://[2001:db9::1]/api")

    def test_mixed_pattern_allowlist(self, monkeypatch):
        """Allowlist can contain exact matches, wildcards, and CIDR ranges together."""
        monkeypatch.setattr(
            settings,
            "allowed_external_hosts",
            [
                "api.anthropic.com",  # Exact match
                "*.github.com",  # Wildcard (matches *.github.com only)
                "*.githubusercontent.com",  # Wildcard for GitHub user content
                "10.0.0.0/8",  # CIDR
            ],
        )

        # Exact match
        validate_outbound_host("https://api.anthropic.com/v1/messages")

        # Wildcard matches
        validate_outbound_host("https://raw.githubusercontent.com/file.txt")
        validate_outbound_host("https://api.github.com/repos")

        # CIDR match
        validate_outbound_host("http://10.5.20.100:8080/service")

        # Block non-matching
        with pytest.raises(ValidationError, match="blocked by egress allowlist"):
            validate_outbound_host("https://evil.com/steal")

    def test_invalid_url_raises_error(self):
        """Invalid URLs should raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid URL"):
            validate_outbound_host("not-a-valid-url")

        with pytest.raises(ValidationError, match="Invalid URL"):
            validate_outbound_host("://missing-scheme")

    def test_operation_parameter_included_in_logs(self, caplog, monkeypatch):
        """The operation parameter should be included in log messages."""
        monkeypatch.setattr(settings, "allowed_external_hosts", [])

        with caplog.at_level("DEBUG"):
            validate_outbound_host("https://api.anthropic.com/v1/messages", "Claude API call")

        # Check that operation is in the log
        assert "Claude API call" in caplog.text

    def test_blocked_host_logs_warning(self, caplog, monkeypatch):
        """Blocked hosts should log a warning."""
        monkeypatch.setattr(settings, "allowed_external_hosts", ["api.anthropic.com"])

        with caplog.at_level("WARNING"):
            with pytest.raises(ValidationError):
                validate_outbound_host("https://malicious.com/steal", "malicious operation")

        assert "blocked by egress allowlist" in caplog.text
        assert "malicious.com" in caplog.text


class TestLogOutboundRequest:
    """Tests for log_outbound_request function."""

    def test_logs_method_host_and_path(self, caplog):
        """Should log the HTTP method, host, and path."""
        with caplog.at_level("INFO"):
            log_outbound_request("https://api.anthropic.com/v1/messages", "POST", "Claude API call")

        assert "POST" in caplog.text
        assert "api.anthropic.com" in caplog.text
        assert "/v1/messages" in caplog.text
        assert "Claude API call" in caplog.text

    def test_logs_with_default_method(self, caplog):
        """Should use GET as default method if not specified."""
        with caplog.at_level("INFO"):
            log_outbound_request("https://example.com/api")

        assert "GET" in caplog.text
        assert "example.com" in caplog.text

    def test_logs_unknown_operation(self, caplog):
        """Should log 'unknown' if operation is not specified."""
        with caplog.at_level("INFO"):
            log_outbound_request("https://example.com/api", "POST")

        assert "unknown" in caplog.text


class TestConfigurationParsing:
    """Tests for allowed_external_hosts configuration parsing."""

    def test_comma_separated_string_parsed_to_list(self):
        """CSV string should be parsed into a list of hosts."""
        from autopack.config import Settings

        # Test the model validator directly
        values = {"allowed_external_hosts": "api.anthropic.com,api.openai.com,github.com"}
        result = Settings.parse_allowed_hosts(values)

        assert result["allowed_external_hosts"] == [
            "api.anthropic.com",
            "api.openai.com",
            "github.com",
        ]

    def test_empty_string_becomes_empty_list(self):
        """Empty string should become an empty list."""
        from autopack.config import Settings

        values = {"allowed_external_hosts": ""}
        result = Settings.parse_allowed_hosts(values)

        assert result["allowed_external_hosts"] == []

    def test_whitespace_trimmed_from_hosts(self):
        """Whitespace around hostnames should be trimmed."""
        from autopack.config import Settings

        values = {"allowed_external_hosts": " api.anthropic.com , api.openai.com , github.com "}
        result = Settings.parse_allowed_hosts(values)

        assert result["allowed_external_hosts"] == [
            "api.anthropic.com",
            "api.openai.com",
            "github.com",
        ]
