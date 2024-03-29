import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple, Union

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate

from .constants import Category, class_spec_dict, emoji_class_dict
from .model import Event, Flags
from .wrapper import SoftRes, SRFlags

log = logging.getLogger("red.misan-cogs.eventmanager")

MISSING = object()


class EventManager(commands.Cog):
    HOUR = 60 * 60
    HALF_HOUR = HOUR / 2
    QUARTER_HOUR = HALF_HOUR / 2

    """A cog to create and manage events."""

    __version__ = "1.12.0"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x352567829, force_registration=True)
        self.config.init_custom("events", 2)
        self.config.init_custom("templates", 2)
        self.config.register_member(spec_class=())
        self.config.register_guild(history_channel=None, softres_log=None, log=None)
        self.cache: Dict[int, Dict[int, Event]] = {}
        self.task = self.check_events.start()
        self.softres = SoftRes(self.bot)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def ask_for_answers(
        self,
        questions: List[Tuple[str, str, str, Callable[[discord.Message], Awaitable[Any]]]],
        ctx: Optional[commands.Context] = None,
        user: Optional[discord.User] = None,
        channel: Optional[discord.abc.Messageable] = None,
        timeout: int = 30,
    ) -> Union[Dict[str, Any], Literal[False]]:
        if not any((ctx, user, channel)):
            raise ValueError("You must specify at least one of ctx, message or channel")
        context = ctx or user or channel
        main_check = MessagePredicate.same_context(ctx=ctx, channel=channel, user=user)
        final = {}
        for question in questions:
            title, description, key, check = question
            answer = MISSING
            sent = False
            while answer is MISSING:
                if not sent:
                    embed = discord.Embed(
                        title=title,
                        description=description,
                    ).set_footer(
                        text=f"You have {timeout} seconds to answer.\nSend `cancel` to cancel."
                    )
                    sent = await context.send(embed=embed)
                try:
                    message: discord.Message = await self.bot.wait_for(
                        "message", check=main_check, timeout=timeout
                    )
                except asyncio.TimeoutError:
                    await context.send("You took too long to answer. Cancelling.")
                    return False

                if message.content.lower() == "cancel":
                    await context.send("Cancelling.")
                    return False

                try:
                    result = await discord.utils.maybe_coroutine(check, message)

                except Exception as e:
                    await context.send(
                        f"The following error has occurred:\n{box(e, lang='py')}\nPlease try again. (The process has not stopped. Send your answer again)"
                    )
                    continue

                answer = result

            final[key] = answer

        return final

    async def to_cache(self):
        all_guilds = await self.config.custom("events").all()
        for guild_id, guild_config in all_guilds.items():
            g = self.cache.setdefault(int(guild_id), {})
            for event in guild_config.values():
                try:
                    g[event["message_id"]] = Event.from_json(self.bot, event)

                except Exception as e:
                    log.exception("Error occurred when caching: ", exc_info=e)

    async def to_config(self):
        for guild_config in self.cache.values():
            for event in guild_config.values():
                json = event.json
                await self.config.custom("events", event.guild_id, event.message_id).set(json)

    def cog_unload(self):
        asyncio.create_task(self.to_config())
        self.task.cancel()
        asyncio.create_task(self.softres._session.close())

    def validate_flags(self, flags: dict):
        return all((flags.get("name"), flags.get("description"), flags.get("end_time")))

    @staticmethod
    async def group_embeds_by_fields(
        *fields: Dict[str, Union[str, bool]], per_embed: int = 3, **kwargs
    ) -> List[discord.Embed]:
        """
        This was the result of a big brain moment i had

        This method takes dicts of fields and groups them into separate embeds
        keeping `per_embed` number of fields per embed.

        Extra kwargs can be passed to create embeds off of.
        """
        groups: list[discord.Embed] = []
        for ind, i in enumerate(range(0, len(fields), per_embed)):
            groups.append(
                discord.Embed(**kwargs)
            )  # append embeds in the loop to prevent incorrect embed count
            fields_to_add = fields[i : i + per_embed]
            for field in fields_to_add:
                groups[ind].add_field(**field)
        return groups

    @commands.group(name="event", invoke_without_command=True)
    async def event(self, ctx: commands.Context, *, flags: Flags):
        """
        Start an event.

        Valid flags are:
        `--end` - The time the event ends.
        `--image` - The image to use for the event.
        `--name` - The name of the event.
        `--description` - A short description of the event.
        `--description2` - A long description of the event.
        `--channel` - The channel to post the event in. [optional]
        """

        if not self.validate_flags(flags):
            await ctx.send(
                "Incomplete arguments. `--name`, `--description` and `--end` are required."
            )
            return

        flags["channel_id"] = flags.get("channel_id") or ctx.channel.id
        event = Event(
            ctx.bot,
            message_id=ctx.message.id,
            guild_id=ctx.guild.id,
            author_id=ctx.author.id,
            **flags,
        )
        msg = await ctx.send(embed=event.embed)
        event.message_id = msg.id
        start_adding_reactions(
            msg, [i for i in emoji_class_dict.keys()] + ["❌", "🧻", "👑", "🚀", "👻"]
        )
        self.cache.setdefault(ctx.guild.id, {})[msg.id] = event

    @event.command(name="edit")
    async def edit(
        self, ctx: commands.Context, message: commands.MessageConverter, *, flags: Flags
    ):
        """
        Edit an event.

        Valid flags are:
        `--end` - The time the event ends.
        `--image` - The image to use for the event.
        `--name` - The name of the event.
        `--description` - A short description of the event.
        `--description2` - A long description of the event.
        """
        if not flags:
            return await ctx.send("You must atleast send one flag to edit.")

        event = self.cache.get(ctx.guild.id, {}).get(message.id)

        if not event:
            return await ctx.send("Event not found.")

        if event.author_id != ctx.author.id:
            return await ctx.send("You do not own this event. Thus, you cannot edit it.")

        new: Event = event.edit(**flags)

        if new.channel_id != event.channel_id:
            new_chan = new.channel
            new_msg = await new_chan.send(embed=new.embed)
            new.message_id = new_msg.id
            start_adding_reactions(
                new_msg, [i for i in emoji_class_dict.keys()] + ["❌", "🧻", "👑", "🚀", "👻"]
            )
            await message.delete()

        else:
            await message.edit(embed=new.embed)

        self.cache[ctx.guild.id][new.message_id] = new

        await ctx.tick()

    @event.command(name="remove")
    async def event_remove(
        self,
        ctx: commands.Context,
        message: commands.MessageConverter,
        users: commands.Greedy[commands.MemberConverter],
    ):
        if not (g := self.cache.get(ctx.guild.id, {})):
            return await ctx.send("No events found.")

        if not (event := g.get(message.id)):
            return await ctx.send("Event not found.")

        if (
            not event.author_id == ctx.author.id
            and not await ctx.bot.is_owner(ctx.author)
            and not ctx.guild.owner_id == ctx.author.id
        ):
            return await ctx.send(
                "You do not own this event. Thus, you cannot remove users from it."
            )

        failed = []

        for user in users:
            ent = event.get_entrant(user.id)
            if not ent:
                failed.append(ent)
                continue

            event.remove_entrant(ent)

        await message.edit(embed=event.embed)

        await ctx.send(
            f"Removed given users from the event."
            + ("\n" + "\n".join(f"{u.mention}" for u in failed) if failed else "")
        )

    @event.group(name="template", invoke_without_command=True)
    async def event_template(self, ctx: commands.Context):
        """
        Manage event templates in your server."""
        return await ctx.send_help(ctx.command)

    @event_template.command(name="add")
    async def event_template_add(self, ctx: commands.Context, template_name: str, *, flags: Flags):
        """
        Add a template to your server."""
        await self.config.custom("templates", ctx.guild.id, template_name).set(flags)
        await ctx.tick()

    @event_template.command(name="remove")
    async def event_template_remove(self, ctx: commands.Context, template_name: str):
        """
        Remove a template from your server."""
        async with self.config.custom("templates", ctx.guild.id).all() as templates:
            if template_name not in templates:
                return await ctx.send("Template not found.")
            del templates[template_name]
            await ctx.tick()

    def format_template(self, flags: dict):
        final = ""
        for key, value in flags.items():
            final += f"\t*{key.replace('_', ' ').capitalize()}*: {value if value else 'Not specified'}\n"

        return final

    @event_template.command(name="list")
    async def event_template_list(self, ctx: commands.Context):
        """
        See a list of templates saved for your server"""

        templates = await self.config.custom("templates", ctx.guild.id).all()

        if not templates:
            return await ctx.send("No templates found.")

        final = ""

        for template in templates:
            final += f"**{template}**: \n{self.format_template(templates[template])}\n"

        for page in pagify(final, delims=["\n\n"]):
            await ctx.maybe_send_embed(page)

    @event.command(name="history")
    async def event_history(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).history_channel.set(channel.id)
        await ctx.tick()

    @event.command(name="log")
    async def event_log(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).log.set(channel.id)
        await ctx.tick()

    @commands.group(name="sr", aliases=["softres"], invoke_without_command=True)
    async def sr(
        self,
        ctx: commands.Context,
        dungeon: commands.Literal[
            "wotlknaxx10",
            "obsidiansanctum10",
            "eyeofeternity10",
            "wyrmrest10",
            "naxxdragons10",
            "wotlknaxx25",
            "obsidiansanctum25",
            "eyeofeternity25",
            "wyrmrest25",
            "naxxdragons25",
        ],
        reserves: int,
    ):
        """
        Create a softres event link."""
        args = {
            "faction": "Horde",
            "instance": dungeon,
            "edition": "wotlk",
            "amount": reserves,
            "note": "",
            "raidDate": datetime.now().isoformat(),
            "allowDuplicate": True,
            "hideReserves": False,
            "characterNotes": False,
            "restrictByClass": False,
        }
        args["discord"] = True
        args["discordId"] = str(ctx.author.id)
        try:
            args["discordInvite"] = (
                await ctx.guild.vanity_invite() or (await ctx.guild.invites())[0]
            ).url

        except Exception:
            pass

        # await ctx.send(str(args))

        token, id = await self.softres.create_raid(**args)

        await ctx.send(f"The link to the softres is: https://softres.it/raid/{id}")

        log = await self.config.guild(ctx.guild).softres_log()

        log = ctx.guild.get_channel(log) or ctx.author

        await log.send(
            f"{ctx.author.mention} created a softres event for {dungeon} with {reserves} reserves. https://softres.it/raid/{id}\nToken: ||{token}||"
        )

        return token, id

    @sr.command(name="lock")
    @commands.dm_only()
    async def sr_lock(self, ctx: commands.Context, raid_id: str, token: str):
        """
        Lock a softres event."""
        await self.softres.update_raid(raid=dict(raidId=raid_id, lock=True), token=token)
        await ctx.tick()

    @sr.command(name="unlock")
    @commands.dm_only()
    async def sr_unlock(self, ctx: commands.Context, raid_id: str, token: str):
        """
        Unlock a softres event."""
        await self.softres.update_raid(raid=dict(raidId=raid_id, lock=False), token=token)
        await ctx.tick()

    @sr.command(name="gargul")
    @commands.dm_only()
    async def sr_gargul(self, ctx: commands.Context, raid_id: str, token: str):
        return await ctx.author.send(
            f"The gargul data recieved for this raid is:\n{await self.softres.get_gargul_data(token, raid_id)}"
        )

    @sr.command(name="log")
    async def sr_log(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).softres_log.set(channel.id)
        await ctx.tick()

    async def remove_reactions_safely(
        self, message: discord.Message, emoji: str, user: discord.User
    ):
        try:
            await message.remove_reaction(emoji, user)
            # to not clutter the menu with useless reactions
        except Exception as e:
            log.exception("Failed to remove reaction", exc_info=e)
        return

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id not in self.cache:
            return

        for event in self.cache[member.guild.id].values():
            if entrant := event.get_entrant(member.id):
                event.remove_entrant(entrant)
                msg = await event.message()
                if not msg:
                    continue

                await msg.edit(embed=event.embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent, name: Optional[str] = None
    ):
        if not payload.guild_id:
            return

        if not (data := self.cache.get(payload.guild_id)):
            return

        if not (event := data.get(payload.message_id)):
            return

        message = await event.message()
        channel = event.channel

        if not message:
            return  # idk what could be the reason message is none tbh.

        user: Optional[discord.User] = payload.member or await self.bot.get_or_fetch_user(
            payload.user_id
        )

        if not user:
            return

        if user.bot:
            return

        emoji = str(payload.emoji)

        if not emoji in emoji_class_dict and emoji not in ["❌", "🧻", "👑", "🚀", "👻"]:
            await self.remove_reactions_safely(message, emoji, user)
            return

        if emoji in emoji_class_dict:
            if entrant := event.get_entrant(user.id):
                emoji_to_remove = class_spec_dict[entrant.category_class]["emoji"]
                await self.remove_reactions_safely(message, emoji_to_remove, user)

            class_name = emoji_class_dict[emoji]

            details = class_spec_dict[class_name]

            valid_specs = [(k, v["emoji"]) for k, v in details["specs"].items()]

            questions = [
                (
                    "Select a spec for the class {}".format(class_name),
                    "\n".join(
                        f"{ind+1}. {spec[1]} {spec[0]}" for ind, spec in enumerate(valid_specs)
                    )
                    + "\nSend the correct number to select a spec.",
                    "spec",
                    lambda m: int(m.content)
                    if all(
                        (
                            m.author == user,
                            not m.guild,
                            m.channel.recipient == user,
                            m.content.isdigit(),
                            int(m.content) in range(1, len(valid_specs) + 1),
                        )
                    )
                    else (_ for _ in ()).throw(
                        commands.BadArgument(
                            f"That's not a valid answer. You must write a number from 1 to {len(valid_specs)}"
                        )
                    ),
                ),
            ]

            answers = await self.ask_for_answers(
                questions,
                channel=(user.dm_channel or await user.create_dm()),
                user=user,
                timeout=30,
            )

            if answers is False:
                return await self.remove_reactions_safely(message, emoji, user)

            spec = valid_specs[answers["spec"] - 1][0]
            category: Category = details["specs"][spec]["categories"][0]
            user_name = name

            event.add_entrant(user_name, user.id, class_name, category, spec)

            await user.send(
                "You have been signed up to the event. "
                "Would you like to set this configuration as your default?\n"
                "(Will be selected automatically when you click the 🚀 reaction)\n"
                "Reply with y/n, yes/no."
            )

            pred = MessagePredicate.yes_or_no(channel=user.dm_channel)

            try:
                await self.bot.wait_for("message", check=pred, timeout=60)

            except asyncio.TimeoutError:
                await user.send("You took too long to answer. Not saving as default.")

            else:
                if pred.result is True:
                    await user.send("Successfully set as default!")
                    await self.config.member_from_ids(event.guild_id, user.id).spec_class.set(
                        (user_name, class_name, category.name, spec)
                    )

                else:
                    await user.send("Alright!")

            embed = event.embed

            await message.edit(embed=embed)

            await self.remove_reactions_safely(message, emoji, user)

            chan = self.bot.get_channel(await self.config.guild(event.guild).log())

            if not chan:
                return

            class_emoji = emoji
            spec_emoji = details["specs"][spec]["emoji"]

            await chan.send(
                embed=discord.Embed(
                    title="**New entrant!**",
                    description=f"**{user_name}** has signed up for **{event.name}** as **{class_emoji} {spec_emoji}**",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow(),
                )
            )

        elif emoji == "❌":
            if not event.author_id == user.id:
                await self.remove_reactions_safely(message, emoji, user)
                return

            try:
                await message.clear_reactions()

            except Exception:
                pass

            embed = event.end()

            await user.send("The event was ended.")

            if (chan_id := await self.config.guild(message.guild).history_channel()) and (
                chan := message.guild.get_channel(chan_id)
            ):
                await chan.send(embed=embed)
                await message.delete()

            else:
                await message.edit(embed=embed)

            await self.config.custom("events", event.guild_id, event.message_id).clear()
            del self.cache[event.guild_id][event.message_id]

        elif emoji == "🧻":
            await self.remove_reactions_safely(message, emoji, user)

            if entrant := event.get_entrant(user.id):
                event.remove_entrant(entrant)

                await user.send("You have been removed from the event.")

                await message.edit(embed=event.embed)

                chan = self.bot.get_channel(await self.config.guild(event.guild).log())

                if not chan:
                    return

                await chan.send(
                    embed=discord.Embed(
                        title="**Entrant removed!**",
                        description=f"**{entrant.name}** has been removed from **{event.name}**.\nThey were signed up as **{entrant.category_class} {entrant.spec}**",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow(),
                    )
                )

            else:
                await user.send("You weren't signed up to the event.")

        elif emoji == "👑":
            ents = event.entrants
            await self.remove_reactions_safely(message, emoji, user)
            if not ents:
                return
            fields = []
            for i in range(0, len(ents), 10):
                e = ents[i : i + 10]
                fields.append(
                    {
                        "name": "\u200b",
                        "value": "\n".join(f"> /invite {entrant.name}" for entrant in e),
                        "inline": True,
                    }
                )

            for embed in await self.group_embeds_by_fields(*fields, per_embed=20):
                await channel.send(embed=embed, delete_after=30)

        elif emoji == "🚀":
            await self.remove_reactions_safely(message, emoji, user)

            if event.get_entrant(user.id):
                return await user.send("You are already signed up to the event.")

            tup = await self.config.member_from_ids(event.guild_id, user.id).spec_class()
            if not tup:
                return await user.send(
                    "You do not have a default configuration set. Please select manually with the reactions provided."
                )

            try:
                user_name, class_name, category, spec = tup

            except ValueError:
                user_name, (class_name, category, spec) = None, tup

            category = Category[category]

            event.add_entrant(user_name, user.id, class_name, category, spec)

            await user.send("You have successfully been signed up to the event.")

            await message.edit(embed=event.embed)

            chan = self.bot.get_channel(await self.config.guild(event.guild).log())

            if not chan:
                return

            class_emoji = class_spec_dict[class_name]["emoji"]
            spec_emoji = class_spec_dict[class_name]["specs"][spec]["emoji"]

            await chan.send(
                embed=discord.Embed(
                    title="**New entrant!**",
                    description=f"**{user_name}** has signed up for **{event.name}** as **{class_emoji} {spec_emoji}**",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow(),
                )
            )

        elif emoji == "👻":
            questions = [
                ("What do you want your name to be?", "", "name", lambda m: m.content),
                (
                    "Select a class for the event",
                    "\n".join(
                        f"{ind+1}. {class_spec_dict[cls]['emoji']}{cls}"
                        for ind, cls in enumerate(class_spec_dict.keys())
                    ),
                    "class",
                    lambda m: int(m.content)
                    if all(
                        (
                            m.author == user,
                            not m.guild,
                            m.channel.recipient == user,
                            m.content.isdigit(),
                            int(m.content) in range(1, len(class_spec_dict) + 1),
                        )
                    )
                    else (_ for _ in ()).throw(
                        commands.BadArgument(
                            f"That's not a valid answer. You must write a number from 1 to {len(class_spec_dict)}"
                        )
                    ),
                ),
            ]

            answers = await self.ask_for_answers(
                questions,
                channel=(user.dm_channel or await user.create_dm()),
                user=user,
                timeout=30,
            )
            await self.remove_reactions_safely(message, emoji, user)

            if answers is False:
                return

            class_name = list(class_spec_dict.keys())[answers["class"] - 1]

            emoji = class_spec_dict[class_name]["emoji"]

            payload.emoji = emoji

            await self.on_raw_reaction_add(payload, answers["name"])

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id not in self.cache:
            return

        for event in self.cache[member.guild.id].values():
            if entrant := event.get_entrant(member.id):
                event.remove_entrant(entrant)
                try:
                    msg = await event.message()

                except Exception:
                    log.debug(
                        f"The channel for the event {event.name} ({event.message_id}) has been deleted so I'm removing it from storage"
                    )
                    del self.cache[event.guild_id][event.message_id]
                    await self.config.custom("events", event.guild_id, event.message_id).clear()
                    continue

                if not msg:
                    continue

                await msg.edit(embed=event.embed)

    @tasks.loop(minutes=5)
    async def check_events(self):
        await self.to_config()

        self.cache.clear()

        await self.to_cache()

        for guild_config in self.cache.copy().values():
            cop = guild_config.copy()
            for event in cop.values():
                if event.end_time <= datetime.now(tz=event.end_time.tzinfo):
                    embed = event.end()
                    try:
                        msg = await event.message()

                    except Exception:
                        log.debug(
                            f"The channel for the event {event.name} ({event.message_id}) has been deleted so I'm removing it from storage"
                        )

                        del self.cache[event.guild_id][event.message_id]
                        await self.config.custom(
                            "events", event.guild_id, event.message_id
                        ).clear()
                        continue

                    if not msg:
                        log.debug(
                            f"The message for the event {event.name} ({event.message_id}) has been deleted so I'm removing it from storage"
                        )

                        await self.config.custom(
                            "events", event.guild_id, event.message_id
                        ).clear()
                        del self.cache[event.guild_id][event.message_id]
                        continue

                    if (
                        chan_id := await self.config.guild_from_id(
                            event.guild_id
                        ).history_channel()
                    ) and (chan := event.guild.get_channel(int(chan_id))):
                        await chan.send(embed=embed)
                        try:
                            await msg.delete()
                        except Exception:
                            pass

                    else:
                        await msg.edit(embed=embed)
                        await msg.clear_reactions()

                    await self.config.custom("events", event.guild_id, event.message_id).clear()
                    del self.cache[event.guild_id][event.message_id]
                    continue

                if not event.entrants:
                    continue

                if event.pings >= 3:
                    continue

                td = event.end_time - datetime.now(tz=event.end_time.tzinfo)

                if td.total_seconds() < self.HOUR:
                    if td.total_seconds() <= self.HALF_HOUR:
                        if td.total_seconds() <= self.QUARTER_HOUR:
                            if event.pings >= 3:
                                continue

                        if event.pings >= 2:
                            continue

                    if event.pings >= 1:
                        continue

                    channel = event.channel

                    if not channel:
                        log.debug(
                            f"The channel for the event {event.name} ({event.message_id}) has been deleted so I'm removing it from storage"
                        )
                        del self.cache[event.guild_id][event.message_id]
                        await self.config.custom(
                            "events", event.guild_id, event.message_id
                        ).clear()
                        continue

                    await channel.send(
                        f"{humanize_list([f'<@{ent.user_id}>' for ent in event.entrants])}\n\nThe event `{event.name}` is about to start <t:{int(event.end_time.timestamp())}:R>",
                        allowed_mentions=discord.AllowedMentions(users=True),
                    )

                    event.pings += 1

    @check_events.before_loop
    async def before(self):
        await self.bot.wait_until_red_ready()
        await self.to_cache()
