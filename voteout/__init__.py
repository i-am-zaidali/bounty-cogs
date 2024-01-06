from .main import Voteout


async def setup(bot):
    await bot.add_cog(Voteout(bot))
