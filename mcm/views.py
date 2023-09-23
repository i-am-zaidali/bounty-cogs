import functools
from typing import List, Optional

import aiohttp
import discord
from discord.interactions import Interaction
from discord.ui import Button, Modal, Select, TextInput, View, button, select
from discord.utils import maybe_coroutine
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext import menus
from tabulate import tabulate


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


def enable_items(self: View):
    for i in self.children:
        i.disabled = False


def chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


async def interaction_check(ctx: commands.Context, interaction: discord.Interaction):
    if not ctx.author.id == interaction.user.id:
        await interaction.response.send_message(
            "You aren't allowed to interact with this bruh. Back Off!", ephemeral=True
        )
        return False

    return True


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(self, **kwargs):
        self.message: Optional[discord.Message] = None
        self.ctx: Optional[commands.Context] = kwargs.pop("ctx", None)
        self.timeout_message: Optional[str] = kwargs.pop("timeout_message", None)
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)
            if self.timeout_message:
                await (self.ctx or self.message.channel).send(self.timeout_message)

        self.stop()


class PaginatorButton(Button["Paginator"]):
    def __init__(self, *, emoji=None, label=None, style=discord.ButtonStyle.green, disabled=False):
        super().__init__(style=style, label=label, emoji=emoji, disabled=disabled)


class CloseButton(Button["Paginator"]):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red, label="Close", emoji="<a:ml_cross:1050019930617155624>"
        )

    async def callback(self, interaction: discord.Interaction):
        await (self.view.message or interaction.message).delete()
        self.view.stop()


class ForwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}")

    async def callback(self, interaction: discord.Interaction):
        if self.view.current_page == await self.view.source.get_max_pages():
            self.view.current_page = 1
        else:
            self.view.current_page += 1

        await self.view.edit_message(interaction)


class BackwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}")

    async def callback(self, interaction: discord.Interaction):
        if self.view.current_page == 1:
            self.view.current_page = await self.view.source.get_max_pages()
        else:
            self.view.current_page -= 1

        await self.view.edit_message(interaction)


class LastItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = await self.view.source.get_max_pages()

        await self.view.edit_message(interaction)


class FirstItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = 1

        await self.view.edit_message(interaction)


class PageButton(PaginatorButton):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, disabled=True)

    def _change_label(self):
        self.label = f"Page {self.view.current_page}/{self.view.source._max_pages}"


