"""Unit tests for security audit module."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from hestia.audit import SecurityAuditor
from hestia.audit.checks import AuditFinding, AuditReport
from hestia.config import HestiaConfig
from hestia.tools.capabilities import NETWORK_EGRESS, SHELL_EXEC


class TestAuditFinding:
    """Tests for AuditFinding dataclass."""

    def test_create_finding(self):
        """Test creating an audit finding."""
        finding = AuditFinding(
            severity="critical",
            category="config",
            message="Test message",
            details={"key": "value"},
        )
        assert finding.severity == "critical"
        assert finding.category == "config"
        assert finding.message == "Test message"
        assert finding.details == {"key": "value"}


class TestAuditReport:
    """Tests for AuditReport dataclass."""

    def test_create_empty_report(self):
        """Test creating an empty audit report."""
        report = AuditReport()
        assert report.findings == []
        assert report.tool_capabilities == {}
        assert report.session_tool_map == {}

    def test_add_finding(self):
        """Test adding a finding to the report."""
        report = AuditReport()
        report.add_finding("critical", "config", "Test message", {"key": "value"})

        assert len(report.findings) == 1
        assert report.findings[0].severity == "critical"
        assert report.findings[0].category == "config"

    def test_add_finding_without_details(self):
        """Test adding a finding without details."""
        report = AuditReport()
        report.add_finding("info", "test", "Simple message")

        assert len(report.findings) == 1
        assert report.findings[0].details == {}

    def test_to_dict(self):
        """Test converting report to dictionary."""
        report = AuditReport()
        report.add_finding("warning", "sandbox", "Test warning")
        report.tool_capabilities = {"tool1": ["cap1"]}

        data = report.to_dict()
        assert data["findings"][0]["severity"] == "warning"
        assert data["tool_capabilities"] == {"tool1": ["cap1"]}

    def test_to_json(self):
        """Test converting report to JSON."""
        report = AuditReport()
        report.add_finding("info", "test", "Test info")

        json_str = report.to_json()
        data = json.loads(json_str)
        assert data["findings"][0]["message"] == "Test info"

    def test_summary_contains_findings(self):
        """Test that summary contains finding information."""
        report = AuditReport()
        report.add_finding("critical", "config", "Critical issue")
        report.add_finding("warning", "sandbox", "Warning issue")
        report.add_finding("info", "test", "Info message")

        summary = report.summary()
        assert "CRITICAL FINDINGS" in summary
        assert "Critical issue" in summary
        assert "WARNINGS" in summary
        assert "Warning issue" in summary
        assert "INFO" in summary
        assert "Info message" in summary

    def test_summary_counts(self):
        """Test that summary shows correct counts."""
        report = AuditReport()
        report.add_finding("critical", "test", "c1")
        report.add_finding("critical", "test", "c2")
        report.add_finding("warning", "test", "w1")
        report.add_finding("info", "test", "i1")

        summary = report.summary()
        assert "2 critical, 1 warning, 1 info" in summary


class TestSecurityAuditor:
    """Tests for SecurityAuditor class."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return HestiaConfig.default()

    @pytest.fixture
    def mock_tool_registry(self):
        """Create a mock tool registry."""
        registry = MagicMock()
        registry.list_names.return_value = ["tool1", "tool2", "terminal"]

        # Mock tool metadata
        def describe(name):
            meta = MagicMock()
            if name == "terminal":
                meta.capabilities = [SHELL_EXEC]
            elif name == "tool1":
                meta.capabilities = [NETWORK_EGRESS]
            else:
                meta.capabilities = []
            return meta

        registry.describe = describe
        return registry

    @pytest.fixture
    def mock_trace_store(self):
        """Create a mock trace store."""
        store = AsyncMock()
        store.list_recent.return_value = []
        return store

    @pytest.mark.asyncio
    async def test_run_audit_without_dependencies(self, config):
        """Test running audit without tool registry or trace store."""
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        assert isinstance(report, AuditReport)
        # Should have info findings about missing dependencies
        info_findings = [f for f in report.findings if f.severity == "info"]
        assert len(info_findings) > 0

    @pytest.mark.asyncio
    async def test_capability_check_flags_dangerous_combo(
        self, config, mock_tool_registry
    ):
        """Test that capability check flags shell_exec + network_egress."""
        # Create a mock tool with both dangerous capabilities
        def describe_dangerous(name):
            meta = MagicMock()
            if name == "dangerous_tool":
                meta.capabilities = [SHELL_EXEC, NETWORK_EGRESS]
            else:
                meta.capabilities = []
            return meta

        mock_tool_registry.list_names.return_value = ["dangerous_tool", "safe_tool"]
        mock_tool_registry.describe = describe_dangerous

        auditor = SecurityAuditor(config, tool_registry=mock_tool_registry)
        report = await auditor.run_audit()

        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) == 1
        assert "dangerous" in critical[0].message.lower()
        assert "shell_exec + network_egress" in str(critical[0].details)

    @pytest.mark.asyncio
    async def test_capability_check_no_dangerous_combo(
        self, config, mock_tool_registry
    ):
        """Test that capability check passes when no dangerous combo exists."""
        # Only terminal has shell_exec, no network_egress on same tool
        auditor = SecurityAuditor(config, tool_registry=mock_tool_registry)
        report = await auditor.run_audit()

        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) == 0

    @pytest.mark.asyncio
    async def test_capability_check_no_registry(self, config):
        """Test capability check handles missing registry."""
        auditor = SecurityAuditor(config, tool_registry=None)
        report = await auditor.run_audit()

        info = [f for f in report.findings if "Tool registry not available" in f.message]
        assert len(info) == 1

    @pytest.mark.asyncio
    async def test_sandbox_check_relative_path_warning(self, config):
        """Test sandbox check warns about relative paths."""
        config.storage.allowed_roots = ["."]
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        warnings = [f for f in report.findings if f.severity == "warning"]
        assert len(warnings) == 1
        assert "Relative path" in warnings[0].message

    @pytest.mark.asyncio
    async def test_sandbox_check_overly_broad_root(self, config):
        """Test sandbox check flags overly broad roots."""
        config.storage.allowed_roots = ["/"]
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        critical = [f for f in report.findings if f.severity == "critical" and "overly broad" in f.message]
        assert len(critical) == 1
        assert "overly broad" in critical[0].message.lower()

    @pytest.mark.asyncio
    async def test_config_check_telegram_empty_allowed_users(self, config):
        """Test config check flags empty allowed_users when bot_token is set."""
        config.telegram.bot_token = "test_token"
        config.telegram.allowed_users = []
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) == 1
        assert "allowed_users" in critical[0].message

    @pytest.mark.asyncio
    async def test_config_check_telegram_no_token(self, config):
        """Test config check reports info when bot_token not set."""
        config.telegram.bot_token = ""
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        info = [f for f in report.findings if "bot_token not set" in f.message]
        assert len(info) == 1

    @pytest.mark.asyncio
    async def test_config_check_matrix_no_token(self, config):
        """Test config check reports info when matrix token not set."""
        config.matrix.access_token = ""
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        info = [f for f in report.findings if "access_token not set" in f.message]
        assert len(info) == 1

    @pytest.mark.asyncio
    async def test_trace_check_no_trace_store(self, config):
        """Test trace check handles missing trace store."""
        auditor = SecurityAuditor(config, trace_store=None)
        report = await auditor.run_audit()

        info = [f for f in report.findings if "Trace store not available" in f.message]
        assert len(info) == 1

    @pytest.mark.asyncio
    async def test_trace_check_empty_traces(self, config, mock_trace_store):
        """Test trace check handles empty trace store."""
        auditor = SecurityAuditor(config, trace_store=mock_trace_store)
        report = await auditor.run_audit()

        info = [f for f in report.findings if "No traces found" in f.message]
        assert len(info) == 1

    @pytest.mark.asyncio
    async def test_trace_check_suspicious_patterns(self, config, mock_trace_store):
        """Test trace check detects suspicious patterns."""
        # Create a mock trace with suspicious pattern
        trace = MagicMock()
        trace.tools_called = ["http_get", "memory_write"]
        mock_trace_store.list_recent.return_value = [trace]

        auditor = SecurityAuditor(config, trace_store=mock_trace_store)
        report = await auditor.run_audit()

        warnings = [f for f in report.findings if f.severity == "warning" and "memory_write" in f.message]
        assert len(warnings) == 1
        assert "memory_write after http_get" in warnings[0].message

    @pytest.mark.asyncio
    async def test_trace_check_excessive_terminal(self, config, mock_trace_store):
        """Test trace check detects excessive terminal calls."""
        trace = MagicMock()
        trace.tools_called = ["terminal", "terminal", "terminal", "terminal"]
        mock_trace_store.list_recent.return_value = [trace]

        auditor = SecurityAuditor(config, trace_store=mock_trace_store)
        report = await auditor.run_audit()

        warnings = [f for f in report.findings if "excessive terminal" in f.message]
        assert len(warnings) == 1

    @pytest.mark.asyncio
    async def test_trace_check_query_error(self, config):
        """Test trace check handles query errors gracefully."""
        trace_store = AsyncMock()
        trace_store.list_recent.side_effect = Exception("DB error")

        auditor = SecurityAuditor(config, trace_store=trace_store)
        report = await auditor.run_audit()

        info = [f for f in report.findings if "Could not query trace store" in f.message]
        assert len(info) == 1


class TestAuditIntegration:
    """Integration tests for audit functionality."""

    @pytest.mark.asyncio
    async def test_full_audit_with_defaults(self):
        """Test full audit with default configuration."""
        config = HestiaConfig.default()
        auditor = SecurityAuditor(config)
        report = await auditor.run_audit()

        # Should produce a valid report
        assert isinstance(report, AuditReport)
        assert len(report.findings) > 0

        # Check that summary is generated without errors
        summary = report.summary()
        assert "SECURITY AUDIT REPORT" in summary
        assert "Findings:" in summary

        # Check that JSON output works
        json_str = report.to_json()
        data = json.loads(json_str)
        assert "findings" in data
