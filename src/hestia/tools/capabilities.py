"""Standardized capability labels for tools.

These labels are used for security policy decisions. Each tool declares which
capabilities it requires, and PolicyEngine.filter_tools() can restrict tools
based on session context (e.g., subagents may be denied shell_exec).
"""

# Filesystem operations
READ_LOCAL = "read_local"
WRITE_LOCAL = "write_local"

# Code execution
SHELL_EXEC = "shell_exec"

# Network operations
NETWORK_EGRESS = "network_egress"

# Memory operations
MEMORY_READ = "memory_read"
MEMORY_WRITE = "memory_write"

# Email
EMAIL_SEND = "email_send"

# Orchestration
ORCHESTRATION = "orchestration"

# Self-management (proposal/style tools)
SELF_MANAGEMENT = "self_management"
