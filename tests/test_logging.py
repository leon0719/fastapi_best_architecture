"""log_config 必須實際被 main.py 接線,且 setup_logging 可安全重複呼叫。"""

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_setup_logging_exists_and_idempotent():
    from app.common.core.log_config import setup_logging

    setup_logging()
    setup_logging()  # 第二次呼叫不得噴錯或重複累加 handler


def test_main_wires_up_logging():
    from app import main

    source = inspect.getsource(main)
    assert "setup_logging()" in source
