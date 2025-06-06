# Импорты для работы с SQLAlchemy ORM
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, func
from sqlalchemy.ext.asyncio import AsyncAttrs  # Для асинхронной работы с ORM
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"
    user_id = Column(BigInteger, primary_key=True)
    rating = Column(Integer, default=0, nullable=False)
    wins_easy = Column(Integer, default=0, nullable=False)
    wins_medium = Column(Integer, default=0, nullable=False)
    wins_hard = Column(Integer, default=0, nullable=False)
    total_games = Column(Integer, default=0, nullable=False)
    
    questions = relationship("UserQuestion", back_populates="player")
    
    def to_model(self):

        from models.player import Player as PlayerModel
        return PlayerModel(
            user_id=self.user_id,
            rating=self.rating
        )


class UserQuestion(Base):
    __tablename__ = "user_questions"
    user_id = Column(BigInteger, ForeignKey("players.user_id"), primary_key=True)
    question_id = Column(Integer, primary_key=True)
    level = Column(String, nullable=False)
    used_at = Column(DateTime, default=datetime.now)
    
    player = relationship("Player", back_populates="questions")