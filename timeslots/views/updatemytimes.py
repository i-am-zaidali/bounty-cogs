import asyncio
import datetime
import re
import typing

import discord
import discord.ui
from redbot.core.bot import Red

from ..common.models import DAYS
from ..common.timeslotgen import TimeSlotsGenerator
from ..common.utils import dates_iter
from .utilviews import SelectView

if typing.TYPE_CHECKING:
    from ..main import TimeSlots


class UpdateMyTimes(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"TIMESLOTS_UPDATEMYTIMES",
):
    def __init__(self):
        button = discord.ui.Button(
            style=discord.ButtonStyle.blurple,
            label="Update my times",
            custom_id="TIMESLOTS_UPDATEMYTIMES",
        )
        super().__init__(button)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        button: discord.ui.Button,
        match: re.Match[str],
    ):
        return cls()

    async def callback(self, interaction: discord.Interaction[Red]):
        cog = typing.cast("TimeSlots", interaction.client.get_cog("TimeSlots"))
        conf = cog.db.get_conf(interaction.guild.id)
        await interaction.response.defer()
        if interaction.message.id != conf.slot_selection_message:
            message = ""
            channel = interaction.guild.get_channel(conf.slot_selection_channel)
            if channel:
                confmessage = channel.get_partial_message(conf.slot_selection_message)
                message += f"The new one can be found at {confmessage.jump_url}"

            else:
                message += "Please ask the admins to set up a new one with the command `[p]timeslots selection channel <channel>`"

            await interaction.followup.send(
                f"This menu has been disabled. {message}", ephemeral=True
            )
            return await interaction.delete_original_response()

        user = conf.get_user(interaction.user.id)
        allowed_to_interact = [interaction.user.id]
        day_select = SelectView(
            allowed_to_interact,
            select_placeholder="Select the day you want to update",
            options=[
                discord.SelectOption(
                    label=date.strftime("%A %m/%d/%Y"), value=str(date.weekday())
                )
                for i, date in enumerate(
                    dates_iter(datetime.datetime.now(tz=datetime.timezone(conf.utcoffset)).date(), conf.next_chart_reset)
                )
            ],
            deselect_placeholder="",  # won't be used
            min_select=1,
            max_select=1,
        )
        await interaction.followup.send(view=day_select, ephemeral=True)

        if await day_select.wait():
            await interaction.followup.send(
                "You took too long to respond. Cancelling!", ephemeral=True
            )
            return

        day = DAYS(int(day_select.selected.pop()))

        time_select = SelectView(
            allowed_to_interact,
            select_placeholder="Select the time you want to reserve",
            options=[
                discord.SelectOption(label=f"{hour:02d}:00", value=str(hour))
                for hour in range(24)
                # if hour not in user.reserved_times.get(day, [])
            ],
            preselected=map(str, user.reserved_times.get(day, [])),
            deselect_placeholder="Select the time you want to remove",
            min_select=1,
            allow_empty_submit=True,
        )

        await day_select.final_interaction.edit_original_response(view=time_select)

        if await time_select.wait():
            await interaction.followup.send(
                "You took too long to respond. Cancelling!", ephemeral=True
            )
            return

        times = sorted(
            map(int, time_select.selected),
        )

        if set(times) == set(user.reserved_times.get(day, [])):
            return

        user.reserved_times[day] = times
        cog.save()

        await interaction.edit_original_response(
            content="Please wait...\nGenerating the new timeslots chart. This may take a while.",
            attachments=[],
            view=None,
        )

        timeslots = {uid: data.reserved_times for uid, data in conf.users.items()}

        io = await asyncio.to_thread(
            TimeSlotsGenerator(cog, interaction.guild).get_colored_organized_chart,
            timeslots,
        )

        await interaction.edit_original_response(
            content=f"## Time Slot Selection for the week {conf.started_on.strftime('%A %m/%d/%Y')} to {conf.next_chart_reset.strftime('%A %m/%d/%Y')}",
            attachments=[discord.File(io, "timeslots.png")],
            view=self.view,
        )
