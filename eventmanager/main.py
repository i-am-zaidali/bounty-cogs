import asyncio
import logging
import time
from typing import Dict, Optional

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.utils.menus import start_adding_reactions

from .constants import class_spec_dict, emoji_class_dict
from .model import Event, Flags

log = logging.getLogger("red.misan-cogs.eventmanager")


class EventManager(commands.Cog):
    """A cog to create and manage events."""

    __version__ = "1.2.2"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x352567829, force_registration=True)
        self.config.init_custom("events", 2)
        self.config.init_custom("templates", 2)
        self.cache: Dict[int, Dict[int, Event]] = {}
        self.task = self.check_events.start()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

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
        
    def validate_flags(self, flags: dict):
        return all((flags.get("name"), flags.get("description"), flags.get("end_time")))

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
            await ctx.send("Incomplete arguments. `--name`, `--description` and `--end` are required.")
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
        start_adding_reactions(msg, [i for i in emoji_class_dict.keys()] + ["❌", "🧻"])
        self.cache.setdefault(ctx.guild.id, {})[msg.id] = event

    @event.command(name="edit")
    async def edit(self, ctx: commands.Context, message: commands.MessageConverter, *, flags: Flags):
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
        
        new = event.edit(**flags)
        
        self.cache[ctx.guild.id][message.id] = new
        
        await ctx.tick()
        
        await message.edit(embed=new.embed)
        
    @event.command(name="remove")
    async def event_remove(self, ctx: commands.Context, message: commands.MessageConverter, users: commands.Greedy[commands.MemberConverter]):
        if not (g:=self.cache.get(ctx.guild.id, {})):
            return await ctx.send("No events found.")
        
        if not (event:=g.get(message.id)):
            return await ctx.send("Event not found.")
        
        if not event.author_id == ctx.author.id or not await ctx.bot.is_owner(ctx.author) or not ctx.guild.owner_id == ctx.author.id:
            return await ctx.send("You do not own this event. Thus, you cannot remove users from it.")
        
        failed = []
        
        for user in users:
            ent = event.get_entrant(user.id)
            if not ent:
                failed.append(ent)
                continue
            
            event.remove_entrant(ent)
            
        await ctx.send(f"Removed given users from the event." + ("\n" + "\n".join(f"{u.mention}" for u in failed) if failed else ""))
        
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
            
        await ctx.maybe_send_embed(final)

    @commands.Cog.listener()
    async def on_member_leave(self, member: discord.Member):
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
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        if not (data := self.cache.get(payload.guild_id)):
            return

        if not (event := data.get(payload.message_id)):
            return

        message = await event.message()

        if not message:
            return  # idk what could be the reason message is none tbh.

        user: Optional[discord.User] = await self.bot.get_or_fetch_user(payload.user_id)

        if not user:
            return

        if user.bot:
            return

        emoji = str(payload.emoji)

        if not emoji in emoji_class_dict and emoji not in ["❌", "🧻"]:
            try:
                await message.remove_reaction(emoji, user)
                # to not clutter the menu with useless reactions
            except Exception:
                pass
            return

        if emoji in emoji_class_dict:

            if entrant := event.get_entrant(user.id):
                emoji_to_remove = class_spec_dict[entrant.category_class]["emoji"]
                try:
                    await message.remove_reaction(emoji_to_remove, user)
                except Exception:
                    pass

            class_name = emoji_class_dict[emoji]

            details = class_spec_dict[class_name]

            valid_specs = [(k, v["emoji"]) for k, v in details["specs"].items()]

            embed = discord.Embed(
                title="Select a spec for the class {}".format(class_name),
                description="\n".join(
                    f"{ind+1}. {spec[1]} {spec[0]}" for ind, spec in enumerate(valid_specs)
                )
                + "\nSend the correct number to select a spec.",
                color=discord.Color.green(),
            )
            try:
                await user.send(embed=embed)

            except Exception:
                await message.channel.send(
                    f"I couldn't dm you to select a spec {user.mention}.\nMake sure your dms are open."
                )
                return

            answer = None
            while answer is None:
                try:
                    msg = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.author == user
                        and not m.guild
                        and m.channel.recipient == user,
                        timeout=60,
                    )

                except asyncio.TimeoutError:
                    await user.send("You took too long to respond. Cancelling.")
                    try:
                        await message.remove_reaction(emoji, user)
                    except Exception:
                        pass
                    return

                if not msg.content.isdigit() or int(msg.content) not in [
                    i + 1 for i in range(len(valid_specs))
                ]:
                    await user.send(
                        f"That's not a valid answer. You must write a number from 1 to {len(valid_specs)}"
                    )
                    continue

                answer = int(msg.content)

            spec = valid_specs[answer - 1][0]

            event.add_entrant(user.id, class_name, details["specs"][spec]["categories"][0], spec)

            await user.send("You have been signed up to the event.")

            embed = event.embed

            await message.edit(embed=embed)

            try:
                await message.remove_reaction(emoji, user)
            except Exception:
                pass

        elif emoji == "❌":
            if not event.author_id == user.id:
                try:
                    await message.remove_reaction(emoji, user)
                except Exception:
                    pass
                return

            try:
                await message.clear_reactions()

            except Exception:
                pass

            embed = event.end()

            await user.send("The event was ended.")

            await message.edit(embed=embed)

        elif emoji == "🧻":
            try:
                await message.remove_reaction(emoji, user)

            except Exception:
                pass

            if entrant := event.get_entrant(user.id):
                event.remove_entrant(entrant)

                await user.send("You have been removed from the event.")

                await message.edit(embed=event.embed)

            else:
                await user.send("You weren't signed up to the event.")

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
            for event in guild_config.values():
                if event.end_time.timestamp() <= time.time():
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

                    await msg.edit(embed=embed)
                    await self.config.custom("events", event.guild_id, event.message_id).clear()
                    del self.cache[event.guild_id][event.message_id]

    @check_events.before_loop
    async def before(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(60)  # wait until all events are cached first
