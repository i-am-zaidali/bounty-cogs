import datetime
import typing
import functools

import discord
from redbot.core.bot import Red

from .viewdisableontimeout import ViewDisableOnTimeout, disable_items

if typing.TYPE_CHECKING:
    from ..main import MissionChiefMetrics

__all__ = ["ReminderDuration"]


class ReminderDuration(ViewDisableOnTimeout):
    durations = {
        "in 1 week": datetime.timedelta(weeks=1),
        "in 2 weeks": datetime.timedelta(weeks=2),
        "in 1 month": datetime.timedelta(weeks=4),
        "in 3 months": datetime.timedelta(weeks=12),
        "in 1 year": datetime.timedelta(weeks=52),
    }

    def __init__(self, trackchannel: discord.TextChannel, **kwargs):
        super().__init__(**kwargs)
        self.channel = trackchannel
        for duration in self.durations:
            self.add_item(
                butt := discord.ui.Button(
                    label=duration,
                    style=discord.ButtonStyle.secondary,
                    custom_id=duration.replace(" ", "_"),
                )
            )
            butt.callback = functools.partial(self.callback, butt)

    async def callback(
        self,
        button: discord.ui.Button["ReminderDuration"],
        interaction: discord.Interaction[Red],
    ):
        user_id = interaction.user.id
        text = f"MissionChiefMetrics REMINDER to submit your stats in {self.channel.mention}"
        jump_url = self.message.channel.jump_url
        utc_now = datetime.datetime.now(tz=datetime.timezone.utc)
        time = self.durations[button.label]
        expires_at = utc_now + time

        reminders_cog = interaction.client.get_cog("Reminders")
        repeat = reminders_cog.Repeat.from_json(
            [{"type": "sample", "value": {"days": time.days}}]
        )

        content = {
            "type": "text",
            "text": text,
        }
        await reminders_cog.create_reminder(
            user_id=user_id,
            content=content,
            jump_url=jump_url,
            created_at=utc_now,
            expires_at=expires_at,
            repeat=repeat,
        )
        disable_items(self)
        await interaction.response.edit_message(view=button.view)
        await interaction.followup.send("Created reminder!")
        self.stop()
        cog: MissionChiefMetrics = interaction.client.get_cog(
            "MissionChiefMetrics"
        )

        async with cog.db.get_conf(self.channel.guild.id).get_member(
            user_id
        ) as member:
            member.reminder_enabled = True
