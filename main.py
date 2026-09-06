import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats

from handlers import router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("HTTP_PROXY")

async def create_bot():
    session = AiohttpSession(proxy=PROXY_URL)

    # Создаем бота с сессией через прокси
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    return bot, dp

async def set_bot_commands(bot: Bot):
    """Регистрация команд бота"""
    commands = [
        BotCommand(command="start", description="Показать справку"),
        BotCommand(command="create", description="Создать очередь"),
        BotCommand(command="join", description="Встать в очередь"),
        BotCommand(command="leave", description="Выйти из очереди"),
        BotCommand(command="show", description="Показать очередь"),
        BotCommand(command="next", description="Вызвать следующего"),
        BotCommand(command="myposition", description="Узнать свою позицию"),
        BotCommand(command="clear", description="Очистить очередь (админы)"),
        BotCommand(command="delete", description="Удалить очередь (админы)"),
    ]
    
    # Регистрируем команды для всех групповых чатов
    await bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
    logger.info("Команды бота зарегистрированы")


async def main():
    """Основная функция"""
    bot, dp = await create_bot()
    if not BOT_TOKEN:
        logger.error("Не задан BOT_TOKEN в переменных окружения")
        return

    try:
        await set_bot_commands(bot)
        logger.info("Бот интерактивной очереди запускается...")
        await dp.start_polling(bot)
    finally:
        # Properly close the bot's session
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
