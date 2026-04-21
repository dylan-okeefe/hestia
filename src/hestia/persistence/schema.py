"""SQLAlchemy Core table definitions for Hestia."""

import sqlalchemy as sa

metadata = sa.MetaData()

sessions = sa.Table(
    "sessions",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("platform", sa.String, nullable=False),
    sa.Column("platform_user", sa.String, nullable=False),
    sa.Column("started_at", sa.DateTime, nullable=False),
    sa.Column("last_active_at", sa.DateTime, nullable=False),
    sa.Column("slot_id", sa.Integer, nullable=True),
    sa.Column("slot_saved_path", sa.String, nullable=True),
    sa.Column("state", sa.String, nullable=False),  # active/idle/archived
    sa.Column("temperature", sa.String, nullable=False),  # hot/warm/cold
    sa.Index("idx_sessions_platform_user", "platform", "platform_user", "state"),
    # Partial unique index: at most one ACTIVE session per (platform, platform_user).
    # Backs the INSERT ... ON CONFLICT DO NOTHING upsert in
    # SessionStore.get_or_create_session, which is the TOCTOU-safe path replacing
    # the old SELECT-then-INSERT race window. SQLite and PostgreSQL both support
    # partial unique indexes with identical syntax for the WHERE clause used here.
    sa.Index(
        "ux_sessions_active_user",
        "platform",
        "platform_user",
        unique=True,
        # Note: stored value is the lowercase ``SessionState.ACTIVE.value`` —
        # the enum *name* is "ACTIVE" but ``.value`` is "active" and that is
        # what gets persisted. The WHERE predicate must match the persisted
        # value exactly for the partial index (and the matching ON CONFLICT
        # WHERE in get_or_create_session) to apply.
        sqlite_where=sa.text("state = 'active'"),
        postgresql_where=sa.text("state = 'active'"),
    ),
)

