import discord
import asyncio
import time

from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.menus import start_adding_reactions
from typing import Dict, Optional

from .model import Flags, Event
from .constants import emoji_class_dict, class_spec_dict, Category

class EventManager(commands.Cog):
    """A cog to create and manage events."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=0x352567829, force_registration=True
        )
        self.config.init_custom("events", 2)
        self.cache: Dict[int, Dict[int, Event]] = {}
        
    async def initialize(self):
        all_guilds = await self.config.custom("events").all()
        for guild_id, guild_config in all_guilds.items():
            g = self.cache.setdefault(int(guild_id), {})
            for event in guild_config.values():
                g.setdefault(event["message_id"], Event.from_json(self.bot, event))
                
    async def to_cache(self):
        for guild_config in self.cache.values():
            for event in guild_config.values():
                json = event.json
                await self.config.custom("events").set_raw(event.guild_id, event.message_id, value=json)
                
    def cog_unload(self):
        asyncio.create_task(self.to_cache())
        
    @commands.command(name="event")
    async def event(self, ctx: commands.Context, *, flags: Flags):
        """
        Start an event.
        
        Valid flags are:
        `--end` - The time the event ends.
        `--image` - The image to use for the event.
        `--name` - The name of the event.
        `--description` - The description of the event.
        `--channel` - The channel to post the event in. [optional]
        """
        flags["channel_id"] = flags.get("channel_id") or ctx.channel.id
        event = Event(ctx.bot, message_id=ctx.message.id, guild_id=ctx.guild.id, author_id=ctx.author.id, **flags)
        msg = await ctx.send(embed=event.embed)
        event.message_id = msg.id
        start_adding_reactions(msg, [i for i in emoji_class_dict.keys()] + ["❌"])
        self.cache.setdefault(ctx.guild.id, {})[msg.id] = event
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        
        if not (data:=self.cache.get(payload.guild_id)):
            return
        
        if not (event:=data.get(payload.message_id)):
            return
        
        message = await event.message()
        
        if not message:
            return # idk what could be the reason message is none tbh.
        
        user: Optional[discord.User] = self.bot.get_user(payload.user_id)
         
        if not user:
            return
        
        if user.bot:
            return
        
        emoji = str(payload.emoji)
        
        if not emoji in emoji_class_dict and emoji != "❌":
            try:
                await message.remove_reaction(emoji, user)
                # to not clutter the menu with useless reactions
            except Exception:
                pass
            return
        
        if emoji in emoji_class_dict:
            
            if (entrant:=event.get_entrant(user.id)):
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
                description="\n".join(f"{ind+1}. {spec[0]} {spec[1]}" for ind, spec in enumerate(valid_specs)) + \
                    "\nSend the correct number to select a spec.",
                color=discord.Color.green()
            )
            try:
                await user.send(embed=embed)
            
            except Exception:
                await message.channel.send(f"I couldn't dm you to select a spec {user.mention}.\nMake sure your dms are open.")
                return
            
            try:
                msg = await self.bot.wait_for(
                    "message", 
                    check=lambda m: 
                        m.author == user and
                        not m.guild and 
                        m.channel.recipient == user and 
                        int(m.content) in [1, 2, 3], 
                    timeout=60
                )
                
            except asyncio.TimeoutError:
                await user.send("You took too long to respond. Cancelling.")
                try:
                    await message.remove_reaction(emoji, user)
                except Exception:
                    pass
                return
            
            spec = valid_specs[int(msg.content) - 1][0]
            
            event.add_entrant(user.id, class_name, details["specs"][spec]["categories"][0], spec)
            
            await user.send("You have been signed up to the event.")
            
            embed = event.embed
            
            await message.edit(embed=embed)
            
        else:
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
            
    @tasks.loop(seconds=5)
    async def check_events(self):
        for guild_config in self.cache.values():
            for event in guild_config.values():
                if event.end_time.timestamp() <= time.time():
                    embed = event.end()
                    await event.message().edit(embed=embed)