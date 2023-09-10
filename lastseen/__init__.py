import asyncio

from .main import LastSeen


async def setup(bot):
    cog = LastSeen(bot)
    await bot.add_cog(cog)
    asyncio.create_task(cog.build_cache())
