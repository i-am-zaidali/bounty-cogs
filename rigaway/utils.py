import re
from datetime import datetime, timedelta, timezone

import emoji
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_timedelta


class TimeConverter(commands.Converter):
    time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d|w))+?")
    time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400, "w": 86400 * 7}

    def __init__(self, setting: bool = False):
        self.setting = setting

    def __call__(self):
        return self

    def __class_getitem__(cls, key):
        if not isinstance(key, bool):
            raise TypeError("TimeConverter only accepts bool arguments.")
        return cls(key)

    async def convert(self, ctx: commands.Context, argument: str):
        args = argument.lower()
        matches = re.findall(self.time_regex, args)
        time = 0
        if not matches:
            raise commands.BadArgument(
                "Invalid time format. h|m|s|d are valid arguments."
            )
        for key, value in matches:
            try:
                time += self.time_dict[value] * float(key)
            except KeyError:
                raise commands.BadArgument(
                    f"{value} is an invalid time key! h|m|s|d are valid arguments"
                )
            except ValueError:
                raise commands.BadArgument(f"{key} is not a number!")

        if not time >= 10:
            raise commands.BadArgument("Time must be greater than 10 seconds.")

        if not self.setting and time > (seconds := await ctx.cog.config.max_duration()):
            suggestion = (
                f"You can change this with `{ctx.prefix}timerset maxduration`."
                if await ctx.bot.is_owner(ctx.author)
                else ""
            )
            raise commands.BadArgument(
                f"Time for timers must be less than {humanize_timedelta(seconds=seconds)}. {suggestion}"
            )

        timed = timedelta(seconds=time)
        time = datetime.now(timezone.utc) + timed
        return timed if self.setting else time


class EmojiConverter(commands.EmojiConverter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            emoji.EMOJI_DATA[argument]

        except KeyError:
            return str(await super().convert(ctx, argument))

        else:
            return argument
