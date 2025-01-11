import io
import typing

import discord
from PIL import Image
from redbot.core import commands
from redbot.core.bot import Red


class Dimensions(commands.Converter):
    def __init__(
        self, width: typing.Optional[int] = None, height: typing.Optional[int] = None
    ):
        self.width = width
        self.height = height

    async def convert(self, ctx: commands.Context, argument: str) -> "Dimensions":
        sep = " "
        if "," in argument:
            sep = ","
        elif "x" in argument:
            sep = "x"
        x, y = argument.split(sep)
        return Dimensions(int(x), int(y))


async def get_image(ctx: commands.Context):
    if not ctx.message.attachments:
        raise commands.BadArgument("No image attached")
    return Image.open(io.BytesIO(await ctx.message.attachments[0].read()))


class ImageUtils(commands.Cog):
    """Image Utilities

    Currently only supports upscaling and downscaling lol"""

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command(name="upscale")
    async def upscale_image(
        self,
        ctx: commands.Context,
        *,
        to_size: typing.Optional[Dimensions],
    ):
        """Upscale an image

        This command will upscale an image to the specified size
        If no size is provided, the bot will increrase the bigger side to 1024 and then increase the other side relatively to maintain aspect ratio"""

        # increase one side to 1024 and then increase the other relatively to maintain aspect ratio if the dimensions are default
        new_size = 1024
        image = await get_image(ctx)
        if to_size is None:
            if image.width > image.height:
                to_size = Dimensions(
                    new_size, int(new_size * image.height / image.width)
                )
            else:
                to_size = Dimensions(
                    int(new_size * image.width / image.height), new_size
                )

        image = image.resize((to_size.width, to_size.height), Image.Resampling.NEAREST)
        with io.BytesIO() as buffer:
            image.save(buffer, "PNG")
            buffer.seek(0)
            await ctx.reply(
                file=discord.File(buffer, filename="upscaled.png"), mention_author=False
            )

    @commands.command(name="downscale")
    async def downscale_image(
        self,
        ctx: commands.Context,
        *,
        to_size: typing.Optional[Dimensions],
    ):
        """Downscale an image

        This command will downscale an image to the specified size
        If no size is provided, the bot will decrease the bigger side to 512 and then increase the other side relatively to maintain aspect ratio"""

        # decrease one side to 512 and then increase the other relatively to maintain aspect ratio if the dimensions are default
        new_size = 512
        image = await get_image(ctx)
        if to_size is None:
            if image.width > image.height:
                to_size = Dimensions(
                    new_size, int(new_size * image.height / image.width)
                )
            else:
                to_size = Dimensions(
                    int(new_size * image.width / image.height), new_size
                )

        image = image.resize((to_size.width, to_size.height), Image.Resampling.NEAREST)
        with io.BytesIO() as buffer:
            image.save(buffer, "PNG")
            buffer.seek(0)
            await ctx.reply(
                file=discord.File(buffer, filename="downscaled.png"),
                mention_author=False,
            )
