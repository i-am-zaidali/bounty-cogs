from .main import MemberHistory


async def setup(bot):
    await bot.add_cog(MemberHistory(bot))
