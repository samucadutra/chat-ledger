import json
import logging

import pytest

from chatledger_core.infra.logging import (
    bind_context,
    configure_logging,
    get_logger,
    unbind_context,
)


def test_json_log_lines_carry_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info", service="test-svc")
    bind_context(request_id="req-1")
    get_logger("t").info("hello", extra_field=1)
    unbind_context("request_id")
    get_logger("t").info("bye")
    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert lines[0]["event"] == "hello"
    assert lines[0]["request_id"] == "req-1"
    assert lines[0]["service"] == "test-svc"
    assert lines[0]["level"] == "info"
    assert "request_id" not in lines[1]
    logging.getLogger().handlers = []


def test_unknown_level_defaults_to_info() -> None:
    configure_logging("nonsense")
    assert logging.getLogger().level == logging.INFO
    logging.getLogger().handlers = []
