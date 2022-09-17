import typing
from argparse import ArgumentParser
from datetime import datetime

import dateparser
import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .constants import Category, class_spec_dict, emoji_class_dict


class Event:
    def __init__(
        self,
        bot: Red,
        name: str,
        message_id: int,
        channel_id: int,
        guild_id: int,
        author_id: int,
        description: str,
        end_time: datetime,
        image_url: str,
        description2: str = "",
        softres: str = "",
        start_time: typing.Optional[datetime] = None,
        pings: int = 0,
    ) -> None:

        self.bot = bot
        self.name = name
        self.guild_id = guild_id
        self.author_id = author_id
        self.message_id = message_id
        self.channel_id = channel_id
        self.description = description
        self.description2 = description2
        self.softres = softres
        self.start_time = start_time or datetime.now()
        self.end_time = end_time
        self.image_url = image_url

        self.pings = pings or 0

        self.entrants: typing.List[Entrant] = []

    @property
    def cog(self):
        return self.bot.get_cog("EventManager")

    @property
    def guild(self) -> typing.Optional[discord.Guild]:
        guild = self.bot.get_guild(self.guild_id)
        return guild

    @property
    def author(self) -> typing.Optional[discord.Member]:
        return self.guild.get_member(self.author_id)

    @property
    def channel(self) -> typing.Optional[discord.TextChannel]:
        return self.guild.get_channel(self.channel_id)

    @property
    def message(self):
        return self._get_message

    @property
    def embed(self) -> discord.Embed:
        """Create the embed for an event."""

        embed = discord.Embed(
            title=self.name,
            description=cf.box(self.description),
            color=discord.Color.green(),
            timestamp=self.start_time,
        )

        embed.add_field(
            name="Time",
            value=f"<t:{int(self.end_time.timestamp())}:F> - <t:{int(self.end_time.timestamp())}:R>",
            inline=True,
        )

        joined_melee = [i for i in self.entrants if i.category is Category.MELEE]
        joined_ranged = [i for i in self.entrants if i.category is Category.RANGED]
        joined_healer = [i for i in self.entrants if i.category is Category.HEALER]
        joined_tank = [i for i in self.entrants if i.category is Category.TANK]

        if self.entrants:
            for category in Category:
                ent = [i for i in self.entrants if i.category is category]
                if not ent:
                    continue
                category_emoji = category.emoji
                embed.add_field(
                    name=f"{category_emoji} **{category.value}**:  (**{len(ent)}**)",
                    value="\n".join(
                        [
                            f"{class_spec_dict[i.category_class]['specs'][i.spec]['emoji']} <@{i.user_id}> - <t:{int(i.joined_at.timestamp())}:F>"
                            for i in ent
                        ]
                    ),
                    inline=False,
                )

        embed.add_field(
            name=f"**{len(self.entrants)}** Joined Users: ",
            value=cf.box(
                f"Melee: {len(joined_melee)}\t Ranged: {len(joined_ranged)}\nHealer: {len(joined_healer)}\t Tank: {len(joined_tank)}"
            ),
            inline=False,
        )

        if self.softres:
            embed.add_field(name="Softres link:", value=self.softres, inline=False)

        if self.description2:
            embed.add_field(name="Additional Information:", value=self.description2, inline=False)

        embed.set_footer(text=f"Created by {self.author}")
        if self.image_url:
            embed.set_image(url=self.image_url)
        return embed

    def end(self):
        embed = self.embed
        embed.title = f"Event Ended"
        embed.description = ""
        embed._fields.insert(
            0, {"name": self.name, "value": cf.box(self.description), "inline": False}
        )
        return embed

    @property
    def json(self):
        return {
            "name": self.name,
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "author_id": self.author_id,
            "description": self.description,
            "description2": self.description2,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "image_url": self.image_url,
            "entrants": [i.json for i in self.entrants],
            "pings": self.pings,
        }

    def copy(self):
        """
        Return a shallow copy of an event."""
        return Event.from_json(self.bot, self.json)

    def edit(
        self,
        *,
        name: str = None,
        description: str = None,
        description2: str = None,
        image_url: str = None,
        end_time: datetime = None,
    ):
        """
        Edit an event.

        This returns a new instance of the event and
        not the same instance that this method was called on."""
        new = self.copy()

        if name:
            new.name = name

        if description:
            new.description = description

        if description2:
            new.description2 = description2

        if image_url:
            new.image_url = image_url

        if end_time:
            new.end_time = end_time

        return new

    async def _get_message(self) -> typing.Optional[discord.Message]:
        msg = list(filter(lambda x: x.id == self.message_id, self.bot.cached_messages))

        if msg:
            return msg[0]

        channel = self.channel

        if not channel:
            raise Exception("The channel for this event could not be found.")

        try:
            msg = await channel.fetch_message(self.message_id)
        except Exception:
            msg = None
        return msg

    def get_entrant(self, user_id: int) -> typing.Optional["Entrant"]:
        for entrant in self.entrants:
            if entrant.user_id == user_id:
                return entrant

    def add_entrant(self, user_id: int, category_class: str, category: Category, spec: str):
        if entrant := self.get_entrant(user_id):
            entrant.category_class = category_class
            entrant.category = category
            entrant.spec = spec
            entrant.joined_at = datetime.now()
            return entrant
        entrant = Entrant(user_id, self, category, category_class, spec, datetime.now())
        self.entrants.append(entrant)

    def remove_entrant(self, entrant: "Entrant"):
        self.entrants.remove(entrant)

    @classmethod
    def from_json(cls, bot: Red, json: dict) -> "Event":
        json["start_time"] = datetime.fromisoformat(json["start_time"])
        json["end_time"] = datetime.fromisoformat(json["end_time"])
        entrants = json["entrants"]
        del json["entrants"]
        self = cls(bot, **json)
        self.entrants = [Entrant.from_json(self, i) for i in entrants]
        return self


