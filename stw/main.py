import asyncio
from io import BytesIO
import logging
import random
from typing import Literal, Tuple

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .views import TradeSelector
from .wheel import get_animated_wheel, draw_still_wheel

log = logging.getLogger("red.bounty.stw")


class STW(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.tasks = []
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(items=[])
        self.config.register_user(inventory={})

    @staticmethod
    def get_random_colors(n):
        for i in range(n):
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            yield (r, g, b)

    @commands.group(name="spinthewheel", aliases=["stw"], invoke_without_command=True)
    @commands.is_owner()
    async def stw(self, ctx: commands.Context, user: discord.Member):
        """Spin the wheel and win prizes"""
        items = await self.config.items()
        if not items:
            return await ctx.send("There are no items to win")

        # Calculate the width and height based on the number of items and the length of the biggest name
        max_name_length = max(len(item) for item in items)
        wheel_size = len(items) * 150
        width = wheel_size + max_name_length * 10
        height = wheel_size

        message = await ctx.send("Spinning the wheel...")

        async def callback(task: asyncio.Task[Tuple[BytesIO, str]]):
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                return await ctx.send(
                    "The image creation task seems to have been cancelled. Try running the command again."
                )
            if exc:
                log.exception("An error occurred while creating the image", exc_info=exc)
                return await ctx.send(
                    f"An error occurred while spinning the wheel: `{exc}`. Check logs for more info."
                )
            img, selected = task.result()
            async with self.config.user(user).inventory() as inventory:
                inventory.setdefault(selected, 0)
                inventory[selected] += 1
            await message.delete()
            await ctx.send(
                f"{user.mention} won `{selected}`. It has been added to their inventory and they can check with `{ctx.clean_prefix}inventory`",
                file=discord.File(img, "wheel.gif"),
            )
            self.tasks.remove(task)

        task = asyncio.create_task(
            get_animated_wheel(
                self, items, list(self.get_random_colors(len(items))), width, height, 60
            )
        )
        task.add_done_callback(lambda x: asyncio.create_task(callback(x)))
        self.tasks.append(task)

    @stw.command(name="createitem", aliases=["ci"])
    async def stw_ci(
        self,
        ctx: commands.Context,
        rarity: Literal["rare", "common", "legendary"],
        *,
        item: str = commands.parameter(converter=str.lower),
    ):
        """Add an item to the wheel"""
        async with self.config.items() as items:
            # if len(items) == 25:
            #    return await ctx.send("There are already 25 items on the wheel. Cannot add more.")
            if item in items:
                return await ctx.send("That item is already on the wheel")
            items.append(item)
            await ctx.tick()
            max_name_length = max(len(item) for item in items)
            wheel_size = len(items) * 150
            width = wheel_size + max_name_length * 10
            height = wheel_size
            await ctx.send(
                "Here's a preview of the wheel: ",
                file=discord.File(
                    draw_still_wheel(
                        self, items, list(self.get_random_colors(len(items))), width, height
                    ),
                    "wheel.png",
                ),
            )

    @stw.command(name="deleteitem", aliases=["di"])
    async def stw_di(
        self, ctx: commands.Context, *, item: str = commands.parameter(converter=str.lower)
    ):
        """Remove an item from the wheel"""
        async with self.config.items() as items:
            if not item in items:
                return await ctx.send("There are no items to remove")
            items.remove(item)
            await ctx.tick()
            await ctx.send(
                "Here's a preview of the wheel: ",
                file=discord.File(
                    draw_still_wheel(items, list(self.get_random_colors(len(items))), 500, 500),
                    "wheel.png",
                ),
            )

    @stw.command(name="listitems", aliases=["li"])
    async def stw_li(self, ctx: commands.Context):
        """List all the items on the wheel"""
        items = await self.config.items()
        if not items:
            return await ctx.send("There are no items on the wheel")
        await ctx.send("- " + "\n- ".join(items))

    @stw.command(name="steal")
    async def stw_r(
        self,
        ctx: commands.Context,
        user: discord.Member,
        amount: int,
        item: str = commands.parameter(converter=str.lower),
    ):
        """Take away a certain item from a user's inventory"""
        if user == ctx.author:
            return await ctx.send("You cannot steal from yourself")

        async with self.config.user(user).inventory() as inventory:
            if not item in inventory:
                return await ctx.send("That user does not have that item in their inventory")

            if inventory[item] < amount:
                return await ctx.send(
                    "That user does not have enough of that item in their inventory"
                )

            inventory[item] -= amount
            if inventory[item] == 0:
                del inventory[item]

            await ctx.send("Successfully stolen")

    @stw.command(name="give")
    async def stw_g(
        self,
        ctx: commands.Context,
        user: discord.Member,
        amount: int,
        item: str = commands.parameter(converter=str.lower),
    ):
        """Give a certain item to a user"""
        if user == ctx.author:
            return await ctx.send("You cannot give to yourself")

        async with self.config.user(user).inventory() as inventory:
            inventory.setdefault(item, 0)
            inventory[item] += amount

        await ctx.send("Successfully given")

    @commands.command(name="inventory", aliases=["inv"])
    async def inv(self, ctx: commands.Context, user=commands.Author):
        """View your inventory"""
        inventory = await self.config.user(user).inventory()
        if not inventory:
            return await ctx.send("You have no items in your inventory")
        existing_items = await self.config.items()
        embed = discord.Embed(
            title=f"{user.display_name}'s inventory",
            description="- "
            + "\n- ".join(
                f"{count:,} `{item}`"
                for item, count in inventory.items()
                if count != 0 and item in existing_items
            ),
        )
        await ctx.send(embed=embed)

    @commands.command(name="trade")
    async def trade(self, ctx: commands.Context, user: discord.Member):
        """Trade an item with another user"""
        if user == ctx.author:
            return await ctx.send("You cannot trade with yourself")
        inventory = await self.config.user(ctx.author).inventory()
        if not inventory:
            return await ctx.send("You have no items in your inventory")

        user_inventory = await self.config.user(user).inventory()
        if not user_inventory:
            return await ctx.send(
                "The user you want to trade with has no items in their inventory"
            )

        copy1 = inventory.copy()
        copy2 = user_inventory.copy()

        view = TradeSelector((ctx.author, inventory), (user, user_inventory))

        view.message = await ctx.send(
            "Use the buttons below to configure the trade. "
            "Each button below is an item that either you or the user you want to trade with owns, "
            "and you can click on them to add them to the trade. \n"
            "- You can also click the `All` button to add all of your items to the trade. \n"
            "- The `Reset` button will remove al your items form the trade and let you start over. \n"
            "Once you are done, click the `Confirm` button to finish the trade. \n"
            "If you want to cancel the trade, Just let it be and it will cancel itself.",
            view=view,
        )
        await view.wait()

        if copy1 == inventory and copy2 == user_inventory:
            return
