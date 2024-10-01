import functools
import re
import typing

import discord
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils.views import ConfirmView
from tabulate import tabulate

from ..common.utils import (
    chunks,
    embed_metadata_into_url,
    extract_metadata_from_url,
)
from .paginator import CloseButton
from .viewdisableontimeout import (
    ViewDisableOnTimeout,
    disable_items,
    enable_items,
)

if typing.TYPE_CHECKING:
    from ..main import MissionChiefMetrics

__all__ = [
    "InvalidStats",
    "AddVehicles",
    "IgnoreStats",
    "RejectStats",
    "MergeStats",
    "ViewStats",
]


def extract_member_from_description(guild: discord.Guild, description: str):
    return guild.get_member(
        description.splitlines()[1].split()[0].lstrip("<@!").rstrip(">")
    )


async def interaction_check(interaction: discord.Interaction[Red]) -> bool:
    guild = interaction.guild
    cog = interaction.client.get_cog("MissionChiefMetrics")
    if not cog:
        await interaction.response.send_message(
            "The MissionChiefMetrics cog isn't loaded.",
            ephemeral=True,
        )
        return False

    if not await interaction.client.is_mod(
        interaction.user
    ) and interaction.user.id not in (
        guild.owner_id,
        *interaction.client.owner_ids,
    ):
        await interaction.response.send_message(
            "You aren't allowed to interact with this.", ephemeral=True
        )
        return False

    return True


