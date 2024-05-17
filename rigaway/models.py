import functools
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Coroutine, List, Optional

import discord
from discord.ui import Button, View
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .exceptions import GiveawayError

if TYPE_CHECKING:
    from .giveaways import Giveaway

log = logging.getLogger("red.craycogs.Giveaway.models")


@dataclass
class GiveawaySettings:
    notify_users: bool
    emoji: str


class GiveawayView(View):
    def __init__(self, cog: "Giveaway", emoji=":tada:", disabled=False):
        super().__init__(timeout=None)
        self.bot = cog.bot
        self.cog = cog
        self.JTB = JoinGiveawayButton(emoji, self._callback, disabled)
        self.add_item(self.JTB)

    async def _callback(
        self, button: "JoinGiveawayButton", interaction: discord.Interaction
    ):
        log.debug("callback called")
        cog: "Giveaway" = self.cog

        giveaway = await cog.get_giveaway(interaction.guild.id, interaction.message.id)
        settings = await cog.get_guild_settings(interaction.guild.id)
        if not giveaway:
            return await interaction.response.send_message(
                "This giveaway does not exist in my database. It might've been erased due to a glitch.",
                ephemeral=True,
            )

        elif not giveaway.remaining_seconds:
            await interaction.response.defer()
            return await giveaway.end()

        log.debug("giveaway exists")

        if interaction.user == giveaway.host:
            return await interaction.response.send_message(
                "You cannot join your own giveaway.", ephemeral=True
            )

        result = await giveaway.add_entrant(interaction.user.id)
        kwargs = {}

        if result:
            kwargs.update(
                {
                    "content": f"{interaction.user.mention} you have been entered in the giveaway."
                    + (
                        " you will be notfied when the giveaway ends."
                        if settings.notify_users
                        else ""
                    )
                }
            )

        else:
            await giveaway.remove_entrant(interaction.user.id)
            kwargs.update(
                {
                    "content": f"{interaction.user.mention} you have been removed from the giveaway."
                    + (
                        " you will no longer be notified for the giveaway."
                        if settings.notify_users
                        else ""
                    )
                }
            )

        await interaction.response.send_message(**kwargs, ephemeral=True)


class JoinGiveawayButton(Button[GiveawayView]):
    def __init__(
        self,
        emoji: Optional[str],
        callback,
        disabled=False,
        custom_id="JOIN_GIVEAWAY_BUTTON",
    ):
        super().__init__(
            emoji=emoji,
            style=discord.ButtonStyle.green,
            disabled=disabled,
            custom_id=custom_id,
        )
        self.callback = functools.partial(callback, self)