messages = sa.Table(
    "messages",
    metadata,
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("idx", sa.Integer, nullable=False),
    sa.Column("role", sa.String, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("tool_calls", sa.Text, nullable=True),  # JSON
    sa.Column("tool_call_id", sa.String, nullable=True),
    sa.Column("reasoning_content", sa.Text, nullable=True),  # stored but stripped on send
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.PrimaryKeyConstraint("session_id", "idx"),
)

turns = sa.Table(
    "turns",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("state", sa.String, nullable=False),
    sa.Column("started_at", sa.DateTime, nullable=False),
    sa.Column("last_transition_at", sa.DateTime, nullable=False),
    sa.Column("iteration", sa.Integer, nullable=False, default=0),
    sa.Column("reasoning_budget", sa.Integer, nullable=False, default=2048),
    sa.Column("status_msg_id", sa.String, nullable=True),
    sa.Column("slot_id", sa.Integer, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
    sa.Index("idx_turns_session", "session_id", "started_at"),
)

turn_transitions = sa.Table(
    "turn_transitions",
    metadata,
    sa.Column("turn_id", sa.String, sa.ForeignKey("turns.id"), nullable=False),
    sa.Column("idx", sa.Integer, nullable=False),
    sa.Column("from_state", sa.String, nullable=False),
    sa.Column("to_state", sa.String, nullable=False),
    sa.Column("at", sa.DateTime, nullable=False),
    sa.Column("reason", sa.String, nullable=True),
    sa.PrimaryKeyConstraint("turn_id", "idx"),
)

scheduled_tasks = sa.Table(
    "scheduled_tasks",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("prompt", sa.Text, nullable=False),
    sa.Column("description", sa.String, nullable=True),
    sa.Column("cron_expression", sa.String, nullable=True),
    sa.Column("fire_at", sa.DateTime, nullable=True),
    sa.Column("enabled", sa.Boolean, nullable=False, default=True),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("last_run_at", sa.DateTime, nullable=True),
    sa.Column("next_run_at", sa.DateTime, nullable=True),
    sa.Column("last_error", sa.Text, nullable=True),
    sa.Index("idx_scheduled_tasks_session", "session_id"),
    sa.Index("idx_scheduled_tasks_due", "next_run_at", "enabled"),
)

failure_bundles = sa.Table(
    "failure_bundles",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("turn_id", sa.String, sa.ForeignKey("turns.id"), nullable=False),
    sa.Column("failure_class", sa.String, nullable=False),
    sa.Column("severity", sa.String, nullable=False),
    sa.Column("error_message", sa.Text, nullable=False),
    sa.Column("tool_chain", sa.Text, nullable=False),  # JSON
    sa.Column("created_at", sa.DateTime, nullable=False),
    # Enriched fields (Phase 11.2)
    sa.Column("request_summary", sa.Text, nullable=True),  # first 200 chars of user message
    sa.Column("policy_snapshot", sa.Text, nullable=True),  # JSON: allowed tools, reasoning budget
    sa.Column("slot_snapshot", sa.Text, nullable=True),  # JSON: slot_id, temperature
    sa.Column("trace_id", sa.String, nullable=True),  # link to trace record
    sa.Index("idx_failure_bundles_class", "failure_class"),
    sa.Index("idx_failure_bundles_created", "created_at"),
)

traces = sa.Table(
    "traces",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("turn_id", sa.String, sa.ForeignKey("turns.id"), nullable=False),
    sa.Column("started_at", sa.DateTime, nullable=False),
    sa.Column("ended_at", sa.DateTime, nullable=True),
    sa.Column("user_input_summary", sa.Text, nullable=False),
    sa.Column("tools_called", sa.Text, nullable=False),  # JSON list
    sa.Column("tool_call_count", sa.Integer, nullable=False, default=0),
    sa.Column("delegated", sa.Boolean, nullable=False, default=False),
    sa.Column("outcome", sa.String, nullable=False),  # success, partial, failed
    sa.Column("artifact_handles", sa.Text, nullable=False),  # JSON list
    sa.Column("prompt_tokens", sa.Integer, nullable=True),
    sa.Column("completion_tokens", sa.Integer, nullable=True),
    sa.Column("reasoning_tokens", sa.Integer, nullable=True),
    sa.Column("total_duration_ms", sa.Integer, nullable=True),
    sa.Index("idx_traces_session", "session_id", "started_at"),
    sa.Index("idx_traces_turn", "turn_id"),
    sa.Index("idx_traces_outcome", "outcome"),
    sa.Index("idx_traces_created", "started_at"),
)

# Egress events — outbound HTTP requests the agent makes (web_search, http_get
# tools). Co-owned with `traces` by TraceStore because both feed the egress /
# usage audit view, but the DDL canonically lives here so `metadata.create_all`
# is the single authoritative creator (consolidated in H-10, 2026-04-20).
egress_events = sa.Table(
    "egress_events",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, nullable=False),
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("domain", sa.String, nullable=False),
    sa.Column("status", sa.Integer, nullable=True),
    sa.Column("size", sa.Integer, nullable=True),
    # ISO-8601 UTC strings from ``utcnow().isoformat()`` (matches TraceStore).
    sa.Column("created_at", sa.String, nullable=False),
    sa.Index("idx_egress_session", "session_id", "created_at"),
    sa.Index("idx_egress_domain", "domain", "created_at"),
    sa.Index("idx_egress_created", "created_at"),
)

skills = sa.Table(
    "skills",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("name", sa.String, nullable=False, unique=True),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("file_path", sa.String, nullable=False),
    sa.Column("state", sa.String, nullable=False),  # draft, tested, trusted, deprecated, disabled
    sa.Column("capabilities", sa.Text, nullable=False),  # JSON list
    sa.Column("required_tools", sa.Text, nullable=False),  # JSON list
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("last_run_at", sa.DateTime, nullable=True),
    sa.Column("run_count", sa.Integer, nullable=False, default=0),
    sa.Column("failure_count", sa.Integer, nullable=False, default=0),
    sa.Index("idx_skills_state", "state"),
    sa.Index("idx_skills_name", "name"),
)

style_profiles = sa.Table(
    "style_profiles",
    metadata,
    sa.Column("platform", sa.String, nullable=False),
    sa.Column("platform_user", sa.String, nullable=False),
    sa.Column("metric", sa.String, nullable=False),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
    sa.PrimaryKeyConstraint("platform", "platform_user", "metric"),
    sa.Index("idx_style_profiles_user", "platform", "platform_user"),
    sa.Index("idx_style_profiles_updated", "updated_at"),
)
