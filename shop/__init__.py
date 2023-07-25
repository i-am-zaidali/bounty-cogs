from .main import Shop


async def setup(bot):
    cog = Shop(bot)
    await bot.add_cog(cog)
