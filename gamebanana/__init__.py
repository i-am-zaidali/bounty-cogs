from .main import GameBanana


async def setup(bot):
    cog = GameBanana(bot)
    await bot.add_cog(cog)
