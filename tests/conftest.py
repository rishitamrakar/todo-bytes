"""Shared pytest fixtures.

Every test runs against an isolated fake HOME directory so we never touch
the real ~/.config/todo-bytes or ~/my-todos.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a fresh tmp dir for the duration of the test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def runner() -> CliRunner:
    """Typer test runner for invoking CLI commands in-process."""
    return CliRunner()
