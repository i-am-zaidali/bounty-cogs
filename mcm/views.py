import functools
import itertools
from pprint import pprint
from typing import TYPE_CHECKING, Optional

import discord
from discord.interactions import Interaction
from discord.ui import Button, Modal, Select, TextInput, View, button, select
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext import menus
from tabulate import tabulate

if TYPE_CHECKING:
    from . import MissionChiefMetrics


def disable_items(self: View):
    for i in self.children:
        i.disabled = True

    return self


def enable_items(self: View):
    for i in self.children:
        i.disabled = False

    return self


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

    async def interaction_check(self, interaction: Interaction) -> bool:
        if (
            msg := getattr(self.ctx, "message", self.message)
        ) and interaction.user.id != msg.author.id:
            await interaction.response.send_message(
                "You aren't allowed to interact with this bruh. Back Off!", ephemeral=True
            )
            return False

        return True


class CloseButton(Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red, label="Close", emoji="<a:ml_cross:1050019930617155624>"
        )

    async def callback(self, interaction: discord.Interaction):
        await (self.view.message or interaction.message).delete()
        self.view.stop()


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


class NewCategory(ViewDisableOnTimeout):
    def __init__(self, cog: "MissionChiefMetrics", ctx: commands.Context):
        self.bot = cog.bot
        self.config = cog.config

        super().__init__(timeout=60, ctx=ctx)

        self.add_item(CloseButton())

    @button(label="Add Category", custom_id="_add_category", style=discord.ButtonStyle.green)
    async def ac_callback(self, inter: discord.Interaction, button: Button):
        modal = Modal(title="New Category", timeout=60)
        modal.add_item(
            ti := TextInput(
                label="Category Name", custom_id="_category_name", placeholder="Category Name"
            )
        )
        setattr(modal, "on_submit", functools.partial(self.modal_cb, modal))
        modal.ti = ti

        await inter.response.send_modal(modal)

    async def modal_cb(self, modal: Modal, inter: discord.Interaction):
        ti: TextInput = modal.ti
        if not ti.value.strip():
            await inter.response.send_message("You need to enter a category name.")
            return

        all_categories = await self.config.guild(inter.guild).vehicle_categories()
        if ti.value.strip().lower() in all_categories:
            return await inter.response.send_message(
                "That category already exists.", ephemeral=True
            )
        await inter.response.defer()
        await self.further_handling(inter, ti.value.strip().lower())

    async def further_handling(self, inter: discord.Interaction, category_name: str):
        all_categories = await self.config.guild(inter.guild).vehicle_categories()
        all_vehicles = await self.config.guild(inter.guild).vehicles()
        all_values_categories = list(itertools.chain.from_iterable(all_categories.values()))

        self.remaining = list(set(all_vehicles) - set(all_values_categories))
        if not self.remaining:
            await inter.followup.send(
                "There are no vehicles left to add to a category. Categories can not have common vehicles."
            )
            return

        async with self.config.guild(inter.guild).vehicle_categories() as categories:
            categories.setdefault(category_name, [])

        self.category = category_name

        view = ViewDisableOnTimeout(timeout=60, ctx=self.ctx)
        view.selected = []
        await self.get_selects(view, inter.guild)

        view.message = await inter.followup.send(
            f"Use the below selects for the purposes mentioned on their placeholders to make changes to the category: `{category_name.capitalize()}`",
            view=view,
            wait=True,
        )

        if not await view.wait():
            async with self.config.guild(inter.guild).vehicle_categories() as categories:
                if not view.selected and not categories[category_name]:
                    del categories[category_name]
                    await inter.followup.send("Cancelled.")
                    return

                else:
                    categories[category_name] = list(
                        set(categories[category_name]).difference(self.remaining)
                    )
                    categories[category_name].extend(view.selected)
                    categories[category_name] = list(set(categories[category_name]))
                    await inter.followup.send("Updated vehicles in the category.")
                    await view.message.edit(view=disable_items(view))
                    return

    async def select_cb(self, select: Select, inter: discord.Interaction):
        view = select.view
        view.selected.extend(select.values)
        view.selected = list(set(view.selected))
        for val in select.values:
            self.remaining.remove(val)

        print(self.remaining, view.selected)

        view.clear_items()
        await self.get_selects(view, inter.guild)

        await inter.response.edit_message(view=view)

        close_view = ViewDisableOnTimeout(timeout=60, ctx=self.ctx)
        close_view.add_item(CloseButton())

        close_view.message = await inter.followup.send(
            f"Currently selected vehicles: {cf.humanize_list(view.selected)}\nIf that's all, click on the close button to finish the process."
            if view.selected
            else "If that's all, click on the close button to finish the process.",
            ephemeral=True,
            view=close_view,
        )

        if await close_view.wait():
            return

        else:
            view.stop()

    async def remove_select_cb(self, select: Select, inter: discord.Interaction):
        view = select.view
        self.remaining.extend(select.values)
        self.remaining = list(set(self.remaining))
        for val in select.values:
            if val in view.selected:
                view.selected.remove(val)

        view.clear_items()
        await self.get_selects(view, inter.guild)

        await inter.response.edit_message(view=view)

        close_view = ViewDisableOnTimeout(timeout=60, ctx=self.ctx)
        close_view.add_item(CloseButton())

        close_view.message = await inter.followup.send(
            f"Currently selected vehicles to add: {cf.humanize_list(view.selected)}\nIf that's all, click on the close button to finish the process."
            if view.selected
            else "If that's all, click on the close button to finish the process.",
            ephemeral=True,
            view=close_view,
        )

        if await close_view.wait():
            return

        else:
            view.stop()

    async def get_selects(self, view: View, guild: discord.Guild):
        [
            *(
                (
                    s := Select(
                        custom_id=f"_vehicles_select_{ind}",
                        placeholder="Select the vehicles to add to the category:",
                        min_values=1,
                        max_values=len(chunk),
                        options=[
                            discord.SelectOption(label=name.capitalize(), value=name)
                            for name in chunk
                        ],
                    ),
                    setattr(s, "callback", functools.partial(self.select_cb, s)),
                    view.add_item(s),
                    pprint(s.options),
                )
                for ind, chunk in enumerate(chunks(self.remaining, 25), 1)
            ),
        ]
        options = [
            discord.SelectOption(label=name.capitalize(), value=name)
            for name in set().union(
                await self.config.guild(guild).vehicle_categories.get_attr(self.category)(),
                view.selected,
            )
            if name not in self.remaining
        ]
        if options:
            pprint(options)
            s = Select(
                custom_id="_vehicles_select_last",
                placeholder="Select the vehicles to remove from the category:",
                min_values=1,
                options=options,
                max_values=len(options),
            )
            s.callback = functools.partial(self.remove_select_cb, s)
            view.add_item(s)


class UpdateCategory(NewCategory):
    def __init__(
        self, cog: "MissionChiefMetrics", ctx: commands.Context, all_categories: list[str]
    ):
        super().__init__(cog, ctx)
        self.category_select = Select(
            custom_id="_category_select",
            placeholder="Select the category to update:",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=name.capitalize(), value=name)
                for name in all_categories
            ],
            row=1,
        )
        self.remove_item(self.children[0])
        self.add_item(self.category_select)
        setattr(
            self.category_select,
            "callback",
            functools.partial(self.cat_select_cb, self.category_select),
        )

    async def cat_select_cb(self, select: Select, inter: discord.Interaction):
        disable_items(self)
        await inter.response.edit_message(view=self)
        await self.further_handling(inter, select.values[0])
