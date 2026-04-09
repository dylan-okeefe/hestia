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
