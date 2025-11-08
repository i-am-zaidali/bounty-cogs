import datetime
import logging
import typing

import discord
from discord.ext import tasks

from ..abc import MixinMeta

if typing.TYPE_CHECKING:
    from ..main import MediaMonitorCog

log = logging.getLogger("red.mediamonitor.expiry")


class ExpireViolations(MixinMeta):
    """Task loop to expire user violations after a set duration."""

    @tasks.loop(minutes=30)
    async def expire_violations(self):
        """Loop to expire user violations after a set duration."""
        log.debug("Running expire_violations task loop.")
        for guild_id, guild_conf in self.db.configs.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.debug(f"Guild with ID {guild_id} not found, skipping expiry check.")
                continue

            if guild_conf.violation_expiration_seconds == 0:
                log.debug(
                    f"Guild {guild_id} has violation expiration disabled, skipping."
                )
                continue

            now_dt = discord.utils.utcnow()

            to_remove: dict[int, list[str]] = {}

            for user_id, user_data in guild_conf.members.items():
                expired_violations = list[str]()
                for violation, data in user_data.violations.items():
                    expiry = datetime.timedelta(
                        seconds=data.timestamp + guild_conf.violation_expiration_seconds
                    )
                    expiration_dt = (
                        datetime.datetime.fromtimestamp(
                            data.timestamp, tz=datetime.timezone.utc
                        )
                        + expiry
                    )
                    if now_dt >= expiration_dt:
                        expired_violations.append(violation)

                if expired_violations:
                    log.debug(
                        f"Expired violations for user {user_id}: {expired_violations}"
                    )
                    to_remove[user_id] = expired_violations

            async with guild_conf:
                for user_id, violations in to_remove.items():
                    user_data = guild_conf.get_member(user_id)
                    for violation in violations:
                        user_data.violations.pop(violation, None)

        log.debug("Completed expire_violations task loop.")

    @expire_violations.before_loop
    async def before_expire_violations(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_red_ready()
