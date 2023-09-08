import asyncio
import functools
import logging
import random
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from typing import Literal, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from .views import TradeSelector
from .wheel import draw_still_wheel, get_animated_wheel

log = logging.getLogger("red.bounty.stw")

RARITY_WEIGHTS = {"common": 5, "rare": 2, "legendary": 1}
WEIGHTS_RARITY = {5: "common", 2: "rare", 1: "legendary"}


class ItemFlags(commands.FlagConverter):
    name: str = commands.flag(default=lambda ctx: ctx.args[2])
    rarity: Optional[Literal["common", "rare", "legendary"]] = None


class STW(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.tasks = []
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(items={})
        self.config.register_user(
            last_spins=[date.fromtimestamp(0).toordinal(), date.fromtimestamp(0).toordinal()]
        )
        self.config.register_guild(subscriber_role=None)
        self.config.register_user(inventory={})

    async def cog_before_invoke(self, ctx: commands.Context):
        await ctx.send(
            f"`Error in command '{ctx.command.qualified_name}'. Check your console or logs for details.`"
        )
        raise ValueError("Your Mom")

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
    async def stw(self, ctx: commands.Context, user: discord.Member):
        """Spin the wheel and win prizes"""
        if random.random() <= 0.6:
            raise ValueError("Something went wrong in the command.")
        sub_role = await self.config.guild(ctx.guild).subscriber_role(default=0)
        if (
            not ctx.author.get_role(sub_role)
            and not ctx.author.guild_permissions.administrator
            and not ctx.bot.is_owner(ctx.author)
        ):
            return await ctx.send("You don't have permission to use this command")
        elif (
            not ctx.author.guild_permissions.administrator
            and not ctx.bot.is_owner(ctx.author)
            and ctx.author.get_role(sub_role)
            and user != ctx.author
        ):
            return await ctx.send("You can only spin the wheel for yourself")

        if not ctx.bot.is_owner(ctx.author):
            last_spins = await self.config.user(user).last_spins()
            this_week = list(self.get_current_week_range())
            last_spins = [date.fromordinal(x) for x in last_spins]
            spun = list(set.intersection(set(last_spins), set(this_week)))
            if len(spun) == 2:
                return await ctx.send(
                    f"{user.mention} has already claimed their two spins for this week"
                )
            elif len(spun) == 1:
                if last_spins[0] == last_spins[1]:
                    return await ctx.send(
                        f"{user.mention} has already claimed their two spins for this week"
                    )
                ind = last_spins.index(spun[0]) - 1
                last_spins[ind] = date.today()

            else:
                last_spins[0] = date.today()

            await self.config.user(user).last_spins.set([x.toordinal() for x in last_spins])

        items = await self.config.items()
        if not items:
            return await ctx.send("There are no items to win")

        # Calculate the width and height based on the number of items and the length of the biggest name
        max_name_length = max(len(item) for item in items)
        wheel_size = len(items) * 150
        wheel_size = wheel_size if wheel_size <= 1500 else 1500
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

        if random.random() < 0.2:
            await asyncio.sleep(2)
            await message.delete()
            return await ctx.send("Sorry! You didnt win anything! Better luck next time!")
        else:
            with ProcessPoolExecutor() as pool:
                img, selected = await asyncio.get_event_loop().run_in_executor(
                    pool,
                    functools.partial(
                        get_animated_wheel,
                        bundled_data_path(self),
                        list(items.items()),
                        list(self.get_random_colors(len(items))),
                        width,
                        height,
                        30,
                    ),
                )
            # selected = random.choice(items)
            async with self.config.user(user).inventory() as inventory:
                inventory.setdefault(selected, 0)
                inventory[selected] += 1
            await message.delete()
            await ctx.send(
                f"{user.mention} won `{selected}`. It has been added to their inventory and they can check with `{ctx.clean_prefix}inventory`",
                file=discord.File(img, "wheel.gif"),
            )
            # fut.add_done_callback(lambda x: asyncio.create_task(callback(x)))
            # self.tasks.append(fut)

    @stw.command(name="createitem", aliases=["ci"])
    @commands.is_owner()
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
            items[item] = RARITY_WEIGHTS[rarity]
            await ctx.tick()
            max_name_length = max(len(item) for item in items)
            wheel_size = len(items) * 150
            wheel_size = wheel_size if wheel_size <= 1500 else 1500
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

    @stw.command(name="deleteitem", aliases=["di"])
    @commands.is_owner()
    async def stw_di(
        self,
        ctx: commands.Context,
        *,
        item: str = commands.parameter(converter=str.lower),
    ):
        """Remove an item from the wheel"""
        async with self.config.items() as items:
            if not item in items:
                return await ctx.send("There are no items to remove")
            del items[item]
            await ctx.tick()
            max_name_length = max(len(item) for item in items)
            wheel_size = len(items) * 150
            wheel_size = wheel_size if wheel_size <= 1500 else 1500
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
    @commands.is_owner()
    async def stw_preview(self, ctx: commands.Context):
        """Preview the wheel"""
        items = await self.config.items()
        if not items:
            return await ctx.send("There are no items on the wheel")
        max_name_length = max(len(item) for item in items)
        wheel_size = len(items) * 150
        wheel_size = wheel_size if wheel_size <= 1500 else 1500
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

    @stw.command(name="listitems", aliases=["li"])
    @commands.is_owner()
    async def stw_li(self, ctx: commands.Context):
        """List all the items on the wheel"""
        items = await self.config.items()
        if not items:
            return await ctx.send("There are no items on the wheel")
        await ctx.send(
            "NAME: (RARITY LEVEL)\n\n- "
            + "\n- ".join(map(lambda x: f"`{x[0]}: ({WEIGHTS_RARITY[x[1]]})`", items.items()))
        )

    @stw.command(name="edititem", aliases=["ei"])
    @commands.is_owner()
    async def stw_ei(
        self,
        ctx: commands.Context,
        item: str = commands.param(converter=str.lower),
        *,
        flags: ItemFlags,
    ):
        """Edit an item on the wheel"""
        async with self.config.items() as items:
            if not item in items:
                return await ctx.send("That item is not on the wheel")
            weight = items.pop(item)
            items[flags.name] = RARITY_WEIGHTS[flags.rarity or weight]
            await ctx.tick()
            max_name_length = max(len(item) for item in items)
            wheel_size = len(items) * 150
            wheel_size = wheel_size if wheel_size <= 1500 else 1500
            width = wheel_size + max_name_length * 10
            height = wheel_size
            await ctx.send(
                "Here's a preview of the wheel: ",
                file=discord.File(
                    await asyncio.to_thread(
                        draw_still_wheel,
                        bundled_data_path(self),
                        items.items(),
                        list(self.get_random_colors(len(items))),
                        width,
                        height,
                    ),
                    "wheel.png",
                ),
            )

    @stw.command(name="steal")
    @commands.mod()
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
    @commands.mod()
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

    @stw.command(name="subscriber", aliases=["subrole"])
    @commands.is_owner()
    async def stw_sr(self, ctx: commands.Context, role: discord.Role):
        """Set the subscriber role"""
        await self.config.guild(ctx.guild).subscriber_role.set(role.id)
        await ctx.tick()

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
