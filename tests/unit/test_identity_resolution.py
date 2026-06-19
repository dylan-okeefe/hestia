"""Tests for identity resolution and system context injection (L169b)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.config import HestiaConfig
from hestia.core.types import Message, Session
from hestia.orchestrator.assembly import TurnAssembly
from hestia.orchestrator.types import Turn, TurnContext, TurnState
from hestia.persistence.db import Database
from hestia.persistence.users import UserStore
from hestia.platforms.base import Platform
from hestia.platforms.runners import run_platform


class TestUserStoreIdentityResolution:
    """Direct tests for UserStore identity lookups."""

    @pytest.fixture
    async def user_store(self, tmp_path):
        """Create a UserStore with a fresh database."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = UserStore(db)
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_get_user_by_identity_returns_correct_user(self, user_store):
        """Resolving an identity returns the matching user."""
        user = await user_store.create_user("Dylan", role="admin", notes="operator")
        await user_store.add_identity(user.id, "telegram", "12345")

        resolved = await user_store.get_user_by_identity("telegram", "12345")
        assert resolved is not None
        assert resolved.id == user.id
        assert resolved.display_name == "Dylan"
        assert resolved.role == "admin"

    @pytest.mark.asyncio
    async def test_cross_platform_identity_resolution(self, user_store):
        """Same user linked to multiple platforms resolves correctly."""
        user = await user_store.create_user("Dylan", role="admin")
        await user_store.add_identity(user.id, "telegram", "tg_dylan")
        await user_store.add_identity(user.id, "matrix", "@dylan:matrix.org")

        tg_resolved = await user_store.get_user_by_identity("telegram", "tg_dylan")
        mx_resolved = await user_store.get_user_by_identity("matrix", "@dylan:matrix.org")

        assert tg_resolved is not None
        assert mx_resolved is not None
        assert tg_resolved.id == user.id
        assert mx_resolved.id == user.id

    @pytest.mark.asyncio
    async def test_get_user_by_identity_returns_none_for_unknown(self, user_store):
        """Unknown identities resolve to None."""
        resolved = await user_store.get_user_by_identity("telegram", "99999")
        assert resolved is None


