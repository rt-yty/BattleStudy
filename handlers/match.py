from aiogram import Router
from aiogram.types import Message
import asyncio
from typing import Dict
import time
from models import Player, Match, MatchFactory, is_correct_answer
from database import update_player_rating, increment_win_counter, increment_game_counter
from config import RATING_CHANGES, TIMEOUT_SETTINGS
from .common import (
    create_game_keyboard, 
    create_no_questions_keyboard,
)

router = Router()

active_matches: Dict[str, Match] = {}

player_matches: Dict[int, str] = {}


async def start_match(player1: Player, player2: Player):
    match = MatchFactory.create_match(player1, player2)
    
    active_matches[match.match_id] = match
 
    player_matches[player1.user_id] = match.match_id
    player_matches[player2.user_id] = match.match_id

    match.levels_chosen[player1.user_id] = player1.preferred_level
    match.levels_chosen[player2.user_id] = player2.preferred_level

    levels = list(match.levels_chosen.values())
    final_level = levels[0]
    match.level = final_level

    question_available = await MatchFactory.select_question(match)
    
    if not question_available:
        keyboard = create_no_questions_keyboard()
        
        for player in match.players:
            if player.user_id in player_matches:
                del player_matches[player.user_id]
        
        del active_matches[match.match_id]

        for player in match.players:
            await router.bot.send_message(
                player.user_id,
                f"❗ Не удалось найти задачу на уровне \"{LEVEL_NAMES.get(match.level, match.level)}\", доступную для обоих игроков.\n"
                f"Выберите другой уровень или присоединитесь к бою снова.",
                reply_markup=keyboard
            )
        
        return
    
    timeout = TIMEOUT_SETTINGS[match.level]
    
    match.timeout_task = asyncio.create_task(timeout_match(match.match_id, timeout))
    
    match.start_time = time.time()
    
    match.timeout_duration = timeout
    
    minutes = timeout // 60
    seconds = timeout % 60
    time_str = f"{minutes} мин. {seconds} сек." if minutes > 0 else f"{seconds} сек."
    
    for player in match.players:
        keyboard = create_game_keyboard()
        opponent_name = match.players[0].display_name if player.user_id != match.players[0].user_id else match.players[1].display_name

        await router.bot.send_message(
            player.user_id,
            f"🔔 Найден соперник: {opponent_name}\n\n"
            f"Уровень сложности: \"{match.level}\"\n\n"
            f"❓ Задача:\n"
            f"{match.question}\n\n"
            f"Присылайте ответы текстом. Побеждает первый, кто даст правильный.",
            reply_markup=keyboard
        )
        
        timer_msg = await router.bot.send_message(
            player.user_id,
            f"⏱ Время на ответ: {time_str}"
        )
        
        match.timer_messages[player.user_id] = timer_msg.message_id
    
    match.timer_update_task = asyncio.create_task(update_timer(match.match_id))


@router.message()
async def process_answer(message: Message):
    user_id = message.from_user.id
    
    if user_id not in player_matches:
        return
    
    match_id = player_matches[user_id]
    
    match = active_matches.get(match_id)
    
    if not match or match.answered or not match.question:
        return
    
    user_answer = message.text
    
    if is_correct_answer(user_answer, match.correct_answer):
        match.answered = True

        if match.timeout_task and not match.timeout_task.done():
            match.timeout_task.cancel()
        
        if match.timer_update_task and not match.timer_update_task.done():
            match.timer_update_task.cancel()

        winner = next(p for p in match.players if p.user_id == user_id)
        loser = next(p for p in match.players if p.user_id != user_id)
        
        level = match.level
        
        winner_rating = await update_player_rating(winner.user_id, RATING_CHANGES[level]["win"])
        loser_rating = await update_player_rating(loser.user_id, RATING_CHANGES[level]["lose"])
        
        await increment_game_counter(winner.user_id)
        await increment_game_counter(loser.user_id)
        
        await increment_win_counter(winner.user_id, level)
        
        await router.bot.send_message(
            winner.user_id,
            f"🎉 Ты выиграл! Новый рейтинг: {winner_rating}"
        )
        
        await router.bot.send_message(
            loser.user_id,
            f"Увы, проиграл. Правильный ответ: {match.correct_answer}\n"
            f"Новый рейтинг: {loser_rating}"
        )
        
        from .rematch import offer_rematch

        await offer_rematch(match.players[0], match.players[1])
        
        for player in match.players:
            if player.user_id in player_matches:
                del player_matches[player.user_id]
        
        del active_matches[match_id]
    else:
        await message.answer("Неверно. Попробуйте ещё раз!")


async def update_timer(match_id: str):
    try:
        while True:
            if match_id not in active_matches:
                return
                
            match = active_matches[match_id]
            
            if match.answered:
                return
            
            elapsed = time.time() - match.start_time
            
            remaining = max(0, match.timeout_duration - elapsed)
            
            minutes = int(remaining) // 60
            seconds = int(remaining) % 60
            time_str = f"{minutes} мин. {seconds} сек." if minutes > 0 else f"{seconds} сек."
            
            for player in match.players:
                if player.user_id in match.timer_messages:
                    try:
                        await router.bot.edit_message_text(
                            f"⏱ Осталось времени: {time_str}",
                            chat_id=player.user_id,
                            message_id=match.timer_messages[player.user_id]
                        )
                    except Exception:
                        pass
            
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


async def timeout_match(match_id: str, timeout: int):
    try:
        await asyncio.sleep(timeout)

        if match_id not in active_matches:
            return
            
        match = active_matches[match_id]
        
        if match.timer_update_task and not match.timer_update_task.done():
            match.timer_update_task.cancel()
        
        if not match.answered:
            for player in match.players:
                await router.bot.send_message(
                    player.user_id,
                    f"⏰ Время вышло! Никто не успел ответить. Поединок — ничья.\n"
                    f"Правильный ответ: {match.correct_answer}\n"
                    f"Рейтинг не изменился."
                )
            
            from .rematch import offer_rematch
            
            await offer_rematch(match.players[0], match.players[1])
            
            for player in match.players:
                if player.user_id in player_matches:
                    del player_matches[player.user_id]
            
            del active_matches[match_id]
    except asyncio.CancelledError:
        pass

async def create_match(player1: Player, player2: Player, level: str):
    
    player1.preferred_level = level
    
    player2.preferred_level = level
    
    await start_match(player1, player2)