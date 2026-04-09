# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Project scaffold with uv, ruff, mypy
- Core dataclasses: Message, ToolCall, Session, Turn, ChatResponse
- InferenceClient for llama.cpp server with /tokenize, /chat, slot operations
- SessionStore with SQLAlchemy Core async
- Alembic migration setup with initial schema
- Smoke tests for inference and persistence

## [0.0.0] - 2026-04-09

### Added
- Initial scaffold (README, LICENSE, .gitignore, pyproject.toml)

