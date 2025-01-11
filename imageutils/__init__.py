from redbot.core.bot import Red

from .main import ImageUtils


async def setup(bot: Red) -> None:
    await bot.add_cog(ImageUtils(bot))
