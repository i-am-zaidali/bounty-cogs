import asyncio

from .main import SFOffline


async def setup(bot):
    cog = SFOffline(bot)
    await bot.add_cog(cog)
    asyncio.create_task(cog.build_cache())
