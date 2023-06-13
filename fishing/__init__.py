from .main import Fishing


async def setup(bot):
    bot.add_cog(Fishing(bot))