class PaginatorSelect(Select["Paginator"]):
    @classmethod
    async def with_pages(cls, view: "Paginator", placeholder: str = "Select a page:"):
        pages: int
        pages: int = await view.source.get_max_pages() or 0
        if pages > 25:
            minus_diff = 0
            plus_diff = 25
            if 12 < view.current_page < pages - 25:
                minus_diff = view.current_page - 12
                plus_diff = view.current_page + 13
            elif view.current_page >= pages - 25:
                minus_diff = pages - 25
                plus_diff = pages
            options = [
                discord.SelectOption(
                    label=f"Page #{i+1}", value=i, description=f"Go to page {i+1}"
                )
                for i in range(minus_diff, plus_diff)
            ]
        else:
            options = [
                discord.SelectOption(label=f"Page #{i}", value=i, description=f"Go to page {i}")
                for i in range(1, pages + 1)
            ]

        return cls(options=options, placeholder=placeholder, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = int(self.values[0])

        await self.view.edit_message(interaction)


class Paginator(ViewDisableOnTimeout):
    def __init__(
        self,
        source: menus.PageSource,
        start_index: int = 1,
        timeout: int = 30,
        use_select: bool = False,
        extra_items: List[discord.ui.Item] = None,
    ):
        super().__init__(timeout=timeout)

        self.ctx: commands.Context
        self._source = source
        self.use_select: bool = use_select
        self.current_page: int = start_index
        self.extra_items: list[discord.ui.Item] = extra_items or []

    @property
    def source(self):
        return self._source

    async def update_buttons(self, edit=False):
        self.clear_items()
        pages = await self.source.get_max_pages() or 0
        buttons_to_add: List[Button] = (
            [FirstItemButton(), BackwardButton(), PageButton(), ForwardButton(), LastItemButton()]
            if pages > 2
            else [BackwardButton(), PageButton(), ForwardButton()]
            if pages > 1
            else []
        )
        if self.use_select and pages > 1:
            buttons_to_add.append(await PaginatorSelect.with_pages(self))

        buttons_to_add.append(CloseButton())

        for button in buttons_to_add:
            self.add_item(button)

        for item in self.extra_items:
            self.add_item(item)

        await self.update_items(edit)

    async def update_items(self, edit: bool = False):
        pages = await self.source.get_max_pages() or 0
        for i in self.children:
            if isinstance(i, PageButton):
                i._change_label()
                continue

            elif self.current_page == 1 and isinstance(i, FirstItemButton):
                i.disabled = True
                continue

            elif self.current_page == pages and isinstance(i, LastItemButton):
                i.disabled = True
                continue

            elif (um := getattr(i, "update", None)) and callable(um) and edit:
                i.update()

            i.disabled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    async def edit_message(self, inter: discord.Interaction):
        page = await self.get_page(self.current_page)

        await self.update_buttons(True)
        await inter.response.edit_message(**page)
        self.message = inter.message

    async def change_source(
        self,
        source,
        start: bool = False,
        ctx: Optional[commands.Context] = None,
        ephemeral: bool = True,
    ):
        """|coro|

        Changes the :class:`PageSource` to a different one at runtime.

        Once the change has been set, the menu is moved to the first
        page of the new source if it was started. This effectively
        changes the :attr:`current_page` to 0.

        Raises
        --------
        TypeError
            A :class:`PageSource` was not passed.
        """

        if not isinstance(source, menus.PageSource):
            raise TypeError("Expected {0!r} not {1.__class__!r}.".format(menus.PageSource, source))

        self._source = source
        self.current_page = 1
        await source._prepare_once()
        if start:
            if ctx is None:
                raise RuntimeError("Cannot start without a context object.")
            await self.start(ctx, ephemeral=ephemeral)

        return self

    async def get_page(self, page_num: int) -> dict:
        await self.update_buttons()
        try:
            page = await self.source.get_page(page_num)
        except IndexError:
            self.current_page = 0
            page = await self.source.get_page(self.current_page)
        value = await self.source.format_page(self, page)
        ret = {"view": self}
        if isinstance(value, dict):
            ret.update(value)
        elif isinstance(value, str):
            ret.update({"content": value, "embed": None})
        elif isinstance(value, discord.Embed):
            ret.update({"embed": value, "content": None})
        return ret

    async def start(self, ctx: commands.Context, ephemeral: bool = True):
        """
        Used to start the menu displaying the first page requested.

        Parameters
        ----------
            ctx: `commands.Context`
                The context to start the menu in.
        """
        await self.source._prepare_once()
        self.author = ctx.author
        self.ctx = ctx
        kwargs = await self.get_page(self.current_page)
        self.message: discord.Message = await getattr(self.message, "edit", ctx.send)(
            **kwargs, ephemeral=ephemeral
        )


def dehumanize_list(l: str):
    elements = l.split(", ")
    if len(elements) == 1:
        if " and " in l:
            prev, last = l.split(" and ")
            return [prev, last]

        else:
            return [l]

    _, elements[-1] = elements[-1].split("and ")
    return list(map(str.strip, elements))


class MergeISView(ViewDisableOnTimeout):
    def __init__(self, original_interaction: discord.Interaction):
        super().__init__(timeout=120)
        self.original_interaction = original_interaction
        self.unknown_vehicles = original_interaction.extras["unknown_vehicles"]
        for vehicle in self.unknown_vehicles:
            button = Button(
                style=discord.ButtonStyle.gray,
                label=vehicle,
                custom_id=f"_merge_{vehicle}",
                disabled=False,
            )
            button.callback = functools.partial(self.merge_button, button)
            setattr(self, f"merge_{vehicle}", button)
            self.add_item(button)

        self.add_item(CloseButton())

    async def select_callback(self, select: Select, interaction: discord.Interaction):
        prev = self.unknown_vehicles.copy()
        self.unknown_vehicles.remove(select.replaced_vehicle)
        if self.unknown_vehicles:
            new_embed = self.original_interaction.message.embeds[0]
            new_embed.description = new_embed.description.replace(
                cf.humanize_list(prev),
                cf.humanize_list(self.unknown_vehicles),
            )
            await self.original_interaction.message.edit(embed=new_embed)

        else:
            self_copy = InvalidStatsView(interaction.client)
            disable_items(self_copy)
            await self.original_interaction.message.edit(view=self_copy)
            await self.original_interaction.extras["message"].clear_reactions()

        getattr(self, f"merge_{select.replaced_vehicle}").disabled = True
        self.original_interaction.extras["vehicles_amount"][
            select.values[0]
        ] = self.original_interaction.extras["vehicles_amount"][select.replaced_vehicle]
        del self.original_interaction.extras["vehicles_amount"][select.replaced_vehicle]
        await interaction.message.delete()
        await interaction.response.send_message(
            f"Merged {select.replaced_vehicle} with {select.values[0]}"
        )
        select.view.stop()

    async def merge_button(self, button: Button, interaction: discord.Interaction):
        view = View(timeout=60)
        for ind, vehicles in enumerate(
            chunks(
                await interaction.client.get_cog("MissionChiefMetrics")
                .config.guild(interaction.guild)
                .vehicles(),
                25,
            ),
            1,
        ):
            select = Select(
                custom_id=f"_merge_select_{ind}",
                placeholder="Select a vehicle to merge with:",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle) for vehicle in vehicles
                ],
            )
            select.replaced_vehicle = button.label
            select.callback = functools.partial(self.select_callback, select)
            view.add_item(select)
        await interaction.response.send_message(
            "Select the vehicle you want to merge with from the below menu.", view=view
        )
        if await view.wait():
            await interaction.followup.send("Timed out.")
            return

        await interaction.message.edit(view=self)


