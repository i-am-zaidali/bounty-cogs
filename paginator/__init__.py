from .main import Paginator


async def setup(bot):
    cog = Paginator(bot)
    await bot.add_cog(cog)
