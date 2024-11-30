# Task loops can be defined here
import asyncio
import datetime
import logging

import discord
from discord.ext import tasks

from timeslots.common.timeslotgen import TimeSlotsGenerator

from ..abc import CompositeMetaClass, MixinMeta
from ..common.utils import all_min

log = logging.getLogger("red.craycogs.timeslots.tasks")


class TaskLoops(MixinMeta, metaclass=CompositeMetaClass):
    """
    Subclass all task loops in this directory so you can import this single task loop class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """

    def __init__(self, *_args):
        super().__init__(*_args)
        self.to_check: list[int] = []

    @tasks.loop(seconds=1)
    async def reset_chart(self):
        """Reset the timeslots chart every week"""
        for guild_id in self.to_check:
            guild = self.bot.get_guild(guild_id)
            conf = self.db.get_conf(guild_id)
            today = datetime.datetime.now(
                tz=datetime.timezone(datetime.timedelta(hours=conf.utcoffset))
            ).date()
            resetday = conf.next_chart_reset
            if (
                guild
                and (conf.started_on and resetday)
                # resetday would be non-null anyways if started_on is non-null
                and today > resetday
            ):
                log.debug(
                    "Detected end of week, resetting chart for %s (%d).",
                    guild.name,
                    guild_id,
                )
                log.info(
                    "Current chart lasted for a total of %d days",
                    (today - resetday).days,
                )
                log.info("Started on: %s", conf.started_on)
                log.info("Ended on: %s", today.strftime("%A %d/%m/%Y"))
                conf.reset_timeslots()
                conf.started_on = today

                log.info("TimeSlots reset for guild %s (%s)", guild.name, guild_id)
                self.save()
                channel = self.bot.get_channel(conf.slot_selection_channel)
                if channel:
                    message = channel.get_partial_message(conf.slot_selection_message)
                    io = await asyncio.to_thread(
                        TimeSlotsGenerator(self, guild).get_colored_organized_chart, {}
                    )
                    await message.edit(attachments=[discord.File(io, "timeslots.png")])
                else:
                    log.warning(
                        "Could not find channel %d in guild %s (%d)",
                        conf.slot_selection_channel,
                        guild.name,
                        guild.id,
                    )

            else:
                log.info(
                    "Not the end of the week yet. Skipping %s (%d)",
                    guild.name,
                    guild_id,
                )
                log.debug(
                    "Today: %s, Next reset: %s, Started on: %s",
                    today.strftime("%A %d/%m/%Y"),
                    resetday.strftime("%A %d/%m/%Y"),
                    conf.started_on.strftime("%A %d/%m/%Y"),
                )

        # calculate the closest midnight based on the offsets set by each guild
        guild_timezones = {
            guild_id: (
                datetime.datetime.now(
                    tz=datetime.timezone(datetime.timedelta(hours=conf.utcoffset))
                )
                + datetime.timedelta(days=1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            for guild_id, conf in self.db.configs.items()
            if conf.started_on
        }

        # get the closest midnight
        self.to_check = all_min(
            guild_timezones.keys(), key=guild_timezones.get, sortkey=guild_timezones.get
        )

        self.reset_chart.change_interval(
            time=guild_timezones[self.to_check[0]].timetz()
        )

    @reset_chart.before_loop
    async def before_reset_chart(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)
        log.info("Reset chart task loop started")
