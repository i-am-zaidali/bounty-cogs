from .main import ReactRole


async def setup(bot):
    cog = ReactRole(bot)
    await bot.add_cog(cog)
