from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
import asyncio
import random
import json
from datetime import datetime
from fractions import Fraction
import time

from .player import Player
from database import fetch_seen_question_ids, mark_question_used

@dataclass
class Match:
    match_id: str
    players: Tuple[Player, Player]
    levels_chosen: Dict[int, Optional[str]] = field(default_factory=dict)
    level: Optional[str] = None
    question_id: Optional[int] = None
    question: Optional[str] = None
    correct_answer: Optional[str] = None
    started_at: Optional[datetime] = None
    answered: bool = False
    timeout_task: Optional[asyncio.Task] = None
    start_time: float = field(default_factory=time.time)
    timeout_duration: int = 300
    question_messages: Dict[int, int] = field(default_factory=dict)
    timer_update_task: Optional[asyncio.Task] = None
    timer_messages: Dict[int, int] = field(default_factory=dict)


class MatchFactory:
    _match_counter: int = 0
    _questions: Dict[str, List[Dict]] = {}
    
    @classmethod
    def load_questions(cls):
        try:
            with open('questions.json', 'r', encoding='utf-8') as f:
                cls._questions = json.load(f)
        except FileNotFoundError:
            print("Error: questions.json file not found")
            cls._questions = {"easy": [], "medium": [], "hard": []}
    
    @classmethod
    def get_questions_by_level(cls, level: str) -> List[Dict]:
        if not cls._questions:
            cls.load_questions()
        return cls._questions.get(level, [])
    
    @classmethod
    def create_match(cls, player1: Player, player2: Player) -> Match:
        cls._match_counter += 1
        match_id = f"match_{cls._match_counter}"
        
        return Match(
            match_id=match_id,
            players=(player1, player2),
            levels_chosen={player1.user_id: None, player2.user_id: None}
        )
    
    @classmethod
    async def select_question(cls, match: Match) -> bool:
        if not cls._questions:
            cls.load_questions()
            
        if match.level not in cls._questions or not cls._questions[match.level]:
            return False
            
        seen1 = await fetch_seen_question_ids(match.players[0].user_id, match.level)
        seen2 = await fetch_seen_question_ids(match.players[1].user_id, match.level)
        
        all_seen = seen1.union(seen2)
        
        available_questions = [q for q in cls._questions[match.level] 
                              if q["id"] not in all_seen]
        
        if not available_questions:
            return False
            
        question = random.choice(available_questions)
        
        match.question_id = question["id"]
        match.question = question["question"]
        match.correct_answer = question["answer"]
        match.started_at = datetime.utcnow()
        
        for player in match.players:
            await mark_question_used(player.user_id, question["id"], match.level)
            
        return True


FLOAT_COMPARISON_TOLERANCE = 1e-6

def is_correct_answer(user_answer: str, correct_answer: str) -> bool:
    user_answer = user_answer.strip().lower()
    correct_answer = correct_answer.strip().lower()
    
    user_answer_normalized = user_answer.replace(',', '.')
    
    try:
        user_fraction = Fraction(user_answer_normalized)
        correct_fraction = Fraction(correct_answer)
        return user_fraction == correct_fraction
    except (ValueError, ZeroDivisionError):
        pass
    
    try:
        user_float = float(user_answer_normalized)
        correct_float = float(correct_answer)
        return abs(user_float - correct_float) < FLOAT_COMPARISON_TOLERANCE
    except ValueError:
        pass
    
    return user_answer == correct_answer