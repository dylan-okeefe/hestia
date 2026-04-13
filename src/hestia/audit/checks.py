"""Security audit checks for Hestia.

Implements deterministic security checks as specified in Phase 13.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.tools.capabilities import NETWORK_EGRESS, SHELL_EXEC
from hestia.tools.registry import ToolNotFoundError

if TYPE_CHECKING:
    from hestia.config import HestiaConfig
    from hestia.persistence.trace_store import TraceStore
    from hestia.tools.registry import ToolRegistry


@dataclass
class AuditFinding:
    """A single security finding."""

    severity: str  # "info", "warning", "critical"
    category: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    """Complete security audit report."""

    findings: list[AuditFinding] = field(default_factory=list)
    tool_capabilities: dict[str, list[str]] = field(default_factory=dict)
    session_tool_map: dict[str, list[str]] = field(default_factory=dict)
    allowed_roots: list[str] = field(default_factory=list)
    config_issues: list[str] = field(default_factory=list)
    dependency_issues: list[str] = field(default_factory=list)
    trace_issues: list[str] = field(default_factory=list)

    def add_finding(
        self,
        severity: str,
        category: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(
            AuditFinding(
                severity=severity,
                category=category,
                message=message,
                details=details or {},
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                    "details": f.details,
                }
                for f in self.findings
            ],
            "tool_capabilities": self.tool_capabilities,
            "session_tool_map": self.session_tool_map,
            "allowed_roots": self.allowed_roots,
            "config_issues": self.config_issues,
            "dependency_issues": self.dependency_issues,
            "trace_issues": self.trace_issues,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = []
        lines.append("=" * 60)
        lines.append("HESTIA SECURITY AUDIT REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Count by severity
        critical = sum(1 for f in self.findings if f.severity == "critical")
        warnings = sum(1 for f in self.findings if f.severity == "warning")
        info = sum(1 for f in self.findings if f.severity == "info")

        lines.append(f"Findings: {critical} critical, {warnings} warning, {info} info")
        lines.append("")

        # Tool capabilities
        if self.tool_capabilities:
            lines.append("-" * 40)
            lines.append("TOOL CAPABILITIES")
            lines.append("-" * 40)
            for tool, caps in sorted(self.tool_capabilities.items()):
                caps_str = ", ".join(caps) if caps else "none"
                lines.append(f"  {tool}: {caps_str}")
            lines.append("")

        # Session tool mapping
        if self.session_tool_map:
            lines.append("-" * 40)
            lines.append("TOOLS BY SESSION TYPE")
            lines.append("-" * 40)
            for session_type, tools in sorted(self.session_tool_map.items()):
                lines.append(f"  {session_type}: {len(tools)} tools")
                for tool in sorted(tools):
                    lines.append(f"    - {tool}")
            lines.append("")

        # Critical findings
        critical_findings = [f for f in self.findings if f.severity == "critical"]
        if critical_findings:
            lines.append("-" * 40)
            lines.append("CRITICAL FINDINGS")
            lines.append("-" * 40)
            for f in critical_findings:
                lines.append(f"  [{f.category}] {f.message}")
                if f.details:
                    for key, value in f.details.items():
                        lines.append(f"    {key}: {value}")
            lines.append("")

        # Warnings
        warnings_list = [f for f in self.findings if f.severity == "warning"]
        if warnings_list:
            lines.append("-" * 40)
            lines.append("WARNINGS")
            lines.append("-" * 40)
            for f in warnings_list:
                lines.append(f"  [{f.category}] {f.message}")
            lines.append("")

        # Info
        info_list = [f for f in self.findings if f.severity == "info"]
        if info_list:
            lines.append("-" * 40)
            lines.append("INFO")
            lines.append("-" * 40)
            for f in info_list:
                lines.append(f"  [{f.category}] {f.message}")
            lines.append("")

        return "\n".join(lines)


class SecurityAuditor:
    """Runs security audits on Hestia configuration and deployment."""

    def __init__(
        self,
        config: HestiaConfig,
        tool_registry: ToolRegistry | None = None,
        trace_store: TraceStore | None = None,
    ):
        """Initialize the security auditor.

        Args:
            config: Hestia configuration to audit
            tool_registry: Optional tool registry for capability checks
            trace_store: Optional trace store for trace-based checks
        """
        self.config = config
        self.tool_registry = tool_registry
        self.trace_store = trace_store

    async def run_audit(self) -> AuditReport:
        """Run all security audits and return the report."""
        report = AuditReport()

        # Run all audit checks
        await self._check_capabilities(report)
        await self._check_sandbox(report)
        await self._check_config(report)
        await self._check_dependencies(report)
        await self._check_traces(report)

        return report

    async def _check_capabilities(self, report: AuditReport) -> None:
        """Check tool capabilities and flag dangerous combinations."""
        if self.tool_registry is None:
            report.add_finding(
                "info", "capabilities", "Tool registry not available, skipping capability audit"
            )
            return

        # Get all tools and their capabilities
        tool_names = self.tool_registry.list_names()
        tool_caps: dict[str, list[str]] = {}

        for name in tool_names:
            try:
                meta = self.tool_registry.describe(name)
                tool_caps[name] = list(meta.capabilities)
            except (ToolNotFoundError, ValueError):
                tool_caps[name] = []

        report.tool_capabilities = tool_caps

        # Flag dangerous combinations
        for tool, caps in tool_caps.items():
            cap_set = set(caps)
            if SHELL_EXEC in cap_set and NETWORK_EGRESS in cap_set:
                report.add_finding(
                    "critical",
                    "capabilities",
                    f"Tool '{tool}' has dangerous capability combination",
                    {"tool": tool, "capabilities": caps, "reason": "shell_exec + network_egress"},
                )

        # Build session type tool map
        session_types = ["interactive", "subagent", "scheduler"]
        from hestia.policy.default import DefaultPolicyEngine

        policy = DefaultPolicyEngine()
        now = utcnow()

        for session_type in session_types:
            session = Session(
                id="audit-session",
                platform=session_type,
                platform_user="audit",
                started_at=now,
                last_active_at=now,
                slot_id=None,
                slot_saved_path=None,
                state=SessionState.ACTIVE,
                temperature=SessionTemperature.HOT,
            )
            allowed = policy.filter_tools(session, tool_names, self.tool_registry)
            report.session_tool_map[session_type] = allowed

        # Flag missing tool restrictions for subagent/scheduler
        if "subagent" in report.session_tool_map:
            subagent_tools = set(report.session_tool_map["subagent"])
            for tool in tool_names:
                if tool not in subagent_tools:
                    meta = self.tool_registry.describe(tool)
                    caps = set(meta.capabilities)
                    if SHELL_EXEC in caps or "write_local" in caps:
                        report.add_finding(
                            "info",
                            "capabilities",
                            f"Tool '{tool}' correctly restricted from subagent sessions",
                            {"tool": tool, "reason": "has shell_exec or write_local"},
                        )

    async def _check_sandbox(self, report: AuditReport) -> None:
        """Check sandbox configuration."""
        allowed_roots = self.config.storage.allowed_roots
        report.allowed_roots = allowed_roots

        # Check for relative paths in allowed_roots
        for root in allowed_roots:
            if root == "." or root == "./":
                report.add_finding(
                    "warning",
                    "sandbox",
                    "Relative path '.' in allowed_roots can resolve differently depending on cwd",
                    {"allowed_root": root},
                )
            elif not root.startswith("/"):
                report.add_finding(
                    "info",
                    "sandbox",
                    f"Relative path '{root}' in allowed_roots",
                    {"allowed_root": root},
                )

        # Check for overly broad roots
        dangerous_roots = ["/", "/home", "/root", "/etc", "/usr"]
        for root in allowed_roots:
            resolved = Path(root).resolve()
            for dangerous in dangerous_roots:
                try:
                    resolved.relative_to(Path(dangerous))
                    if str(resolved) == dangerous or root in dangerous_roots:
                        report.add_finding(
                            "critical",
                            "sandbox",
                            f"Allowed root '{root}' is overly broad",
                            {"allowed_root": root, "resolved": str(resolved)},
                        )
                except ValueError:
                    continue

        # Check file tools use check_path_allowed
        # This is a static check - we verify the function exists in path_utils
        try:
            from hestia.tools.builtin.path_utils import check_path_allowed

            report.add_finding(
                "info", "sandbox", "Path validation utility (check_path_allowed) is available"
            )
        except ImportError:
            report.add_finding(
                "critical",
                "sandbox",
                "Path validation utility (check_path_allowed) not found",
            )

    async def _check_config(self, report: AuditReport) -> None:
        """Check for common configuration misconfigurations."""
        issues: list[str] = []

        # Check Telegram allowed_users
        if self.config.telegram.bot_token:
            if not self.config.telegram.allowed_users:
                report.add_finding(
                    "critical",
                    "config",
                    "Telegram bot has empty allowed_users - anyone can talk to the bot",
                    {"setting": "telegram.allowed_users"},
                )
                issues.append("telegram.allowed_users is empty")
        else:
            report.add_finding(
                "info", "config", "Telegram bot_token not set (bot will not function)"
            )

        # Check Matrix configuration
        if not self.config.matrix.access_token:
            report.add_finding(
                "info", "config", "Matrix access_token not set (Matrix bot will not function)"
            )

        if self.config.matrix.access_token and not self.config.matrix.user_id:
            report.add_finding(
                "warning",
                "config",
                "Matrix access_token is set but user_id is missing",
                {"setting": "matrix.user_id"},
            )

        # Check allowed_roots
        if "/" in self.config.storage.allowed_roots:
            report.add_finding(
                "critical",
                "config",
                "allowed_roots contains '/' - allows access to entire filesystem",
                {"setting": "storage.allowed_roots"},
            )
            issues.append("allowed_roots contains '/'")

        # Check home directory in allowed_roots
        home = str(Path.home())
        if home in self.config.storage.allowed_roots:
            report.add_finding(
                "warning",
                "config",
                f"allowed_roots contains home directory ({home})",
                {"setting": "storage.allowed_roots", "home": home},
            )
            issues.append(f"allowed_roots contains home directory ({home})")

        report.config_issues = issues

    async def _check_dependencies(self, report: AuditReport) -> None:
        """Check for known vulnerabilities in dependencies."""
        # Check if pip-audit is available
        pip_audit = shutil.which("pip-audit")

        if pip_audit is None:
            report.add_finding(
                "info",
                "dependencies",
                "pip-audit not installed, skipping vulnerability scan",
                {"note": "Install pip-audit for dependency vulnerability scanning"},
            )
            report.dependency_issues.append("pip-audit not available")
            return

        try:
            # Run pip-audit
            result = subprocess.run(
                [pip_audit, "--format=json", "--desc=off"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                report.add_finding(
                    "info", "dependencies", "No known vulnerabilities found in dependencies"
                )
            else:
                # Parse vulnerabilities
                try:
                    vulnerabilities = json.loads(result.stdout)
                    for vuln in vulnerabilities:
                        report.add_finding(
                            "warning",
                            "dependencies",
                            f"Vulnerability in {vuln.get('name', 'unknown')}: {vuln.get('vulnerability_id', 'unknown')}",
                            vuln,
                        )
                        report.dependency_issues.append(
                            f"{vuln.get('name')}: {vuln.get('vulnerability_id')}"
                        )
                except json.JSONDecodeError:
                    report.add_finding(
                        "warning",
                        "dependencies",
                        "pip-audit returned non-zero exit but output could not be parsed",
                        {"stdout": result.stdout[:500], "stderr": result.stderr[:500]},
                    )

        except subprocess.TimeoutExpired:
            report.add_finding(
                "warning", "dependencies", "pip-audit timed out after 60 seconds"
            )
            report.dependency_issues.append("pip-audit timed out")
        except OSError as e:
            report.add_finding(
                "info",
                "dependencies",
                f"Could not run pip-audit: {e}",
            )
            report.dependency_issues.append(f"pip-audit error: {e}")

    async def _check_traces(self, report: AuditReport) -> None:
        """Check traces for suspicious patterns."""
        if self.trace_store is None:
            report.add_finding(
                "info", "traces", "Trace store not available, skipping trace checks"
            )
            return

        # Check if traces table exists and has data
        try:
            recent_traces = await self.trace_store.list_recent(limit=100)
        except Exception as e:  # noqa: BLE001
            # Trace store may raise various errors; audit should remain resilient
            report.add_finding(
                "info",
                "traces",
                f"Could not query trace store: {e}",
            )
            return

        if not recent_traces:
            report.add_finding(
                "info", "traces", "No traces found in trace store (no activity recorded yet)"
            )
            return

        # Check for suspicious patterns
        memory_write_after_http = 0
        excessive_terminal_calls = 0
        suspicious_writes = 0

        for trace in recent_traces:
            tools = trace.tools_called

            # Pattern: memory_write after http_get (potential data exfiltration path)
            has_http = False
            has_memory_write_after_http = False
            terminal_count = 0

            for tool in tools:
                if tool == "http_get":
                    has_http = True
                elif tool == "memory_write" and has_http:
                    has_memory_write_after_http = True
                elif tool == "terminal":
                    terminal_count += 1

            if has_memory_write_after_http:
                memory_write_after_http += 1

            if terminal_count > 3:
                excessive_terminal_calls += 1

        if memory_write_after_http > 0:
            report.add_finding(
                "warning",
                "traces",
                f"Found {memory_write_after_http} trace(s) with memory_write after http_get",
                {
                    "count": memory_write_after_http,
                    "note": "Potential data exfiltration path - verify this is intended behavior",
                },
            )
            report.trace_issues.append(
                f"{memory_write_after_http} trace(s) with memory_write after http_get"
            )

        if excessive_terminal_calls > 0:
            report.add_finding(
                "warning",
                "traces",
                f"Found {excessive_terminal_calls} trace(s) with excessive terminal calls (>3)",
                {"count": excessive_terminal_calls},
            )
            report.trace_issues.append(
                f"{excessive_terminal_calls} trace(s) with excessive terminal calls"
            )

        # Summary
        report.add_finding(
            "info",
            "traces",
            f"Analyzed {len(recent_traces)} recent traces",
            {"total_analyzed": len(recent_traces)},
        )
