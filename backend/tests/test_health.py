import asyncio
import pytest

def test_sync_environment_ready():
    """Verify synchronous test execution."""
    assert True

async def test_async_environment_ready():
    """Verify async test execution with pytest-asyncio auto mode."""
    await asyncio.sleep(0.01)
    assert True
