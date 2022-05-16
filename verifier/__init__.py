from .main import Verifier

async def setup(bot):
    cog = Verifier(bot)
    bot.add_cog(cog)
    await cog.build_cache()