class TestGroupChatResolution:
    """Tests for group chat sender resolution via run_platform."""

    @pytest.fixture
    async def group_setup(self, tmp_path):
        """Create an AppContext-like mock with a real UserStore."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = UserStore(db)

        app = MagicMock()
        app.db = db
        app.bootstrap_db = AsyncMock()
        app.set_confirm_callback = MagicMock()
        app.make_orchestrator = MagicMock()
        app.session_store = MagicMock()
        app.user_store = store
        app.inference.close = AsyncMock()
        app.context_builder = MagicMock()
        app.context_builder.warm_up = AsyncMock()
        app.event_bus = None

        _session = Session(
            id="sess-1",
            platform="fake",
            platform_user="room_1",
            started_at=MagicMock(),
            last_active_at=MagicMock(),
            slot_id=None,
            slot_saved_path=None,
            state=MagicMock(),
            temperature=MagicMock(),
        )
        app.handoff_service = MagicMock()
        app.handoff_service.get_or_create_session_with_handoff = AsyncMock(
            return_value=_session
        )

        orchestrator = MagicMock()
        orchestrator.recover_stale_turns = AsyncMock(return_value=0)
        orchestrator.process_turn = AsyncMock()
        app.make_orchestrator.return_value = orchestrator

        config = MagicMock(spec=HestiaConfig)
        config.system_prompt = "You are Hestia."
        config.scheduler = MagicMock()
        config.scheduler.tick_interval_seconds = 60
        config.telegram = MagicMock()
        config.telegram.voice_messages = False
        config.telegram.bot_token = ""
        config.matrix = MagicMock()
        config.matrix.access_token = ""
        config.matrix.user_id = ""
        config.inference = MagicMock()
        config.inference.model_name = "test-model"
        config.inference.stream = False
        config.voice = MagicMock()

        yield app, config, store, orchestrator
        await db.close()

    @pytest.mark.asyncio
    async def test_group_chat_uses_sender_for_resolution(self, group_setup):
        """In a group chat, sender_platform_user is used to resolve the user."""
        app, config, store, orchestrator = group_setup

        user = await store.create_user("Alice", role="trusted")
        await store.add_identity(user.id, "fake", "alice_123")

        class FakePlatform(Platform):
            def __init__(self):
                self._on_message = None

            @property
            def name(self):
                return "fake"

            async def start(self, on_message):
                self._on_message = on_message

            async def stop(self):
                pass

            async def send_message(self, user, text):
                return "msg-id"

            async def edit_message(self, user, msg_id, text):
                pass

            async def send_error(self, user, text):
                pass

        adapter = FakePlatform()

        async def single_message_then_stop(*args, **kwargs):
            if adapter._on_message is not None:
                await adapter._on_message("fake", "room_1", "hello", "alice_123", None)
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=single_message_then_stop):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=AsyncMock(return_value=True),
                platform_name="fake",
            )

        call_kwargs = orchestrator.process_turn.call_args.kwargs
        assert call_kwargs["resolved_user"] is not None
        assert call_kwargs["resolved_user"].display_name == "Alice"
        assert call_kwargs["resolved_user"].role == "trusted"

    @pytest.mark.asyncio
    async def test_private_chat_uses_platform_user_for_resolution(self, group_setup):
        """In a private chat, platform_user is used to resolve the user."""
        app, config, store, orchestrator = group_setup

        user = await store.create_user("Bob", role="user")
        await store.add_identity(user.id, "fake", "bob_123")

        class FakePlatform(Platform):
            def __init__(self):
                self._on_message = None

            @property
            def name(self):
                return "fake"

            async def start(self, on_message):
                self._on_message = on_message

            async def stop(self):
                pass

            async def send_message(self, user, text):
                return "msg-id"

            async def edit_message(self, user, msg_id, text):
                pass

            async def send_error(self, user, text):
                pass

        adapter = FakePlatform()

        async def single_message_then_stop(*args, **kwargs):
            if adapter._on_message is not None:
                await adapter._on_message("fake", "bob_123", "hello", None, None)
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=single_message_then_stop):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=AsyncMock(return_value=True),
                platform_name="fake",
            )

        call_kwargs = orchestrator.process_turn.call_args.kwargs
        assert call_kwargs["resolved_user"] is not None
        assert call_kwargs["resolved_user"].display_name == "Bob"

    @pytest.mark.asyncio
    async def test_group_chat_auto_registers_room(self, group_setup):
        """Group chat messages auto-create room and membership."""
        app, config, store, orchestrator = group_setup

        user = await store.create_user("Carol", role="user")
        await store.add_identity(user.id, "fake", "carol_123")

        class FakePlatform(Platform):
            def __init__(self):
                self._on_message = None

            @property
            def name(self):
                return "fake"

            async def start(self, on_message):
                self._on_message = on_message

            async def stop(self):
                pass

            async def send_message(self, user, text):
                return "msg-id"

            async def edit_message(self, user, msg_id, text):
                pass

            async def send_error(self, user, text):
                pass

        adapter = FakePlatform()

        async def single_message_then_stop(*args, **kwargs):
            if adapter._on_message is not None:
                await adapter._on_message("fake", "room_2", "hello", "carol_123", None)
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=single_message_then_stop):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=AsyncMock(return_value=True),
                platform_name="fake",
            )

        # Room should have been created
        room = await store.get_room_by_platform("fake", "room_2")
        assert room is not None

        # User should be a member
        members = await store.get_room_members(room.id)
        assert len(members) == 1
        assert members[0].id == user.id

    @pytest.mark.asyncio
    async def test_group_chat_no_room_for_unknown_user(self, group_setup):
        """Unknown users in group chats do not trigger room creation."""
        app, config, store, orchestrator = group_setup

        class FakePlatform(Platform):
            def __init__(self):
                self._on_message = None

            @property
            def name(self):
                return "fake"

            async def start(self, on_message):
                self._on_message = on_message

            async def stop(self):
                pass

            async def send_message(self, user, text):
                return "msg-id"

            async def edit_message(self, user, msg_id, text):
                pass

            async def send_error(self, user, text):
                pass

        adapter = FakePlatform()

        async def single_message_then_stop(*args, **kwargs):
            if adapter._on_message is not None:
                await adapter._on_message("fake", "room_3", "hello", "unknown_123", None)
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=single_message_then_stop):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=AsyncMock(return_value=True),
                platform_name="fake",
            )

        # Unknown senders in group/room contexts are rejected before a turn is
        # created, so process_turn is never called and no room is auto-registered.
        assert orchestrator.process_turn.call_args is None

        room = await store.get_room_by_platform("fake", "room_3")
        assert room is None


class TestResolvedUserTyping:
    """Tests that resolved_user is properly typed as User | None."""

    @pytest.mark.asyncio
    async def test_resolved_user_typed_as_user(self):
        """TurnContext.resolved_user exposes User attributes without casting."""
        from hestia.persistence.users import User

        user = User(
            id="u1",
            display_name="Dylan",
            role="admin",
            trust_preset="household",
            notes="test",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        turn = Turn(
            id="turn-1",
            session_id="sess-1",
            state=TurnState.RECEIVED,
            user_message=Message(role="user", content="hi"),
            started_at=datetime.now(UTC),
        )
        ctx = TurnContext(
            turn=turn,
            user_message=Message(role="user", content="hi"),
            system_prompt="You are helpful.",
            respond_callback=AsyncMock(),
            session=MagicMock(),
            resolved_user=user,
        )

        # These attribute accesses should work without casting
        assert ctx.resolved_user is not None
        assert ctx.resolved_user.display_name == "Dylan"
        assert ctx.resolved_user.role == "admin"


class TestSystemPromptInjection:
    """Tests for user context injection into the system prompt."""

    @pytest.fixture
    async def assembly_setup(self, tmp_path):
        """Create a TurnAssembly with mocked dependencies."""
        builder = MagicMock()
        builder.set_style_prefix = MagicMock()
        builder.build = AsyncMock(return_value=MagicMock())

        tools = MagicMock()
        tools.list_names = MagicMock(return_value=[])
        tools.meta_tool_schemas = MagicMock(return_value=[])

        policy = MagicMock()
        policy.filter_tools = MagicMock(return_value=[])

        message_store = MagicMock()
        message_store.get_messages = AsyncMock(return_value=[])
        message_store.append_message = AsyncMock()

        assembly = TurnAssembly(
            context_builder=builder,
            tool_registry=tools,
            policy=policy,
            session_store=MagicMock(),
            message_store=message_store,
            proposal_store=None,
            style_store=None,
            style_config=None,
            slot_manager=None,
        )

        yield assembly, builder

    @pytest.mark.asyncio
    async def test_system_prompt_includes_resolved_user(self, assembly_setup):
        """When resolved_user is set, user context is prepended to system prompt."""
        assembly, builder = assembly_setup

        session = MagicMock()
        session.id = "sess-1"
        session.platform = "fake"
        session.platform_user = "u1"

        user = MagicMock()
        user.display_name = "Dylan"
        user.role = "admin"
        user.notes = "Likes coffee"

        turn = Turn(
            id="turn-1",
            session_id="sess-1",
            state=TurnState.RECEIVED,
            user_message=Message(role="user", content="hi"),
            started_at=MagicMock(),
        )
        ctx = TurnContext(
            turn=turn,
            user_message=Message(role="user", content="hi"),
            system_prompt="You are helpful.",
            respond_callback=AsyncMock(),
            session=session,
            resolved_user=user,
        )

        transition = AsyncMock()
        await assembly.prepare(session, ctx, transition)

        call_args = builder.build.call_args.kwargs
        built_prompt = call_args["system_prompt"]
        assert built_prompt.startswith("Current user: Dylan (admin)\nNotes: Likes coffee")
        assert "You are helpful." in built_prompt

    @pytest.mark.asyncio
    async def test_system_prompt_no_user_context_when_unresolved(self, assembly_setup):
        """When resolved_user is None, no user context is injected."""
        assembly, builder = assembly_setup

        session = MagicMock()
        session.id = "sess-1"
        session.platform = "fake"
        session.platform_user = "u1"

        turn = Turn(
            id="turn-1",
            session_id="sess-1",
            state=TurnState.RECEIVED,
            user_message=Message(role="user", content="hi"),
            started_at=MagicMock(),
        )
        ctx = TurnContext(
            turn=turn,
            user_message=Message(role="user", content="hi"),
            system_prompt="You are helpful.",
            respond_callback=AsyncMock(),
            session=session,
            resolved_user=None,
        )

        transition = AsyncMock()
        await assembly.prepare(session, ctx, transition)

        call_args = builder.build.call_args.kwargs
        built_prompt = call_args["system_prompt"]
        assert built_prompt == "You are helpful."
