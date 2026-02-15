import contextlib
import enum
import typing

import discord
from redbot.core.utils import chat_formatting as cf

from ..eightbitANSI import EightBitANSI


class DetailsCandidate(enum.Enum):
    MEMBERS = enum.auto()
    ROLES = enum.auto()
    CHANNELS = enum.auto()
    EMOJIS = enum.auto()
    STICKERS = enum.auto()


class DetailButton(discord.ui.Button):
    def __init__(
        self,
        guild: discord.Guild,
        details_candidate: DetailsCandidate,
        enabled: bool = True,
    ) -> None:
        self.guild = guild
        self.details_candidate = details_candidate

        super().__init__(
            label="Show details",
            style=discord.ButtonStyle.primary,
            disabled=not enabled,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from .page_source import DetailsPageSource
        from .paginator import Paginator

        page_source = DetailsPageSource(self.guild, self.details_candidate)
        paginator = Paginator(
            source=page_source,
            use_select=self.details_candidate == DetailsCandidate.CHANNELS,
        )
        await paginator.start(interaction)


class AllLimits(discord.ui.LayoutView):
    def __init__(self, guild: discord.Guild) -> None:
        super().__init__()
        self.guild = guild
        self.container = AllLimitsContainer(guild)
        self.add_item(self.container)

        self.message: typing.Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.walk_children():
                if hasattr(item, "disabled"):
                    item.disabled = True
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


class AllLimitsContainer(discord.ui.Container):
    def __init__(self, guild: discord.Guild) -> None:
        super().__init__()
        self.guild = guild
        self.create_layout()

    def create_layout(self) -> None:
        channels_title = discord.ui.TextDisplay(
            content=f"**Channel Limit:**\n{len(self.guild.channels)}/{500}"
        )
        channels_pbar = discord.ui.TextDisplay(
            cf.box(
                simple_progressbar(
                    progress=len(self.guild.channels),
                    max_progress=500,
                ),
                lang="ansi",
            )
        )
        channel_section = discord.ui.Section(
            channels_title,
            channels_pbar,
            accessory=DetailButton(
                self.guild, DetailsCandidate.CHANNELS, enabled=bool(self.guild.channels)
            ),
        )
        self.add_item(channel_section)
        self.add_item(discord.ui.Separator())

        roles_title = discord.ui.TextDisplay(
            content=f"**Role Limit:**\n{len(self.guild.roles)}/{250}"
        )
        roles_pbar = discord.ui.TextDisplay(
            cf.box(
                simple_progressbar(
                    progress=len(self.guild.roles),
                    max_progress=250,
                ),
                lang="ansi",
            )
        )
        role_section = discord.ui.Section(
            roles_title,
            roles_pbar,
            accessory=DetailButton(
                self.guild, DetailsCandidate.ROLES, enabled=bool(self.guild.roles)
            ),
        )
        self.add_item(role_section)
        self.add_item(discord.ui.Separator())

        emotes = len([emoji for emoji in self.guild.emojis if not emoji.animated])
        emojis = len([emoji for emoji in self.guild.emojis if emoji.animated])
        emojis_title = discord.ui.TextDisplay(content="**Emoji Limit:**")
        emotes_pbar = discord.ui.TextDisplay(
            f"__Emotes (static)___: {emotes}/{self.guild.emoji_limit}"
            + cf.box(
                simple_progressbar(
                    progress=emotes,
                    max_progress=self.guild.emoji_limit,
                ),
                lang="ansi",
            )
        )
        emojis_pbar = discord.ui.TextDisplay(
            f"__Emojis (animated)___: {emojis}/{self.guild.emoji_limit}"
            + cf.box(
                simple_progressbar(
                    progress=emojis,
                    max_progress=self.guild.emoji_limit,
                ),
                lang="ansi",
            )
        )
        emoji_section = discord.ui.Section(
            emojis_title,
            emotes_pbar,
            emojis_pbar,
            accessory=DetailButton(
                self.guild, DetailsCandidate.EMOJIS, enabled=bool(self.guild.emojis)
            ),
        )
        self.add_item(emoji_section)
        self.add_item(discord.ui.Separator())

        stickers_title = discord.ui.TextDisplay(
            content=f"**Sticker Limit:**\n{len(self.guild.stickers)}/{self.guild.sticker_limit}"
        )
        stickers_pbar = discord.ui.TextDisplay(
            cf.box(
                simple_progressbar(
                    progress=len(self.guild.stickers),
                    max_progress=self.guild.sticker_limit,
                ),
                lang="ansi",
            )
        )
        sticker_section = discord.ui.Section(
            stickers_title,
            stickers_pbar,
            accessory=DetailButton(
                self.guild, DetailsCandidate.STICKERS, enabled=bool(self.guild.stickers)
            ),
        )
        self.add_item(sticker_section)

        self.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))

        # region: static limits
        bitrate_title = discord.ui.TextDisplay(content="**Bitrate Limit:**")
        bitrate = discord.ui.TextDisplay(content=f"{self.guild.bitrate_limit} BPS")
        self.add_item(bitrate_title)
        self.add_item(bitrate)
        self.add_item(discord.ui.Separator())

        filesize_title = discord.ui.TextDisplay(content="**File Size Limit:**")
        filesize = discord.ui.TextDisplay(
            content=f"{self.guild.filesize_limit / (1024 * 1024):.2f} MB"
        )
        self.add_item(filesize_title)
        self.add_item(filesize)
        self.add_item(discord.ui.Separator())

        stage_video_users_title = discord.ui.TextDisplay(
            content="**Max Stage Video Users:**"
        )
        stage_video_users = discord.ui.TextDisplay(
            content=f"{self.guild.max_stage_video_users}"
        )
        self.add_item(stage_video_users_title)
        self.add_item(stage_video_users)
        self.add_item(discord.ui.Separator())

        video_channel_users_title = discord.ui.TextDisplay(
            content="**Max Video Channel Users:**"
        )
        video_channel_users = discord.ui.TextDisplay(
            content=f"{self.guild.max_video_channel_users}"
        )

        self.add_item(video_channel_users_title)
        self.add_item(video_channel_users)
        self.add_item(discord.ui.Separator())

        category_title = discord.ui.TextDisplay(
            content="**Channels per Category Limit:**"
        )
        category = discord.ui.TextDisplay(content="50")
        self.add_item(category_title)
        self.add_item(category)

        # endregion


def simple_progressbar(
    full: str = "█",
    empty: str = "─",
    *,
    progress: int | float,
    max_progress: int,
    size_of_bar: int = 30,
):
    """
    Generate a simple progress bar that uses two different characters as the bars.
    """
    if not isinstance(progress, (int, float)) or not isinstance(
        max_progress, (int, float)
    ):
        raise ValueError("max_progress or progress is not a number")

    size_of_bar = int(size_of_bar)
    full_float = size_of_bar * (min(progress, max_progress) / max_progress)
    full_count = int(full_float + 0.5)

    bars = [
        EightBitANSI.paint_cyan(full, background=EightBitANSI.background.blue)
    ] * full_count + [EightBitANSI.paint_black(empty)] * (size_of_bar - full_count)

    result = "".join(bars)

    return (
        EightBitANSI.paint_black("[", background=EightBitANSI.background.light_gray)
        + result
        + EightBitANSI.paint_black("]", background=EightBitANSI.background.light_gray)
    )