class AddWhichVehiclesView(ViewDisableOnTimeout):
    def __init__(self, unknown_vehicles: list[str], **kwargs):
        self._kwargs = kwargs
        super().__init__(timeout=60, **kwargs)
        self.unknown_vehicles = unknown_vehicles
        for ind, vehicles in enumerate(chunks(unknown_vehicles, 25), 1):
            select = discord.ui.Select(
                custom_id=f"_add_select_{ind}",
                placeholder="Select the vehicles you want to add:",
                min_values=1,
                max_values=len(vehicles),
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle)
                    for vehicle in vehicles
                ],
            )
            self.add_item(select)
            select.callback = functools.partial(self.callback, select)

    @discord.ui.button(label="Add All", style=discord.ButtonStyle.green, row=5)
    async def butt_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.selected = self.unknown_vehicles.copy()
        await interaction.response.send_message(
            "Added all vehicles to allowed vehicles"
        )
        self.stop()

    async def callback(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        await interaction.response.send_message(
            f"Added {cf.humanize_list(select.values)} to allowed vehicles"
        )
        self.selected = select.values
        self.stop()


class SelectWhichVehicleToMergeWithView(ViewDisableOnTimeout):
    def __init__(
        self,
        vehicles: list[str],
        unknown_vehicles: list[str],
        stats: dict[str, int],
        vehicle: str,
        **kwargs,
    ):
        self._kwargs = kwargs
        super().__init__(timeout=60, **kwargs)
        self.stats = stats
        self.unknown_vehicles = unknown_vehicles
        self.selected = vehicle
        self.generate_selects(vehicles)

    def generate_selects(self, vehicles: list[str]):
        for ind, vehicles in enumerate(chunks(vehicles, 25), 1):
            select = discord.ui.Select(
                custom_id=f"_merge_select_{ind}",
                placeholder="Select the vehicles you want to merge:",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle)
                    for vehicle in vehicles
                ],
            )
            self.add_item(select)
            select.callback = functools.partial(self.callback, select)

    async def callback(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        self.unknown_vehicles.remove(self.selected)
        self.stats[select.values[0]] = self.stats.pop(self.selected)
        view = SelectUnknownVehicleView(
            self.unknown_vehicles, self.stats, **self._kwargs
        )
        await interaction.response.edit_message(
            content="Please select the vehicle you want to merge with another:",
            view=view,
        )
        await interaction.followup.send(
            f"Successfully merged {self.selected} with {select.values[0]}"
        )


class SelectUnknownVehicleView(ViewDisableOnTimeout):
    def __init__(
        self, unknown_vehicles: list[str], stats: dict[str, int], **kwargs
    ):
        self._kwargs = kwargs
        super().__init__(timeout=60, **kwargs)
        self.stats = stats
        self.unknown_vehicles = unknown_vehicles
        self.generate_selects()
        self.add_item(CloseButton())

    def generate_selects(self):
        for ind, vehicles in enumerate(chunks(self.unknown_vehicles, 25), 1):
            select = discord.ui.Select(
                custom_id=f"_merge_select_{ind}",
                placeholder="Select the vehicles you want to merge:",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle)
                    for vehicle in vehicles
                ],
            )
            self.add_item(select)
            select.callback = functools.partial(self.callback, select)

    async def callback(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        cog: MissionChiefMetrics = interaction.client.get_cog(
            "MissionChiefMetrics"
        )
        conf = cog.db.get_conf(interaction.guild)
        view = SelectWhichVehicleToMergeWithView(
            conf.vehicles,
            self.unknown_vehicles,
            self.stats,
            select.values,
            **self._kwargs,
        )
        await interaction.response.edit_message(
            content="Please select the vehicle you want to merge with:",
            view=view,
        )
        self.stop()


class AddVehicles(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_IS_ADD_VEHICLES_(?P<chanid>\d{17,20})_(?P<msgid>\d{17,20})",
):
    def __init__(
        self,
        chanid: int,
        msgid: int,
        stats: dict[str, int],
        unknown_vehicles: list[str],
        message: discord.PartialMessage,
    ):
        self.chanid = chanid
        self.msgid = msgid
        self.stats = stats
        self.unknown_vehicles: list[str] = unknown_vehicles
        self.message = message
        item = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Add Vehicles",
            custom_id=f"MCM_IS_ADD_VEHICLES_{chanid}_{msgid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        chanid, msgid = int(match.group("chanid")), int(match.group("msgid"))
        stats = extract_metadata_from_url(
            interaction.message.embeds[0].image.url
        )
        unknown: list[str] = stats.pop("unknown_vehicles", [])

        return cls(
            chanid,
            msgid,
            stats,
            unknown,
            interaction.guild.get_channel(chanid).get_partial_message(msgid),
        )

    async def callback(self, interaction: discord.Interaction[Red]):
        user = extract_member_from_description(
            interaction.guild, interaction.message.embeds[0].description
        )
        if not user:
            return await interaction.response.send_message(
                "User not found. They might have left the server"
            )
        cog: MissionChiefMetrics = interaction.client.get_cog(
            "MissionChiefMetrics"
        )
        conf = cog.db.get_conf(interaction.guild)
        view = AddWhichVehiclesView(
            self.unknown_vehicles, allowed_to_interact=[interaction.user.id]
        )
        disable_items(self.view)
        self.item.disabled = True
        await interaction.response.edit_message(view=self)
        view.message = await interaction.followup.send(
            "Please select which vehicles you want to add from the below menu: ",
            view=view,
            wait=True,
        )
        result = await view.wait()
        await view.message.delete()
        if result:
            return

        to_add = view.selected
        prev = self.unknown_vehicles.copy()
        self.unknown_vehicles = [
            vehicle
            for vehicle in self.unknown_vehicles
            if vehicle not in to_add
        ]
        async with conf:
            conf.vehicles.extend((x.lower() for x in to_add))
            conf.vehicles = list(set(conf.vehicles))
        await cog.log_new_stats(
            user,
            conf.get_member(user.id),
            self.stats,
        )
        if not self.unknown_vehicles:
            disable_items(self.view)
            await interaction.message.edit(view=self.view)
            try:
                await self.message.clear_reactions()
                await self.message.add_reaction("✅")

            except discord.HTTPException:
                pass

        else:
            new_embed = interaction.message.embeds[0]
            new_embed.description = new_embed.description.replace(
                cf.humanize_list(prev),
                cf.humanize_list(self.unknown_vehicles),
            )
            await interaction.message.edit(embed=new_embed)
        async with conf.get_member(user.id) as member:
            member.stats = self.stats
        enable_items(self.view)
        await interaction.edit_original_response(view=self.view)

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction)


