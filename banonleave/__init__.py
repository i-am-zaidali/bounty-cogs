from .main import BanOnLeave

async def setup(bot):
    cog = BanOnLeave(bot)
    bot.add_cog(cog)