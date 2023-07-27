from .main import STW


async def setup(bot):
    cog = STW(bot)
    await bot.add_cog(cog)
