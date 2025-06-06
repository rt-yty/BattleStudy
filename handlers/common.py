from aiogram import Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command
from typing import Dict, List, Tuple
from models import Player
from database import get_player_rating, get_player_stats, get_leaderboard, fetch_seen_question_ids

router = Router()

queues: Dict[str, List[Player]] = {
    "easy": [],
    "medium": [],
    "hard": []
}

LEVEL_NAMES = {
    "easy": "лёгкий",
    "medium": "средний",
    "hard": "сложный"
}

TOP_PLAYERS_LIMIT = 10

def create_main_keyboard(include_leave_queue: bool = False) -> ReplyKeyboardMarkup:
    keyboard_buttons = [
        [KeyboardButton(text="👨‍✈️ Присоединиться к бою")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🏆 Турнирная таблица")],
        [KeyboardButton(text="❓ Как играть")]
    ]
    if include_leave_queue:
        keyboard_buttons.insert(1, [KeyboardButton(text="❌ Выйти из очереди")])
        keyboard_buttons.pop(0)
    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)

def create_level_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Лёгкий", callback_data="level_easy"),
            InlineKeyboardButton(text="Средний", callback_data="level_medium"),
            InlineKeyboardButton(text="Сложный", callback_data="level_hard")
        ]]
    )

def create_game_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🏆 Турнирная таблица")],
            [KeyboardButton(text="❓ Как играть")]
        ],
        resize_keyboard=True
    )

def create_no_questions_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👨‍✈️ Присоединиться к бою")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🏆 Турнирная таблица")],
            [KeyboardButton(text="❓ Как играть")]
        ],
        resize_keyboard=True
    )

def create_rematch_keyboard(key: str, accept: bool = False) -> InlineKeyboardMarkup:
    if accept:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Принять реванш", callback_data=f"rematch:{key}"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data=f"decline_rematch:{key}")
        ]])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Взять реванш", callback_data=f"rematch:{key}"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data=f"decline_rematch:{key}")
        ]])

def is_player_in_queue(user_id: int) -> bool:
    return any(any(p.user_id == user_id for p in queue) for queue in queues.values())

def is_player_in_match(user_id: int) -> bool:
    from .match import active_matches, player_matches
    if user_id not in player_matches:
        return False
    match_id = player_matches.get(user_id)
    match_exists = match_id in active_matches
    if not match_exists:
        del player_matches[user_id]
        return False
    return True

def get_player_status(user_id: int) -> Tuple[bool, bool]:
    return is_player_in_queue(user_id), is_player_in_match(user_id)

def remove_player_from_queues(user_id: int) -> bool:
    removed = False
    for level in queues:
        before_len = len(queues[level])
        queues[level] = [p for p in queues[level] if p.user_id != user_id]
        if len(queues[level]) < before_len:
            removed = True
    return removed

async def check_available_questions(user_id: int, level: str) -> Tuple[bool, str]:
    from models.match import MatchFactory
    seen_question_ids = await fetch_seen_question_ids(user_id, level)
    all_questions = MatchFactory.get_questions_by_level(level)
    available_questions = [q for q in all_questions if q.get('id') not in seen_question_ids]
    if not available_questions:
        return False, f"У тебя закончились вопросы уровня '{LEVEL_NAMES[level]}'. Попробуй другой уровень сложности."
    return True, ""

async def try_start_match_with_opponent(current_player: Player, level: str) -> bool:
    from .match import create_match
    opponent = None
    for player in queues[level]:
        if player.user_id != current_player.user_id:
            opponent = player
            break
    if opponent:
        queues[level] = [p for p in queues[level] if p.user_id not in [current_player.user_id, opponent.user_id]]
        await create_match(current_player, opponent, level)
        print(f"Матч создан между игроками {current_player.user_id} и {opponent.user_id} на уровне {level}")
        return True
    return False

# === ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ ===
@router.message(Command("start"))
async def start_command(message: Message):
    keyboard = create_main_keyboard()
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в BattleStudy - бот для поединков по теории вероятностей!\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )

@router.message(F.text == "👨‍✈️ Присоединиться к бою")
async def join_battle(message: Message):
    user_id = message.from_user.id
    in_queue, in_match = get_player_status(user_id)
    if in_queue:
        await message.answer("Ты уже в очереди!")
        return
    if in_match:
        await message.answer("Ты уже в поединке!")
        return
    keyboard = create_level_selection_keyboard()
    await message.answer(
        "Выбери уровень сложности:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("level_"))
async def select_level(callback: CallbackQuery):
    level = callback.data.split("_")[1]
    user_id = callback.from_user.id
    in_queue, in_match = get_player_status(user_id)
    if in_queue:
        await callback.answer("Ты уже в очереди!")
        return
    if in_match:
        await callback.answer("Ты уже в поединке!")
        return
    questions_available, error_message = await check_available_questions(user_id, level)
    if not questions_available:
        keyboard = create_main_keyboard()
        await callback.message.answer(f"❗ {error_message}", reply_markup=keyboard)
        await callback.answer()
        return
    player = Player(
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        rating=await get_player_rating(user_id),
        preferred_level=level
    )
    queues[level].append(player)
    print(f"Игрок {player.user_id} добавлен в очередь {level}. Текущая очередь {level}: {[p.user_id for p in queues[level]]}")
    match_started = await try_start_match_with_opponent(player, level)
    if not match_started:
        keyboard = create_main_keyboard(include_leave_queue=True)
        await callback.message.answer(
            f"Ты добавлен в очередь с уровнем сложности: {LEVEL_NAMES[level]}. Ждём соперника...",
            reply_markup=keyboard
        )
    await callback.answer()

@router.message(F.text == "❌ Выйти из очереди")
async def leave_queue(message: Message):
    user_id = message.from_user.id
    removed = remove_player_from_queues(user_id)
    if removed:
        keyboard = create_main_keyboard()
        await message.answer("Ты вышел из очереди.", reply_markup=keyboard)
        print(f"Игрок {user_id} вышел из очереди.")
    else:
        await message.answer("Ты не находишься в очереди.")

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    stats = await get_player_stats(user_id)
    await message.answer(
        f"👤 Профиль игрока: {message.from_user.first_name}\n\n"
        f"🎮 Сыграно боев: {stats['total_games']}\n"
        f"⭐ Рейтинг: {stats['rating']}\n\n"
        f"🏆 Статистика побед:\n\n"
        f"    🟢 Лёгкий уровень: {stats['wins_easy']}\n"
        f"    🟡 Средний уровень: {stats['wins_medium']}\n"
        f"    🔴 Сложный уровень: {stats['wins_hard']}\n"
    )

@router.message(F.text == "🏆 Турнирная таблица")
async def show_leaderboard(message: Message):
    leaderboard = await get_leaderboard(TOP_PLAYERS_LIMIT)
    if not leaderboard:
        await message.answer("Турнирная таблица пуста.")
        return
    text = f"🏆 Турнирная таблица (топ-{TOP_PLAYERS_LIMIT}):\n\n"
    for i, (user_id, rating) in enumerate(leaderboard, 1):
        try:
            user = await router.bot.get_chat(user_id)
            name = user.first_name
        except Exception:
            name = f"Игрок {user_id}"
        text += f"{i}. {name} — {rating} очков\n"
    await message.answer(text)

@router.message(F.text == "❓ Как играть")
async def show_help(message: Message):
    help_text = (
        "📚 <b>Как играть в BattleStudy</b>\n\n"
        "BattleStudy - это бот для поединков по теории вероятностей. "
        "Вот основные правила:\n\n"
        "1️⃣ <b>Начало игры</b>\n"
        "Нажмите кнопку 'Присоединиться к бою', выберите уровень сложности, "
        "и бот найдет вам соперника.\n\n"
        "2️⃣ <b>Время на ответ</b>\n"
        "В зависимости от уровня сложности, у вас будет разное время на ответ:\n\n"
        "   🟢 Легкий: 1 минута\n"
        "   🟡 Средний: 3 минуты\n"
        "   🔴 Сложный: 5 минут\n\n"
        "3️⃣ <b>Победа и рейтинг</b>\n"
        "Побеждает тот, кто первым даст правильный ответ. "
        "За победу вы получаете очки рейтинга, за поражение - теряете.\n\n"
        "   🟢 Легкий: +10/-5 очков\n"
        "   🟡 Средний: +25/-15 очков\n"
        "   🔴 Сложный: +50/-35 очков\n\n"
        "4️⃣ <b>Профиль и статистика</b>\n"
        "В профиле вы можете увидеть свой рейтинг, количество побед по каждой сложности и количество сыгранных боев "
        "на каждом уровне сложности.\n\n"
        "5️⃣ <b>Турнирная таблица</b>\n"
        "Показывает топ-10 игроков по рейтингу.\n\n"
        "Удачи в поединках! 🎮"
    )
    await message.answer(help_text)