class Entrant:
    def __init__(
        self,
        user_id: int,
        event: Event,
        category: Category,
        category_class: str,
        spec: str,
        joined_at: datetime,
    ) -> None:
        self.user_id = user_id
        self.event = event
        self.category = category
        self.category_class = category_class
        self.spec = spec
        self.joined_at: datetime = joined_at

    @property
    def user(self) -> typing.Optional[discord.Member]:
        return self.event.guild.get_member(self.user_id)

    @property
    def json(self) -> dict:
        return {
            "user_id": self.user_id,
            "category": self.category.name,
            "category_class": self.category_class,
            "spec": self.spec,
            "joined_at": self.joined_at.isoformat(),
        }

    @classmethod
    def from_json(cls, event: Event, json: dict):
        json["category"] = Category[json["category"]]
        json["joined_at"] = datetime.fromisoformat(json["joined_at"])
        return cls(event=event, **json)


class NoExitParser(ArgumentParser):
    def error(self, message):
        raise commands.BadArgument(message)


def validate_end_time(date: typing.List[str]):
    if not (time := dateparser.parse(" ".join(date))):
        print(date)
        raise commands.BadArgument("Invalid end time.")

    if time.timestamp() < datetime.now().timestamp():
        raise commands.BadArgument("The end time must be in the future.")

    return time


class Flags(commands.Converter):
    async def convert(self, ctx, argument: str):
        argument = argument.replace("—", "--")
        parser = NoExitParser(description="EventManager flag parser", add_help=False)

        parser.add_argument(
            "--name",
            "-n",
            type=str,
            help="The name of the event.",
            dest="name",
            nargs="+",
            default=[],
        )
        parser.add_argument(
            "--description",
            "-d",
            type=str,
            help="The description of the event.",
            dest="description",
            nargs="+",
            default=[],
        )
        parser.add_argument(
            "--description2",
            "-d2",
            type=str,
            help="The description of the event.",
            dest="description2",
            nargs="+",
            default=[],
        )
        parser.add_argument(
            "--end",
            "-e",
            type=str,
            help="The end time of the event.",
            dest="end",
            nargs="+",
            default=[],
        )
        parser.add_argument(
            "--image",
            "-i",
            type=str,
            help="The image url of the event.",
            dest="image",
            nargs="+",
            default=[],
        )
        parser.add_argument(
            "--channel",
            "-c",
            type=str,
            help="The channel to post the event in.",
            dest="channel",
            nargs="+",
        )
        parser.add_argument(
            "--template",
            "-t",
            type=str,
            help="An already existing template to use instead.",
            dest="template",
            nargs="+",
            default=None,
        )
        parser.add_argument("--softres", "-sr", type=str, dest="softres")

        try:
            flags = vars(parser.parse_args(argument.split(" ")))
        except Exception as e:
            raise commands.BadArgument(str(e))

        template = None

        if temp_name := flags.get("template"):
            templates = await ctx.cog.config.custom("templates", ctx.guild.id).all()
            if not templates:
                raise commands.BadArgument("There are no templates to use.")

            temp_name = " ".join(temp_name)

            if not (template := templates.get(temp_name)):
                raise commands.BadArgument(f"There is no template named {temp_name}.")

        f = template or flags

        if flags.get("end"):
            time = validate_end_time(flags.get("end"))

            f["end_time"] = time

        f["name"] = " ".join(flags["name"]) or f.get("name")
        f["description"] = " ".join(flags["description"]) or f.get("description")
        f["description2"] = " ".join(flags["description2"])[:1021] + (
            "..." if len(" ".join(flags["description2"])) > 1021 else ""
        ) or f.get("description2")

        f["image_url"] = " ".join(flags["image"])

        if chan := flags.get("channel"):
            f["channel_id"] = (
                await commands.TextChannelConverter().convert(ctx, " ".joint(chan))
            ).id

        try:
            del f["channel"]
            del f["end"]
            del f["image"]
            del f["template"]

        except KeyError:
            pass

        return f
