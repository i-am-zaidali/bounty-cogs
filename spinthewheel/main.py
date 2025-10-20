import asyncio
import functools
import logging
import random
import re
import typing
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from .views import Paginator, WheelSource
from .wheel import draw_still_wheel, get_animated_wheel

log = logging.getLogger("red.bounty.stw")

RARITY_WEIGHTS = {"common": 5, "rare": 2, "legendary": 1}
WEIGHTS_RARITY = {5: "common", 2: "rare", 1: "legendary"}


class STW(commands.Cog):
    """Spin the wheel and win prizes"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.tasks = []
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(wheels={})

    @staticmethod
    def get_random_colors(n):
        for i in range(n):
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            yield (r, g, b)

    @staticmethod
    def get_current_week_range():
        # yield every date object of the current week
        today = date.today()
        start = today - timedelta(days=today.weekday())
        for i in range(7):
            yield start + timedelta(days=i)

    @commands.group(name="spinthewheel", aliases=["stw"], invoke_without_command=True)
    @commands.guild_only()
    async def stw(
        self,
        ctx: commands.Context,
        wheel: typing.Optional[str] = commands.parameter(
            converter=str.lower, default=None
        ),
    ):
        """Spin the wheel and win prizes"""

        if not wheel or not (
            items := (await self.config.guild(ctx.guild).wheels()).get(wheel)
        ):
            await ctx.send(
                (f"No wheel called **__{wheel}__** exists. " if wheel else "")
                + "Please send a list of items below in the form: `itemName:rarity` or write `cancel` to end this.\n```py\nitem1:common\nitem2:rare\nitem3:legendary\n```"
            )
            try:
                msg = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.author == ctx.author
                    and m.channel == ctx.channel
                    and (
                        "cancel" in m.content
                        or re.match(
                            r"(?P<name>\w+):(?P<rarity>common|rare|legendary)",
                            m.content,
                        )
                    ),
                    timeout=180,
                )

            except asyncio.TimeoutError:
                return await ctx.send("You took too long to respond")

            if msg.content.startswith("cancel"):
                return await ctx.send("Cancelled")

            items = {
                x[0]: RARITY_WEIGHTS[x[1]]
                for x in re.findall(
                    r"(?P<name>\w+):(?P<rarity>common|rare|legendary)", msg.content
                )
            }

        if not len(items) >= 2:
            return await ctx.send("There must be at least 2 items to spin the wheel")

        # Calculate the width and height based on the number of items and the length of the biggest name
        max_name_length = max(len(item) for item in items)
        wheel_size = min(len(items) * 150, 1500)
        width = wheel_size + max_name_length * 10
        height = wheel_size

        message = await ctx.send("Spinning the wheel...")

        # async def callback(task: asyncio.Future[Tuple[BytesIO, str]]):
        #     try:
        #         exc = task.exception()
        #     except asyncio.CancelledError:
        #         return await ctx.send(
        #             "The image creation task seems to have been cancelled. Try running the command again."
        #         )
        #     if exc:
        #         log.exception("An error occurred while creating the image", exc_info=exc)
        #         return await ctx.send(
        #             f"An error occurred while spinning the wheel: `{exc}`. Check logs for more info."
        #         )
        #     img, selected = task.result()
        #     async with self.config.user(user).inventory() as inventory:
        #         inventory.setdefault(selected, 0)
        #         inventory[selected] += 1
        #     await message.delete()
        #     await ctx.send(
        #         f"{user.mention} won `{selected}`. It has been added to their inventory and they can check with `{ctx.clean_prefix}inventory`",
        #         file=discord.File(img, "wheel.gif"),
        #     )
        #     self.tasks.remove(task)

        with ProcessPoolExecutor() as pool:
            img, selected = await asyncio.get_event_loop().run_in_executor(
                pool,
                functools.partial(
                    get_animated_wheel,
                    bundled_data_path(self),
                    list(
                        (isinstance(items, dict) and items.items())
                        or dict.fromkeys(items, 5).items()
                    ),
                    list(self.get_random_colors(len(items))),
                    width,
                    height,
                    30,
                ),
            )
            await message.delete()
            msg = await ctx.send(
                file=discord.File(img, "wheel.gif"),
            )
            await asyncio.sleep(30 * 0.06)
            await msg.edit(content=f"`{selected}` was chosen")
            # fut.add_done_callback(lambda x: asyncio.create_task(callback(x)))
            # self.tasks.append(fut)

    @stw.group(name="wheel")
    @commands.admin_or_permissions(manage_guild=True)
    async def stw_wheel(self, ctx: commands.Context):
        """Manage the wheel"""

    @stw_wheel.command(name="create", aliases=["add", "+", "new"])
    async def stw_wheel_create(
        self,
        ctx: commands.Context,
        name: str = commands.parameter(converter=str.lower),
    ):
        """Create a new wheel"""
        async with self.config.guild(ctx.guild).wheels() as wheels:
            if name in wheels:
                return await ctx.send("A wheel with that name already exists")

            wheels[name] = {}
            await ctx.tick()

    @stw_wheel.command(name="delete", aliases=["remove", "-", "del"])
    async def stw_wheel_delete(
        self, ctx: commands.Context, name: str = commands.parameter(converter=str.lower)
    ):
        """Delete a wheel and it's items"""
        async with self.config.guild(ctx.guild).wheels() as wheels:
            if name not in wheels:
                return await ctx.send("A wheel with this name does not exist.")

            del wheels[name]
            await ctx.tick()

    @stw_wheel.command(name="list")
    async def stw_wheel_list(self, ctx: commands.Context):
        """List all the wheels"""
        wheels: dict[str, dict[str, int]] = await self.config.guild(ctx.guild).wheels()
        if not wheels:
            return await ctx.send("There are no wheels to preview")
        source = WheelSource(wheels, WEIGHTS_RARITY)
        paginator = Paginator(source, use_select=True)
        await paginator.start(ctx)

    @stw_wheel.group(name="item", aliases=["items"])
    async def stw_wheel_item(self, ctx: commands.Context):
        """Manage items in the wheel"""

    @stw_wheel_item.command(name="clear")
    @commands.admin_or_permissions(manage_guild=True)
    async def stw_clearitems(
        self,
        ctx: commands.Context,
        wheel: str = commands.parameter(converter=str.lower),
    ):
        """Clear all items from the wheel"""
        async with self.config.guild(ctx.guild).wheels() as wheels:
            if wheel not in wheels:
                return await ctx.send("A wheel with this name does not exist.")
            wheels[wheel] = {}
            await ctx.tick()

    @stw_wheel_item.command(name="create", aliases=["add", "+", "new"])
    @commands.admin_or_permissions(manage_guild=True)
    async def stw_ci(
        self,
        ctx: commands.Context,
        wheel: str = commands.parameter(converter=str.lower),
        rarity: typing.Literal["rare", "common", "legendary"] = "common",
        *,
        item: str = commands.parameter(converter=str.lower),
    ):
        """Add an item to the wheel"""
        async with self.config.guild(ctx.guild).wheels() as wheels:
            if wheel not in wheels:
                return await ctx.send("A wheel with this name does not exist.")
            items: dict[str, str] = wheels[wheel]
            if len(items) == 25:
                return await ctx.send(
                    "There are already 25 items on the wheel. Cannot add more."
                )
            if item in items:
                return await ctx.send("That item is already on the wheel")

            items[item] = RARITY_WEIGHTS[rarity]
            await ctx.tick()
            max_name_length = max(len(item) for item in items)
            wheel_size = min(len(items) * 150, 1500)
            width = wheel_size + max_name_length * 10
            height = wheel_size
            await ctx.send(
                "Here's a preview of the wheel: ",
                file=discord.File(
                    await asyncio.to_thread(
                        draw_still_wheel,
                        bundled_data_path(self),
                        list(items.items()),
                        list(self.get_random_colors(len(items))),
                        width,
                        height,
                    ),
                    "wheel.png",
                ),
            )

    @stw_wheel_item.command(name="delete", aliases=["remove", "-", "del"])
    @commands.admin_or_permissions(manage_guild=True)
    async def stw_di(
        self,
        ctx: commands.Context,
        wheel: str = commands.parameter(converter=str.lower),
        *,
        item: str = commands.parameter(converter=str.lower),
    ):
        """Remove an item from the wheel"""
        async with self.config.guild(ctx.guild).wheels() as wheels:
            if wheel not in wheels:
                return await ctx.send("A wheel with this name does not exist.")
            items: dict[str, str] = wheels[wheel]
            if item not in items:
                return await ctx.send("There are no items to remove")
            del items[item]
            await ctx.tick()
            if items:
                return
            max_name_length = max(len(item) for item in items)
            wheel_size = min(len(items) * 150, 1500)
            width = wheel_size + max_name_length * 10
            height = wheel_size
            await ctx.send(
                "Here's a preview of the wheel: ",
                file=discord.File(
                    await asyncio.to_thread(
                        draw_still_wheel,
                        bundled_data_path(self),
                        list(items.items()),
                        list(self.get_random_colors(len(items))),
                        width,
                        height,
                    ),
                    "wheel.png",
                ),
            )

    @stw.command(name="preview")
    @commands.admin_or_permissions(manage_guild=True)
    async def stw_preview(
        self,
        ctx: commands.Context,
        wheel: str = commands.parameter(converter=str.lower),
    ):
        """Preview the wheel"""
        wheels = await self.config.guild(ctx.guild).wheels()
        if wheel not in wheels:
            return await ctx.send("There are no wheels to preview")
        items = wheel.get(wheel)
        if not items:
            return await ctx.send("There are no items on the wheel")
        if not len(items) >= 2:
            return await ctx.send("There must be at least 2 items to preview the wheel")
        max_name_length = max(len(item) for item in items)
        wheel_size = min(len(items) * 150, 1500)
        width = wheel_size + max_name_length * 10
        height = wheel_size
        await ctx.send(
            "Here's a preview of the wheel: ",
            file=discord.File(
                await asyncio.to_thread(
                    draw_still_wheel,
                    bundled_data_path(self),
                    list(items.items()),
                    list(self.get_random_colors(len(items))),
                    width,
                    height,
                ),
                "wheel.png",
            ),
        )

    @stw_wheel_item.command(name="list")
    @commands.admin_or_permissions(manage_guild=True)
    async def stw_li(
        self,
        ctx: commands.Context,
        wheel: str = commands.parameter(converter=str.lower),
    ):
        """List all the items on the wheel"""
        wheels: dict[str, dict[str, int]] = await self.config.guild(ctx.guild).wheels()
        if wheel not in wheels:
            return await ctx.send("There are no wheels to preview")
        wheel = {wheel: wheels[wheel]}
        source = WheelSource(wheel, WEIGHTS_RARITY)
        paginator = Paginator(source, use_select=True)
        await paginator.start(ctx)
