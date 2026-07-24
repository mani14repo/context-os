# Contributing

1. Fork the repository and create a focused branch.
2. Install development dependencies with `pip install -e ".[dev]"`.
3. Add tests for behavior changes.
4. Run `ruff check src tests` and `pytest`.
5. Open a pull request describing the problem, design, and compatibility impact.

Public interfaces follow semantic versioning. New storage or model providers should implement the protocols in `contextos.protocols` and avoid coupling the core package to a specific vendor.

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
