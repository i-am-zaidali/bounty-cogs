from .main import DeleteCounter
 
async def setup(bot):
    cog = DeleteCounter(bot)
    await bot.add_cog(cog)
    