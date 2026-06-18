# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-18

### Added
- **Platform Mode**: Persistent SQLite memory (`--memory`).
- **Coordinator Routing**: Deterministic agent routing via `CoordinatorAgent`.
- **Security Scanning**: Dedicated security agent checks.
- **Knowledge Graph**: AST-based repo context for Architect and Build agents.
- **MCP Optional Dependency**: Added optional `mcp` extra to `pyproject.toml`.

### Changed
- Improved error handling in Orchestrator with `fail_fast` option.
- Added uuid suffix to generated branch names in `GitHubPRAgent` to prevent collisions.

## [0.1.0] - Initial Release
- 5-Agent Pipeline (Reviewer, Architect, Test-Runner, Build, GitHub-PR).
- Local LLM and external OpenAI-compatible endpoints support.
- Model Context Protocol (MCP) basic integrations.
- Automatic PR creation and unified diff application.
