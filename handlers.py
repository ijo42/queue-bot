import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.formatting import Text, Bold

from database import Database

logger = logging.getLogger(__name__)

router = Router()
db = Database()


def get_user_display_name(message: Message) -> str:
    """Получить отображаемое имя пользователя"""
    user = message.from_user
    if user.full_name:
        return user.full_name
    elif user.username:
        return f"@{user.username}"
    else:
        return f"User {user.id}"


def get_user_mention(user_id: int, username: str, full_name: str) -> str:
    """Создать упоминание пользователя"""
    if full_name:
        return f'<a href="tg://user?id={user_id}">{full_name}</a>'
    elif username:
        return f"@{username}"
    else:
        return f"User {user_id}"


def get_topic_id(message: Message) -> int:
    """Получить ID топика из сообщения"""
    return message.message_thread_id or 0


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    help_text = """
🤖 <b>Бот интерактивной очереди</b>

<b>Команды управления очередью:</b>
/create [название] - создать новую очередь
/join - встать в очередь
/leave - выйти из очереди
/next - вызвать следующего (убрать первого)
/show - показать текущую очередь
/clear - очистить очередь (только админы)
/delete - удалить очередь (только админы)
/myposition - узнать свою позицию

<b>Примеры:</b>
/create Очередь на консультацию
/join
/show
"""
    await message.answer(help_text)


@router.message(Command("create"))
async def cmd_create_queue(message: Message):
    """Создать новую очередь"""
    # Проверка, что команда используется в группе
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    # Получаем название очереди
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Укажите название очереди\nПример: /create Очередь на консультацию")
        return
    
    queue_name = args[1].strip()
    topic_id = get_topic_id(message)
    
    # Проверяем, есть ли уже активная очередь
    existing_queue = db.get_active_queue(message.chat.id, topic_id)
    if existing_queue:
        await message.answer(
            f"❌ В этом топике уже есть активная очередь: <b>{existing_queue['name']}</b>\n"
            "Сначала удалите её командой /delete"
        )
        return
    
    # Создаём очередь
    queue_id = db.create_queue(message.chat.id, topic_id, queue_name)
    if queue_id:
        await message.answer(f"✅ Очередь <b>{queue_name}</b> создана!\nИспользуйте /join чтобы встать в очередь")
    else:
        await message.answer("❌ Ошибка при создании очереди")


@router.message(Command("join"))
async def cmd_join_queue(message: Message):
    """Встать в очередь"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    topic_id = get_topic_id(message)
    
    # Получаем активную очередь
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди. Создайте её командой /create")
        return
    
    # Добавляем пользователя
    user = message.from_user
    position = db.join_queue(
        queue['id'],
        user.id,
        user.username or "",
        user.full_name or ""
    )
    
    if position:
        user_name = get_user_display_name(message)
        await message.answer(
            f"✅ {user_name} встал(а) в очередь <b>{queue['name']}</b>\n"
            f"📍 Позиция: <b>{position}</b>"
        )
    else:
        await message.answer("❌ Вы уже в очереди!")


@router.message(Command("leave"))
async def cmd_leave_queue(message: Message):
    """Выйти из очереди"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    topic_id = get_topic_id(message)
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди")
        return
    
    if db.leave_queue(queue['id'], message.from_user.id):
        user_name = get_user_display_name(message)
        await message.answer(f"✅ {user_name} вышел(ла) из очереди")
    else:
        await message.answer("❌ Вы не в очереди")


@router.message(Command("show"))
async def cmd_show_queue(message: Message):
    """Показать текущую очередь"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    topic_id = get_topic_id(message)
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди")
        return
    
    members = db.get_queue_members(queue['id'])
    
    if not members:
        await message.answer(f"📋 Очередь <b>{queue['name']}</b> пуста")
        return
    
    # Формируем список участников
    lines = [f"📋 <b>{queue['name']}</b>\n"]
    for member in members:
        # Используем full_name или username без создания ссылки/упоминания
        if member['full_name']:
            user_display = member['full_name']
        elif member['username']:
            user_display = member['username']  # Без @ чтобы не вызывать уведомление
        else:
            user_display = f"User {member['user_id']}"

        lines.append(f"{member['position']}. {user_display}")

    await message.answer("\n".join(lines))

@router.message(Command("next"))
async def cmd_next_in_queue(message: Message):
    """Вызвать следующего в очереди"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    topic_id = get_topic_id(message)
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди")
        return
    
    # Убираем первого из очереди
    first_user = db.next_in_queue(queue['id'])
    
    if not first_user:
        await message.answer("📋 Очередь пуста")
        return
    
    # Получаем следующего пользователя
    members = db.get_queue_members(queue['id'])
    
    first_mention = get_user_mention(
        first_user['user_id'],
        first_user['username'],
        first_user['full_name']
    )
    
    response = f"🔔 <b>Вызван:</b> {first_mention}"
    
    if members:
        next_user = members[0]
        next_mention = get_user_mention(
            next_user['user_id'],
            next_user['username'],
            next_user['full_name']
        )
        response += f"\n\n👉 <b>Следующий:</b> {next_mention}"
    else:
        response += "\n\n✅ Очередь завершена!"
    
    await message.answer(response)


@router.message(Command("myposition"))
async def cmd_my_position(message: Message):
    """Узнать свою позицию в очереди"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    topic_id = get_topic_id(message)
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди")
        return
    
    position = db.get_user_position(queue['id'], message.from_user.id)
    
    if position:
        await message.answer(f"📍 Ваша позиция в очереди: <b>{position}</b>")
    else:
        await message.answer("❌ Вы не в очереди")


@router.message(Command("clear"))
async def cmd_clear_queue(message: Message):
    """Очистить очередь (только для администраторов)"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    # Проверка прав администратора
    chat_member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if chat_member.status not in ["creator", "administrator"]:
        await message.answer("❌ Эта команда доступна только администраторам")
        return
    
    topic_id = get_topic_id(message)
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди")
        return
    
    count = db.clear_queue(queue['id'])
    await message.answer(f"✅ Очередь <b>{queue['name']}</b> очищена ({count} участников удалено)")


@router.message(Command("delete"))
async def cmd_delete_queue(message: Message):
    """Удалить очередь (только для администраторов)"""
    if message.chat.type == "private":
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    
    # Проверка прав администратора
    chat_member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if chat_member.status not in ["creator", "administrator"]:
        await message.answer("❌ Эта команда доступна только администраторам")
        return
    
    topic_id = get_topic_id(message)
    queue = db.get_active_queue(message.chat.id, topic_id)
    if not queue:
        await message.answer("❌ Нет активной очереди")
        return
    
    if db.delete_queue(queue['id']):
        await message.answer(f"✅ Очередь <b>{queue['name']}</b> удалена")
    else:
        await message.answer("❌ Ошибка при удалении очереди")
