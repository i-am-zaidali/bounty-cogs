from .main import ChannelTimezone


async def setup(bot):
    await bot.add_cog(ChannelTimezone(bot))
