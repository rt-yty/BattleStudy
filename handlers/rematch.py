import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery
from typing import Dict, Set, Tuple, List

from models import Player
from .common import (
    create_main_keyboard,
    create_rematch_keyboard,
    create_no_questions_keyboard,
    LEVEL_NAMES
)
from database import get_player_rating, fetch_seen_question_ids
from models.match import MatchFactory
from database import fetch_seen_question_ids
from models.player import Player

router = Router()

rematch_waiting: Dict[Tuple[int, int], Set[int]] = {}

rematch_messages: Dict[Tuple[int, int], Dict[int, int]] = {}

rematch_levels: Dict[Tuple[int, int], str] = {}

rematch_timers: Dict[Tuple[int, int], asyncio.Task] = {}


def get_pair_key(user_id1: int, user_id2: int) -> Tuple[int, int]:
    min_id = min(user_id1, user_id2)
    max_id = max(user_id1, user_id2)
    return (min_id, max_id)


def get_other_player_id(pair_key: Tuple[int, int], user_id: int) -> int:
    min_id, max_id = pair_key
    return min_id if user_id == max_id else max_id


async def validate_rematch_participant(callback: CallbackQuery, min_id: int, max_id: int) -> bool:
    user_id = callback.from_user.id
    if user_id != min_id and user_id != max_id:
        await callback.answer("Вы не можете участвовать в этом реванше", show_alert=True)
        return False
    return True


async def remove_rematch_buttons(pair_key: Tuple[int, int]):
    if pair_key in rematch_messages:
        for player_id, message_id in rematch_messages[pair_key].items():
            try:
                await router.bot.edit_message_reply_markup(
                    chat_id=player_id,
                    message_id=message_id,
                    reply_markup=None
                )
            except Exception:
                pass


async def cancel_rematch_after_timeout(pair_key: Tuple[int, int]):
    await asyncio.sleep(20)
    
    if pair_key in rematch_waiting:
        keyboard = create_main_keyboard()

        await remove_rematch_buttons(pair_key)
        
        min_id, max_id = pair_key
        for user_id in [min_id, max_id]:
            await router.bot.send_message(
                user_id,
                "⏰ Время ожидания реванша истекло. Реванш отменен.",
                reply_markup=keyboard
            )
        
        if pair_key in rematch_waiting:
            del rematch_waiting[pair_key]
        if pair_key in rematch_messages:
            del rematch_messages[pair_key]
        if pair_key in rematch_levels:
            del rematch_levels[pair_key]
        if pair_key in rematch_timers:
            del rematch_timers[pair_key]

async def offer_rematch(player1: Player, player2: Player):
    pair_key = get_pair_key(player1.user_id, player2.user_id)
    key = f"{pair_key[0]}_{pair_key[1]}"
    
    if player1.preferred_level and player1.preferred_level == player2.preferred_level:
        rematch_levels[pair_key] = player1.preferred_level

    keyboard = create_rematch_keyboard(key, accept=False)
    
    if pair_key not in rematch_messages:
        rematch_messages[pair_key] = {}
    
    for player in [player1, player2]:
        msg = await router.bot.send_message(
            player.user_id,
            "Хотите взять реванш?",
            reply_markup=keyboard
        )
        rematch_messages[pair_key][player.user_id] = msg.message_id
    
    timer_task = asyncio.create_task(cancel_rematch_after_timeout(pair_key))
    rematch_timers[pair_key] = timer_task

@router.callback_query(F.data.startswith("rematch:"))
async def process_rematch_request(callback: CallbackQuery):
    _, key = callback.data.split(":")
    min_id, max_id = map(int, key.split("_"))
    user_id = callback.from_user.id
    
    if not await validate_rematch_participant(callback, min_id, max_id):
        return
    
    pair_key = (min_id, max_id)
    
    if pair_key not in rematch_waiting:
        rematch_waiting[pair_key] = set()
    
    if user_id in rematch_waiting[pair_key]:
        await callback.answer("Вы уже согласились на реванш. Ожидаем ответа соперника.")
        return
    
    rematch_waiting[pair_key].add(user_id)
    await callback.answer("Запрос на реванш отправлен!")
    
    other_player_id = get_other_player_id(pair_key, user_id)
    
    await remove_rematch_buttons(pair_key)
    
    if len(rematch_waiting[pair_key]) == 1:
        user = await router.bot.get_chat(user_id)
        display_name = user.username or user.first_name or f"Игрок {user_id}"
        
        keyboard = create_rematch_keyboard(key, accept=True)
        
        msg = await router.bot.send_message(
            other_player_id,
            f"🔄 {display_name} хочет взять реванш! Принять?",
            reply_markup=keyboard
        )
        
        if pair_key not in rematch_messages:
            rematch_messages[pair_key] = {}
        rematch_messages[pair_key][other_player_id] = msg.message_id
    
    if rematch_waiting[pair_key] == {min_id, max_id}:
        if pair_key in rematch_timers:
            rematch_timers[pair_key].cancel()
            del rematch_timers[pair_key]
        
        del rematch_waiting[pair_key]
        if pair_key in rematch_messages:
            del rematch_messages[pair_key]
        
        await start_new_match(min_id, max_id)


