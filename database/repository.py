# Импорты для типизации и работы с SQLAlchemy
from typing import Set, List, Tuple, Dict
from sqlalchemy import select, update, func, exists
from .connection import db_manager
from .models import Player, UserQuestion

async def init_db() -> None:
    await db_manager.init_db()

async def _ensure_player_exists(session, user_id: int) -> Player:
    stmt = select(Player).where(Player.user_id == user_id)
    result = await session.execute(stmt)
    player = result.scalar_one_or_none()
    
    if player is None:
        player = Player(user_id=user_id, rating=0)
        session.add(player)
        await session.commit()
    
    return player


async def get_player_rating(user_id: int) -> int:
    async with db_manager.session() as session:
        player = await _ensure_player_exists(session, user_id)
        return player.rating


async def update_player_rating(user_id: int, delta: int) -> int:
    async with db_manager.session() as session:
        stmt = select(exists().where(Player.user_id == user_id))
        result = await session.execute(stmt)
        exists_player = result.scalar()
        
        if not exists_player:
            player = Player(user_id=user_id, rating=max(0, delta))
            session.add(player)
            await session.commit()
            return max(0, delta)
        else:
            stmt = update(Player).where(Player.user_id == user_id).values(
                rating=func.greatest(0, Player.rating + delta)
            ).returning(Player.rating)
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar_one()


async def fetch_seen_question_ids(user_id: int, level: str) -> Set[int]:
    async with db_manager.session() as session:
        stmt = select(UserQuestion.question_id).where(
            UserQuestion.user_id == user_id,
            UserQuestion.level == level
        )
        result = await session.execute(stmt)
        return {row[0] for row in result.all()}


async def mark_question_used(user_id: int, question_id: int, level: str) -> None:
    async with db_manager.session() as session:
        # Гарантируем существование игрока в базе
        await _ensure_player_exists(session, user_id)
        
        # Проверяем, не отмечен ли уже этот вопрос как использованный
        stmt = select(exists().where(
            UserQuestion.user_id == user_id,
            UserQuestion.question_id == question_id
        ))
        result = await session.execute(stmt)
        exists_record = result.scalar()
        
        # Если запись не существует, создаем новую
        if not exists_record:
            user_question = UserQuestion(
                user_id=user_id,
                question_id=question_id,
                level=level
            )
            session.add(user_question)
            await session.commit()


async def get_leaderboard(limit: int = 10) -> List[Tuple[int, int]]:
    async with db_manager.session() as session:
        stmt = select(Player.user_id, Player.rating).order_by(
            Player.rating.desc()
        ).limit(limit)
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


async def increment_win_counter(user_id: int, level: str) -> None:
    if level not in ("easy", "medium", "hard"):
        raise ValueError(f"Неверный уровень сложности: {level}")
        
    column_name = f"wins_{level}"
    
    async with db_manager.session() as session:
        player = await _ensure_player_exists(session, user_id)
        
        setattr(player, column_name, getattr(player, column_name) + 1)
        await session.commit()


async def increment_game_counter(user_id: int) -> None:
    async with db_manager.session() as session:
        player = await _ensure_player_exists(session, user_id)
        player.total_games += 1
        await session.commit()


async def get_player_stats(user_id: int) -> Dict[str, int]:
    async with db_manager.session() as session:
        player = await _ensure_player_exists(session, user_id)
        
        return {
            "rating": player.rating,
            "wins_easy": player.wins_easy,
            "wins_medium": player.wins_medium,
            "wins_hard": player.wins_hard,
            "total_games": player.total_games
        }