class IgnoreStats(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_IS_IGNORE_(?P<chanid>\d{17,20})_(?P<msgid>\d{17,20})",
):
    def __init__(
        self,
        chanid: int,
        msgid: int,
        stats: dict[str, int],
        unknown_vehicles: list[str],
        message: discord.PartialMessage,
    ):
        self.chanid = chanid
        self.msgid = msgid
        self.stats = stats
        self.unknown_vehicles: list[str] = unknown_vehicles
        self.message = message
        item = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Ignore",
            custom_id=f"MCM_IS_IGNORE_{chanid}_{msgid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        chanid, msgid = int(match.group("chanid")), int(match.group("msgid"))
        stats = extract_metadata_from_url(
            interaction.message.embeds[0].image.url
        )
        unknown: list[str] = stats.pop("unknown_vehicles", [])

        return cls(
            chanid,
            msgid,
            stats,
            unknown,
            interaction.guild.get_channel(chanid).get_partial_message(msgid),
        )

    async def callback(self, interaction: discord.Interaction[Red]):
        message = self.message
        try:
            await message.clear_reactions()
        except discord.HTTPException:
            await interaction.response.send_message(
                "Failed to clear reactions. Please clear them manually.",
                ephemeral=True,
            )
        user = extract_member_from_description(
            interaction.guild, interaction.message.embeds[0].description
        )
        if not user:
            return await interaction.response.send_message(
                "User not found. They might have left the server"
            )
        cog: MissionChiefMetrics = interaction.client.get_cog(
            "MissionChiefMetrics"
        )
        memdata = cog.db.get_conf(interaction.guild).get_member(user)
        await cog.log_new_stats(
            user,
            await cog.config.member(user).stats(),
            self.stats,
        )
        async with memdata:
            memdata.stats = self.stats
        disable_items(self.view)
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send("Ignoring the unknown vehicles.")

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction)


class RejectStats(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_IS_REJECT_(?P<chanid>\d{17,20})_(?P<msgid>\d{17,20})",
):
    def __init__(
        self,
        chanid: int,
        msgid: int,
        stats: dict[str, int],
        unknown_vehicles: list[str],
        message: discord.PartialMessage,
    ):
        self.chanid = chanid
        self.msgid = msgid
        self.stats = stats
        self.unknown_vehicles: list[str] = unknown_vehicles
        self.message = message
        item = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Reject",
            custom_id=f"MCM_IS_REJECT_{chanid}_{msgid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        chanid, msgid = int(match.group("chanid")), int(match.group("msgid"))
        stats = extract_metadata_from_url(
            interaction.message.embeds[0].image.url
        )
        unknown: list[str] = stats.pop("unknown_vehicles", [])

        return cls(
            chanid,
            msgid,
            stats,
            unknown,
            interaction.guild.get_channel(chanid).get_partial_message(msgid),
        )

    async def callback(self, interaction: discord.Interaction[Red]):
        disable_items(self.view)
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send("Rejecting the stats.")
        try:
            await self.message.delete()
        except discord.NotFound:
            await interaction.response.send_message(
                "Message not found. It might have been deleted already."
            )

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction)


class MergeStats(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_IS_MERGE_(?P<chanid>\d{17,20})_(?P<msgid>\d{17,20})",
):
    def __init__(
        self,
        chanid: int,
        msgid: int,
        stats: dict[str, int],
        unknown_vehicles: list[str],
        message: discord.PartialMessage,
    ):
        self.chanid = chanid
        self.msgid = msgid
        self.stats = stats
        self.unknown_vehicles: list[str] = unknown_vehicles
        self.message = message
        item = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Merge",
            custom_id=f"MCM_IS_MERGE_{chanid}_{msgid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        chanid, msgid = int(match.group("chanid")), int(match.group("msgid"))
        stats = extract_metadata_from_url(
            interaction.message.embeds[0].image.url
        )
        unknown: list[str] = stats.pop("unknown_vehicles", [])

        return cls(
            chanid,
            msgid,
            stats,
            unknown,
            interaction.guild.get_channel(chanid).get_partial_message(msgid),
        )

    async def callback(self, interaction: discord.Interaction[Red]):
        org = self.stats.copy()
        view = SelectUnknownVehicleView(
            self.unknown_vehicles,
            self.stats,
            allowed_to_interact=[interaction.user.id],
        )
        member = extract_member_from_description(
            interaction.guild, interaction.message.embeds[0].description
        )
        if not member:
            return await interaction.response.send_message(
                "User not found. They might have left the server"
            )
        await interaction.defer()
        view.message = await interaction.followup.send(
            f"The options in the select menu below represent each of the unknown vehicles detected in {member.mentions}'s stats message.\n"
            f"Once clicked, this will edit to a different select menu with options to merge the selected vehicle with.\n"
            f"BE AWARE: When merging, the vehicle you select from the menu, it's stats will be replace with the stats of the vehicle you selected first.",
            view=view,
            wait=True,
        )

        await view.wait()
        if org == self.stats:
            await view.message.delete()
            return await interaction.followup.send(
                "No changes were made and the menu has timed out."
            )
        else:
            confirm = ConfirmView(
                interaction.user, timeout=60, disable_buttons=True
            )
            confirm.message = await interaction.followup.send(
                "The select menu has timed out but I detected changes were made."
                "Should I successfully merge the stats?",
                view=confirm,
                wait=True,
            )
            if await confirm.wait():
                await view.message.delete()
                return
            if not confirm.result:
                await view.message.delete()
                return await interaction.followup.send(
                    "Reverting changes made."
                )

        if not self.unknown_vehicles:
            disable_items(self.view)
            self.item.disabled = True
            await interaction.message.edit(view=self.view)
            try:
                await self.message.clear_reactions()
                await self.message.add_reaction("✅")
            except discord.HTTPException:
                await interaction.followup.send(
                    f"Failed to update the reactions on the stats message. Please clear them manually. {self.message.jump_url}"
                )

        embeds = interaction.message.embeds
        embeds[0].set_image(url=embed_metadata_into_url(self.stats))
        await interaction.edit_original_response(embeds=embeds)

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction)


