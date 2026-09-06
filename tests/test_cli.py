"""CLI 冒烟测试。"""

from __future__ import annotations

from typer.testing import CliRunner

from robin.main import app

runner = CliRunner()


def test_version():
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0
    assert "Robin" in res.output


def test_help_lists_commands():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    for cmd in ["run", "schedule", "archive", "init", "version"]:
        assert cmd in res.output
