# ADR-0003: Language is Python 3.11+

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Python 3.11 brings significant performance improvements (10-60% faster
  than 3.10), better error messages, and native `asyncio.TaskGroup`. We don't need
  to support older versions because this is a greenfield project targeting modern
  hardware.
- **Decision:** Minimum supported Python version is 3.11. Development happens on
  3.13 when available.
- **Consequences:** Cannot run on Ubuntu 22.04's default Python 3.10 without
  installing a newer version. Use of `|` union syntax and other 3.10+ features
  is allowed.