class GiveawayObj:
    def __init__(self, **kwargs):
        gid, cid, e, bot = self.check_kwargs(kwargs)

        self.bot: Red = bot

        self.message_id: int = kwargs.get("message_id")
        self.channel_id: int = cid
        self.guild_id: int = gid
        self.name: str = kwargs.get("name", "A New Giveaway!")
        self.emoji: str = kwargs.get("emoji", ":tada:")
        self._entrants: set[int] = set(kwargs.get("entrants", {}) or {})
        self._host: int = kwargs.get("host")
        self.ends_at: datetime = e
        self._winner: Optional[int] = kwargs.get("winner")

    @property
    def cog(self) -> Optional["Giveaway"]:
        return self.bot.get_cog("Giveaway")

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self) -> Optional[discord.TextChannel]:
        return self.guild.get_channel(self.channel_id)

    @property
    def message(self) -> Coroutine[Any, Any, Optional[discord.Message]]:
        return self._get_message()

    @property
    def host(self) -> Optional[discord.Member]:
        return self.guild.get_member(self._host)

    @property
    def winner(self) -> Optional[discord.Member]:
        return self.guild.get_member(self._winner)

    @property
    def entrants(self) -> List[discord.Member]:
        return [y for x in self._entrants if (y := self.guild.get_member(x))]

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"

    @property
    def remaining_seconds(self):
        return self.ends_at - datetime.now(timezone.utc)

    @property
    def remaining_time(self):
        return self.remaining_seconds.total_seconds()

    @property
    def ended(self):
        return datetime.now(timezone.utc) > self.ends_at

    @property
    def edit_wait_duration(self):
        return (
            15
            if (secs := self.remaining_time.total_seconds()) <= 120
            else 60 if secs < 300 else 300
        )

    @property
    def json(self):
        """
        Return json serializable giveaways metadata."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "name": self.name,
            "emoji": self.emoji,
            "entrants": list(self._entrants),
            "host": self._host,
            "ends_at": self.ends_at.timestamp(),
            "winner": self._winner,
        }

    @staticmethod
    def check_kwargs(kwargs: dict):
        if not (gid := kwargs.get("guild_id")):
            raise GiveawayError("No guild ID provided.")

        if not (cid := kwargs.get("channel_id")):
            raise GiveawayError("No channel ID provided.")

        if not (e := kwargs.get("ends_at")):
            raise GiveawayError("No ends_at provided for the giveaway.")

        if not (bot := kwargs.get("bot")):
            raise GiveawayError("No bot object provided.")

        return gid, cid, e, bot

    def __str__(self):
        return (
            f"<{self.__class__.__name__} "
            f"message_id={self.message_id} name={self.name} "
            f"emoji={self.emoji} time_remainin={cf.humanize_timedelta(timedelta=self.remaining_time)}>"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __hash__(self) -> int:
        return hash((self.message_id, self.channel_id))

    async def get_embed_description(self):
        return f"""{'Ends in' if not self.ended else 'Ended'}: <t:{int(self.ends_at.timestamp())}:R> (<t:{int(self.ends_at.timestamp())}:F>)\n
            Hosted by: {self.host.mention}\n
            Entries: {len(self._entrants)}\n
            Winners: {self.winner.mention if self.ended else 'No winner selected'}\n"""

    async def get_embed_color(self):
        return await self.bot.get_embed_color(self.channel)

    async def _get_message(self, message_id: int = None) -> Optional[discord.Message]:
        message_id = message_id or self.message_id
        msg = list(filter(lambda x: x.id == message_id, self.bot.cached_messages))
        if msg:
            return msg[0]
        try:
            msg = await self.channel.fetch_message(message_id)
        except Exception:
            msg = None
        return msg

    async def add_entrant(self, user_id: int):
        if user_id == self._host or user_id in self._entrants:
            return False
        self._entrants.add(user_id)
        return True

    async def remove_entrant(self, user_id: int):
        if user_id == self._host or user_id not in self._entrants:
            return False
        self._entrants.remove(user_id)
        return True

    async def start(self):
        embed = (
            discord.Embed(
                title=f"Giveaway for **{self.name}**",
                description=await self.get_embed_description(),
                color=await self.get_embed_color(),
            )
            .set_thumbnail(url=getattr(self.guild.icon, "url", ""))
            .set_footer(
                text=f"Hosted by: {self.host}", icon_url=self.host.display_avatar.url
            )
        )

        kwargs = {
            "embed": embed,
            "view": GiveawayView(self.cog, self.emoji, False)
        }
        

        msg: discord.Message = await self.channel.send(**kwargs)

        self.message_id = msg.id
        kwargs["view"].stop()

        await self.cog.add_giveaway(self)

    async def end(self):
        msg = await self.message
        if not msg:
            await self.cog.remove_giveaway(self)
            raise GiveawayError(
                f"Couldn't find giveaway message with id {self.message_id}. Removing from cache."
            )

        embed: discord.Embed = msg.embeds[0]
        embed.description = self.get_embed_description()

        settings = await self.cog.get_guild_settings(self.guild_id)

        view = GiveawayView(self.cog, settings.emoji, True)

        await msg.edit(embed=embed, view=view)

        notify = settings.notify_users

        if self.winner and self.winner in self.entrants:
            self.winner = self.winner

        elif self._entrants:
            self.winner = random.choice(self.entrants)

        else:
            self.winner = None

        rep = await msg.reply(
            (
                f"Congratulations {self.winner.mention}! You won the **{self.name}**!"
                if self.winner
                else "No winner could be selected for this giveaway."
            )
        )

        pings = (
            " ".join((i.mention for i in self.entrants if i is not None))
            if self._entrants and notify
            else ""
        )

        if pings:
            for page in cf.pagify(pings, delims=[" "], page_length=2000):
                await msg.channel.send(
                    page, reference=rep.to_reference(fail_if_not_exists=False)
                )

        await self.cog.remove_giveaway(self)

    @classmethod
    def from_json(cls, json: dict):
        gid, cid, e, bot = cls.check_kwargs(json)
        return cls(
            **{
                "message_id": json.get("message_id"),
                "channel_id": cid,
                "guild_id": gid,
                "bot": bot,
                "name": json.get("name"),
                "emoji": json.get("emoji", ":tada:"),
                "entrants": json.get("entrants", []),
                "host": json.get("host"),
                "ends_at": datetime.fromtimestamp(e, tz=timezone.utc),
                "winner": json.get("winner"),
            }
        )
