from .main import MiniGames


async def setup(bot):
    await bot.add_cog(MiniGames(bot))
