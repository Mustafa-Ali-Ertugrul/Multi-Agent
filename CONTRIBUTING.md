# Contributing to Multi-Agent

We love your input! We want to make contributing to this project as easy and transparent as possible.

## Pull Requests

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Ensure the test suite passes.
4. Make sure your code lints and is formatted correctly.

## Quality Checks

Please run the quality checks before submitting a contribution:

```bash
ruff check .
ruff format --check .
mypy src tests
pytest
```

When adding a new agent or gateway behavior, please include the relevant unit tests. `mypy` is a blocking step in the CI, so ensure type hints are comprehensive in public APIs and test helpers.

## Security Issues

If you discover a security vulnerability, please do not open an issue. Email the project maintainers directly.