class AddWhichVehiclesView(ViewDisableOnTimeout):
    def __init__(self, original_interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.original_interaction = original_interaction
        unknown = original_interaction.extras["unknown_vehicles"]
        for ind, vehicles in enumerate(chunks(unknown, 25), 1):
            select = Select(
                custom_id=f"_add_select_{ind}",
                placeholder="Select the vehicles you want to add:",
                min_values=1,
                max_values=len(vehicles),
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle) for vehicle in vehicles
                ],
            )
            setattr(
                self,
                f"select_{ind}",
                select,
            )
            self.add_item(select)
            select.callback = functools.partial(self.calback, select)

        addall_but = Button(label="Add All", custom_id="_add_all", style=discord.ButtonStyle.green)
        self.add_item(addall_but)
        addall_but.callback = functools.partial(self.but_callback, addall_but)

    async def but_callback(self, button: Button, interaction: discord.Interaction):
        self.selected = self.original_interaction.extras["unknown_vehicles"]
        await interaction.response.send_message(f"Added all vehicles to allowed vehicles")
        await interaction.message.delete()
        self.stop()

    async def calback(self, select: Select, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Added {cf.humanize_list(select.values)} to allowed vehicles"
        )
        await interaction.message.delete()
        self.selected = select.values
        self.stop()


