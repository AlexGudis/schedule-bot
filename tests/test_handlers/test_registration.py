import pytest
from unittest.mock import AsyncMock, patch
from src.bot.handlers import command_start_handler, registration

@pytest.mark.asyncio
async def test_start_command(bot):
    with patch('src.bot.handlers.Bot', return_value=bot):
        message = AsyncMock()
        message.text = "/start"
        message.from_user.id = 123
        
        await command_start_handler(message, AsyncMock())
        
        assert bot.send_message.await_count == 1
        assert "Привет" in bot.send_message.call_args.kwargs['text']
        assert hasattr(bot.send_message.call_args.kwargs['reply_markup'], 'inline_keyboard')

@pytest.mark.asyncio
async def test_registration_flow(bot, mock_supabase):
    with patch('src.bot.handlers.Bot', return_value=bot):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        
        callback = AsyncMock()
        callback.data = "registration"
        callback.from_user.username = "test_user"
        callback.message = AsyncMock()
        
        await registration(callback, AsyncMock())
        
        assert bot.send_message.await_count == 1
        assert "Введите ваше ФИО" in bot.send_message.call_args.kwargs['text']