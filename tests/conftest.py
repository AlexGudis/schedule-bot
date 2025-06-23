import pytest
from unittest.mock import AsyncMock, MagicMock


import sys
from pathlib import Path

# Добавляем src в путь поиска модулей
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

@pytest.fixture
def bot():
    mock = AsyncMock()
    
    # Создаем специальный mock для отслеживания отправленных сообщений
    mock.last_message = None
    
    async def send_message(chat_id=None, text=None, reply_markup=None, **kwargs):
        mock.last_message = MagicMock()
        mock.last_message.text = text
        mock.last_message.reply_markup = reply_markup
        return mock.last_message
    
    mock.send_message = send_message
    return mock 

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    # Мокируем стандартные ответы Supabase
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return mock