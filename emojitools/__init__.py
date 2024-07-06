from .main import EmojiTools


async def setup(bot):
    await bot.add_cog(EmojiTools(bot))
