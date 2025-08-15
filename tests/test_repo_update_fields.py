import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from bot.db import repo


@pytest.mark.asyncio
async def test_update_fields_creates_and_updates_record(tmp_path):
    db_path = tmp_path / "test.db"
    await repo.ensure_schema(str(db_path))
    chat_id = 123456
    await repo.update_fields(str(db_path), chat_id, alerts_on=1)
    chat = await repo.get_chat(str(db_path), chat_id)
    assert chat is not None
    assert chat.chat_id == chat_id
    assert chat.alerts_on == 1


@pytest.mark.asyncio
async def test_update_fields_rejects_unknown_field(tmp_path):
    """Passing an unknown field should raise a clear error."""
    db_path = tmp_path / "test.db"
    await repo.ensure_schema(str(db_path))

    with pytest.raises(ValueError):
        await repo.update_fields(str(db_path), 1, invalid_field=True)
