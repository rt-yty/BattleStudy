import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN
from database import db_manager, init_db
from handlers import common_router, match_router, rematch_router
from models import MatchFactory


async def main():
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    dp = Dispatcher()
    
    dp.include_router(common_router)
    dp.include_router(match_router)
    dp.include_router(rematch_router)
    
    common_router.bot = bot
    match_router.bot = bot
    rematch_router.bot = bot
    
    await init_db()
    
    MatchFactory.load_questions()
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)

        await dp.start_polling(bot)
    except KeyboardInterrupt:
        from handlers.match import active_matches
        for match in active_matches.values():
            if match.timeout_task and not match.timeout_task.done():
                match.timeout_task.cancel()
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())