class ViewStats(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_IS_VIEW_(?P<chanid>\d{17,20})_(?P<msgid>\d{17,20})",
):
    def __init__(self, chanid: int, msgid: int):
        self.chanid = chanid
        self.msgid = msgid
        item = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="View Stats",
            custom_id=f"MCM_IS_VIEW_{chanid}_{msgid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        chanid, msgid = int(match.group("chanid")), int(match.group("msgid"))
        return cls(chanid, msgid)

    async def callback(self, interaction: discord.Interaction[Red]):
        stats: dict[str, int] = extract_metadata_from_url(
            interaction.message.embeds[0].image.url
        )
        tabbed = tabulate(
            stats.items(),
            headers=["Vehicle", "Amount"],
            tablefmt="fancy_grid",
            colalign=("center", "center"),
        )
        embed = discord.Embed(
            description=cf.box(tabbed, "diff"),
            color=discord.Colour.green(),
        )
        view = ViewDisableOnTimeout(
            timeout=None, allowed_to_interact=[interaction.user.id]
        )
        view.add_item(CloseButton())
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )
        view.message = await interaction.original_response()

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction)


class InvalidStats(discord.ui.View):
    def __init__(
        self,
        message: discord.Message,
        stats: dict[str, int],
        unknown: list[str],
    ):
        super().__init__(timeout=60)
        self.add_item(
            AddVehicles(message.channel.id, message.id, stats, unknown, message)
        )
        self.add_item(
            IgnoreStats(message.channel.id, message.id, stats, unknown, message)
        )
        self.add_item(
            RejectStats(message.channel.id, message.id, stats, unknown, message)
        )
        self.add_item(
            MergeStats(message.channel.id, message.id, stats, unknown, message)
        )

    @staticmethod
    def generate_embed(
        message: discord.Message, stats: dict[str, int], vehicles: list[str]
    ):
        return (
            discord.Embed(
                title=f"Invalid Stats Posted: **__{message.jump_url}__**",
                description=f"{message.author.mention} has submitted stats for vehicles that are not in the list of allowed vehicles:\n",
                color=discord.Color.red(),
                timestamp=message.created_at,
            )
            .add_field(
                name="Unknown Vehicles",
                value="- "
                + "\n- ".join(
                    [vehicle for vehicle in stats if vehicle not in vehicles]
                ),
            )
            .add_field(
                name="Instructions: ",
                value=(
                    "Use the buttons below to decide what to do.\n\n"
                    "- `Add Vehicle` - The unknown vehicle will be \
                        added to the list of allowed vehicles\n"
                    "- `Ignore` - The unknown vehicle will be \
                        ignored and the stats will be updated\n"
                    "- `Reject` - The stats will be \
                        rejected and the message will be deleted\n"
                    "- `Merge` - You will be given a dropdown to merge \
                        the unknown vehicles with an existing vehicle\n"
                ),
            )
        )