async def start_new_match(user_id1: int, user_id2: int):
    from .match import start_match

    pair_key = get_pair_key(user_id1, user_id2)
    
    saved_level = rematch_levels.get(pair_key)
    
    if saved_level is None:
        saved_level = "easy"
    
    user1 = await router.bot.get_chat(user_id1)
    user2 = await router.bot.get_chat(user_id2)
    
    player1 = Player(
        user_id=user_id1,
        username=user1.username,
        first_name=user1.first_name,
        rating=await get_player_rating(user_id1),
        preferred_level=saved_level
    )
    
    player2 = Player(
        user_id=user_id2,
        username=user2.username,
        first_name=user2.first_name,
        rating=await get_player_rating(user_id2),
        preferred_level=saved_level
    )
    
    player1.username = user1.username
    player1.first_name = user1.first_name
    
    player2.username = user2.username
    player2.first_name = user2.first_name
    
    if saved_level:
        if not MatchFactory._questions:
            MatchFactory.load_questions()
            
        if saved_level not in MatchFactory._questions or not MatchFactory._questions[saved_level]:
            await send_no_questions_message([user_id1, user_id2], saved_level)
            return
        seen1 = await fetch_seen_question_ids(user_id1, saved_level)
        seen2 = await fetch_seen_question_ids(user_id2, saved_level)
        all_seen = seen1.union(seen2)
        
        available_questions = [q for q in MatchFactory._questions[saved_level] 
                              if q["id"] not in all_seen]
        
        if not available_questions:
            await send_no_questions_message([user_id1, user_id2], saved_level)
            return

    for user_id in [user_id1, user_id2]:
        await router.bot.send_message(
            user_id,
            "🔄 Оба игрока согласились на реванш! Начинаем новый поединок."
        )
    
    await start_match(player1, player2)


@router.callback_query(F.data.startswith("decline_rematch:"))
async def process_decline_rematch(callback: CallbackQuery):
    _, key = callback.data.split(":")
    min_id, max_id = map(int, key.split("_"))
    user_id = callback.from_user.id
    
    if not await validate_rematch_participant(callback, min_id, max_id):
        return
    
    pair_key = (min_id, max_id)
    
    if pair_key in rematch_timers:
        rematch_timers[pair_key].cancel()
        del rematch_timers[pair_key]
    
    other_player_id = get_other_player_id(pair_key, user_id)

    await remove_rematch_buttons(pair_key)
    
    user = await router.bot.get_chat(user_id)
    display_name = user.username or user.first_name or f"Игрок {user_id}"
    
    keyboard = create_main_keyboard()
    
    await router.bot.send_message(
        user_id,
        "Вы отказались от реванша.",
        reply_markup=keyboard
    )
    
    await router.bot.send_message(
        other_player_id,
        f"🚫 {display_name} отказался от реванша.",
        reply_markup=keyboard
    )
    
    if pair_key in rematch_waiting:
        del rematch_waiting[pair_key]
    if pair_key in rematch_messages:
        del rematch_messages[pair_key]
    if pair_key in rematch_levels:
        del rematch_levels[pair_key]
    
    await callback.answer("Вы отказались от реванша")


async def send_no_questions_message(user_ids: List[int], level: str):
    standard_keyboard = create_no_questions_keyboard()
    for user_id in user_ids:
        await router.bot.send_message(
            user_id,
            f"❗ Не удалось найти задачу на уровне \"{LEVEL_NAMES.get(level, level)}\", доступную для обоих игроков.\n"
            f"Выберите другой уровень или присоединитесь к бою снова.",
            reply_markup=standard_keyboard
        )