class InvalidStatsView(View):
    def __init__(self, bot: Red):
        self.bot = bot
        self.extras: dict[int, dict] = {}
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        cog = self.bot.get_cog("MissionChiefMetrics")
        if not cog:
            await interaction.response.send_message(
                "The MissionChiefMetrics cog isn't loaded.",
                ephemeral=True,
            )
            return False

        if not await self.bot.is_mod(interaction.user) and not interaction.user.id in (
            guild.owner_id,
            *interaction.client.owner_ids,
        ):
            await interaction.response.send_message(
                "You aren't allowed to interact with this.", ephemeral=True
            )
            return False

        msg = interaction.message

        desc = msg.embeds[0].description.splitlines()

        url = desc[0].strip("**")

        unknown_vehicles = dehumanize_list(desc[3].lower())

        if self.extras.get(msg.id):
            self.extras[msg.id].update({"unknown_vehicles": dehumanize_list(desc[3])})
            interaction.extras.update(self.extras[msg.id])

        else:
            try:
                message = await commands.MessageConverter().convert(
                    await self.bot.get_context(msg), url
                )

            except commands.BadArgument:
                self_copy = InvalidStatsView(self.bot)
                disable_items(self_copy)
                await interaction.response.edit_message(view=self_copy)
                await interaction.followup.send(
                    "I can't seem to find the original stats message, so, I'm disabling this menu.",
                    ephemeral=True,
                )
                return False

            vehicles_amount: dict[str, int] = cog.parse_vehicles(message.content.lower())

            interaction.extras.update(
                {
                    "unknown_vehicles": unknown_vehicles,
                    "vehicles_amount": vehicles_amount,
                    "message": message,
                }
            )
            self.extras[msg.id] = interaction.extras

        return True

    @button(label="Add Vehicle(s)", custom_id="_add_vehicle", style=discord.ButtonStyle.green)
    async def add_vehicle(self, interaction: discord.Interaction, button: Button):
        cog = self.bot.get_cog("MissionChiefMetrics")
        assert cog is not None
        view = AddWhichVehiclesView(interaction)
        await interaction.response.send_message(
            "Please select which vehicles you want to add from the below menu: ", view=view
        )
        view.message = await interaction.original_response()
        if await view.wait():
            return

        to_add = view.selected
        prev = interaction.extras["unknown_vehicles"].copy()
        interaction.extras["unknown_vehicles"] = [
            vehicle for vehicle in interaction.extras["unknown_vehicles"] if vehicle not in to_add
        ]
        async with cog.config.guild(interaction.guild).vehicles() as vehicles:
            vehicles.extend(map(lambda x: x.lower(), to_add))
            vehicles = list(set(vehicles))
        user = interaction.extras["message"].author
        await cog.log_new_stats(
            user, await cog.config.member(user).stats(), interaction.extras["vehicles_amount"]
        )
        if not interaction.extras["unknown_vehicles"]:
            self_copy = InvalidStatsView(self.bot)
            disable_items(self_copy)
            await interaction.message.edit(view=self_copy)
            await interaction.extras["message"].clear_reactions()
            await interaction.extras["message"].add_reaction("✅")

        else:
            new_embed = interaction.message.embeds[0]
            new_embed.description = new_embed.description.replace(
                cf.humanize_list(prev),
                cf.humanize_list(interaction.extras["unknown_vehicles"]),
            )
            await interaction.message.edit(embed=new_embed)
            await cog.config.member(interaction.extras["message"].author).stats.set(
                interaction.extras["vehicles_amount"]
            )

    @button(label="Ignore", custom_id="_ignore", style=discord.ButtonStyle.blurple)
    async def ignore(self, interaction: discord.Interaction, button: Button):
        message: discord.Message = interaction.extras["message"]
        await message.clear_reactions()
        user = message.author
        cog = self.bot.get_cog("MissionChiefMetrics")
        await cog.log_new_stats(
            user, await cog.config.member(user).stats(), interaction.extras["vehicles_amount"]
        )
        await cog.config.member(user).stats.set(interaction.extras["vehicles_amount"])
        self_copy = InvalidStatsView(self.bot)
        disable_items(self_copy)
        await interaction.response.edit_message(view=self_copy)
        await interaction.followup.send("Ignoring the unknown vehicles.")

    @button(label="Reject", custom_id="_reject", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: Button):
        await interaction.extras["message"].delete()
        self_copy = InvalidStatsView(self.bot)
        disable_items(self_copy)
        await interaction.response.edit_message(view=self_copy)
        await interaction.followup.send("Rejecting the stats.")

    @button(label="Merge", custom_id="_merge", style=discord.ButtonStyle.gray)
    async def merge(self, interaction: discord.Interaction, button: Button):
        view = MergeISView(interaction)
        await interaction.response.send_message(
            f"Click the buttons below that represent each of the unknown vehicles detected in {interaction.extras['message'].author.mention}'s stats message.\n"
            f"once clicked, the button will send a select menu with options to merge the selected vehicle with.\n"
            f"BE AWARE: When merging, the vehicle you select from the menu, it's stats will be replace with the stats of the vehicle you clicked the button for.",
            view=view,
        )
        view.message = await interaction.original_response()

    @button(label="View Stats", custom_id="_view_stats", style=discord.ButtonStyle.green, row=2)
    async def view_stats(self, interaction: discord.Interaction, button: Button):
        ctx: commands.Context = await self.bot.get_context(interaction.message)
        ctx.interaction = interaction

        embed = discord.Embed(
            title=f"{interaction.extras['message'].author}'s stats",
            description=cf.box(
                tabulate(
                    interaction.extras["vehicles_amount"].items(),
                    headers=["Vehicle", "Amount"],
                    tablefmt="fancy_grid",
                    colalign=("center", "center"),
                )
            ),
        )
        await ctx.send(embed=embed)


class ClearOrNot(View):
    def __init__(self, bot: Red):
        self.bot = bot
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: Interaction) -> bool:
        cog = self.bot.get_cog("MissionChiefMetrics")
        if not cog:
            await interaction.response.send_message(
                "The MissionChiefMetrics cog isn't loaded.",
                ephemeral=True,
            )
            return False

        if not await self.bot.is_mod(interaction.user) and not interaction.user.id in (
            interaction.guild.owner_id,
            *interaction.client.owner_ids,
        ):
            await interaction.response.send_message(
                "You aren't allowed to interact with this.", ephemeral=True
            )
            return False
        self_copy = ClearOrNot(self.bot)
        disable_items(self_copy)
        await interaction.response.edit_message(view=self_copy)
        return True

    @button(label="Clear their stats", custom_id="_clear_stats", style=discord.ButtonStyle.red)
    async def clear_stats(self, interaction: discord.Interaction, button: Button):
        actual_user = int(interaction.message.embeds[0].footer.text.strip("ID: "))
        await self.bot.get_cog("MissionChiefMetrics").config.member_from_ids(
            interaction.guild.id, actual_user
        ).clear()
        await interaction.followup.send("Cleared their stats.")

    @button(label="No, let it stay", custom_id="_no_clear_stats", style=discord.ButtonStyle.green)
    async def no_clear_stats(self, interaction: discord.Interaction, button: Button):
        await interaction.followup.send("Okay, I won't clear their stats.")
