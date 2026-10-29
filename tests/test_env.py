"""`.env` loading for the CLI and the smoke ping. Existing variables win."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from router.smoke import load_env_file


def test_env_file_fills_missing_keys_and_keeps_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "# comment",
                "NEBIUS_API_KEY=from-file",
                "TAVILY_API_KEY='web'",
                "EMPTY=",
                "export OTHER=1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEBIUS_API_KEY", "already")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EMPTY", raising=False)
    monkeypatch.delenv("OTHER", raising=False)

    load_env_file()

    assert os.environ["NEBIUS_API_KEY"] == "already"
    assert os.environ["TAVILY_API_KEY"] == "web"
    assert os.environ["EMPTY"] == ""
    assert os.environ["OTHER"] == "1"
