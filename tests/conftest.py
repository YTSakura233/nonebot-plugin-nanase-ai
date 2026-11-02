import sys
from pathlib import Path

import httpx
import pytest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def prevent_live_services(monkeypatch):
    from nonebot_plugin_soruto_ai.core import db
    monkeypatch.setattr(db.aiomysql, 'create_pool', AsyncMock(side_effect=AssertionError('live DB disabled in tests')))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request',
                        AsyncMock(side_effect=AssertionError('live HTTP disabled in tests')))
