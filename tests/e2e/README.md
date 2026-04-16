# End-to-End Tests for Hestia

These tests exercise the full stack through Matrix: platform adapter → orchestrator → inference → tools → response.

## Prerequisites

- Docker and docker-compose
- Python dependencies: `matrix-nio` (already in project dependencies)

## Running E2E Tests

### 1. Start Synapse (Matrix homeserver)

```bash
cd tests/e2e
docker-compose up -d
```

Wait for Synapse to be healthy (about 10-20 seconds).

### 2. Configure test users and room

This is a one-time setup. The test fixtures expect:
- A test user (`@testuser:localhost`)
- A Hestia bot user (`@hestia:localhost`)
- A shared room where both users are members

You can use Synapse's admin API or register users via:

```bash
# Register test user (if registration is enabled)
curl -X POST http://localhost:8008/_matrix/client/r0/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass123","auth":{"type":"m.login.dummy"}}'
```

### 3. Start Hestia with Matrix adapter

Configure Hestia to connect to the test Synapse:

```python
# test_config.py
matrix = MatrixConfig(
    homeserver="http://localhost:8008",
    user_id="@hestia:localhost",
    access_token="<test_bot_token>",
    allowed_rooms=["!<room_id>:localhost"],
)
```

Run Hestia:
```bash
hestia matrix --config test_config.py
```

### 4. (Optional) Start mock llama server

For deterministic, fast tests without a real LLM:

```bash
python tests/e2e/mock_llama_server.py &
```

Configure Hestia to use the mock server:
```python
inference = InferenceConfig(
    base_url="http://localhost:9999",
    model_name="mock-llama",
)
```

### 5. Run the tests

```bash
# Unskip the tests by removing the pytestmark or using an override
HESTIA_TEST_SYNAPSE_URL=http://localhost:8008 \
HESTIA_TEST_USER=@testuser:localhost \
HESTIA_TEST_PASSWORD=testpass123 \
HESTIA_TEST_HESTIA_USER=@hestia:localhost \
pytest tests/e2e/ -v
```

### 6. Cleanup

```bash
docker-compose down -v
```

## Test Coverage

| Test | Description |
|------|-------------|
| `test_hello_gets_response` | Basic round-trip connectivity |
| `test_time_query_triggers_tool` | Tool invocation (current_time) |
| `test_memory_save_and_retrieve` | Memory persistence |
| `test_context_persists_across_turns` | Multi-turn conversation |
| `test_write_file_requires_confirmation` | Tool confirmation flow |

## Skipped by Default

E2E tests are **skipped by default** because they require Docker. Default pytest runs stay green:

```bash
uv run pytest tests/unit tests/integration -q  # No e2e tests run
```

To run e2e tests, explicitly:
```bash
uv run pytest tests/e2e -v  # Only e2e tests
uv run pytest tests/ -v     # All tests including e2e
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Test (pytest)                                              │
│  └── HestiaMatrixTestClient                                 │
│      └── matrix-nio AsyncClient ──→ Synapse (Docker)        │
└─────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  Hestia Bot   │
                              │  (process)    │
                              └───────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  Mock/OpenAI  │
                              │  LLM Server   │
                              └───────────────┘
```

## Troubleshooting

**Test times out waiting for response:**
- Ensure Hestia bot is running and connected
- Check that both users are in the same room
- Verify the room ID in `allowed_rooms` config

**Synapse won't start:**
- Check port 8008 is available
- Review logs: `docker-compose logs synapse`

**Login fails:**
- User may need to be registered first
- Check Synapse configuration for registration settings
