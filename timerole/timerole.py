"""
This cog and its original idea belongs to Bobloy (https://github.com/bobloy)
This fork is merely a rewrite of his cog for optimization and cetain additional functionalities. 
Almost none of the original cog's code was taken for this rewrite except for the concept of its functionality.
All credits go to bobloy and I do not assume ownership of the cog."""
from itertools import zip_longest
from typing import Dict, List
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, pagify, humanize_timedelta, box
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import logging
from tabulate import tabulate
from discord.ext import tasks
from datetime import datetime, timezone
import discord
import asyncio
import re

from .obj import TimedRole

log = logging.getLogger("red.cTm.timerole")

class TimeConverter(commands.Converter):
    time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d|w))+?")
    time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400, "w": 604800}

    async def convert(self, ctx, argument):
        args = argument.lower()
        matches = re.findall(self.time_regex, args)
        time = 0
        if not matches:
            raise commands.BadArgument("Invalid time format. h|m|s|d are valid arguments.")
        for key, value in matches:
            try:
                time += self.time_dict[value] * float(key)
            except KeyError:
                raise commands.BadArgument(
                    f"{value} is an invalid time key! h|m|s|d are valid arguments"
                )
            except ValueError:
                raise commands.BadArgument(f"{key} is not a number!")

        return time


class TimeRole(commands.Cog):
    """
    Add or remove roles from members based on the amount of time they have been in the server."""
    
    __author__ = ["crayyy_zee#2900", "Bobloy"]
    __version__ = "1.0.2"
    
    def __init__(self, bot: Red):
        self.bot = bot
        
        self.cache: Dict[int, List[TimedRole]] = {}
        self.role_task = self.role_loop.start()
        
        self.config = Config.get_conf(self, 25, True)
        self.config.register_guild(remove_roles={}, add_roles={}, announce_channel=None, check_bots=False, reapply=False)
        self.config.register_member(already_added=[])
        # config will be structure like this:
        # {  guild_id:
        #      {
        #          "remove_roles": {123: {"delay": 234, "required": []}}, # {role_id: {delay to remove after, required roles}}
        #          "add_roles": {123: {"delay": 234, "required": []}}, # {role_id: {delay to add after, required roles}},
        #          "announce_channel": 123, # channel_id to announce in
        #          "check_bots": False # whether to remove roles from bots
        #          "reapply": False # whether to reapply roles to members that have somehow lost it
        #      }
        #    member_id:
        #      {alread_added: [123, 234, 567] # list of roles that have been added to this member already.
        # }
        
    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)
        
    async def to_config(self):
        log.debug("Saving TimedRoles to Config...")
        to_save = {}
        for guild_id, guild_data in self.cache.copy().items():
            to_save[guild_id] = {
                "remove_roles": {x.id: x.json for x in guild_data if x.mode == "remove"},
                "add_roles": {x.id: x.json for x in guild_data if x.mode == "add"},
            }
            log.debug(f"Saving TimedRoles for {guild_id}\n{to_save[guild_id]}")
            async with self.config.guild_from_id(guild_id).all() as g_data:
                g_data["remove_roles"] = to_save[guild_id]["remove_roles"]
                g_data["add_roles"] = to_save[guild_id]["add_roles"]
                log.debug(f"Inside Config Context Manager. {g_data=}")
            
        log.debug("TimedRoles saved to Config.")
        log.debug("======================================================")
    
    def cog_unload(self) -> None:
        log.debug("Unloading TimedRoles...")
        self.role_loop.cancel()
        asyncio.create_task(self.to_config())
        
    @tasks.loop(hours=1)
    async def role_loop(self):
        if not self.cache:
            return
        
        log.debug("Running role_loop...")
        log.debug("======================================================")
        
        for all_roles in self.cache.copy().values():
            log.debug(f"{all_roles=}")
            announce_message = ""
            
            members_to_edit: Dict[discord.Member, List[discord.Role]] = {}
            # the members whose roles need to be added/removed
            
            to_add = list(filter(lambda x: x.mode =="add", all_roles))
            # the timedroles that are to be added
            
            log.debug(f"{to_add=}")
            
            to_remove = list(filter(lambda x: x.mode == "remove", all_roles))
            # the timedroles that are to be removed
            
            log.debug(f"{to_remove=}")
            
            for add_role, remove_role in zip_longest(to_add, to_remove, fillvalue=None):
                # zipping to decrease the use of multiple loops for each list.
                log.debug(f"{add_role=} {remove_role=}")
                
                if add_role: # can be none due to zip_longest
                    if not add_role.role: # incase the role has been deleted
                        log.debug(f"Removing add_role due to role being deleted {add_role.id=}")
                        self.cache[add_role.guild_id].remove(add_role) # delete it from cache, config will reflect later.
                        
                    else:
                        filtered_members = await add_role.filter_members_without_role()
                        log.debug(f"filtered_members for add_role {add_role.id}:\n{filtered_members=}")
                        reapply = await self.config.guild_from_id(add_role.guild_id).reapply()
                        to_update = {
                            member: members_to_edit.get(member, member.roles) + [add_role.role]
                            for member in filtered_members
                            if ((add_role.id not in await self.config.member(member).already_added()) or (reapply is True))
                            # check if the role was already added to the member, if it was, check if reapply is enabled else dont add.
                            and member.joined_at is not None # This can be none if the user is lurking aka viewing server from discovery
                            and (not (datetime.now(tz=timezone.utc) - member.joined_at) >= rr[0].delay if (rr:=list(filter(lambda x: x.id == add_role.id, to_remove))) != [] else True)
                            # check if the role is not to be removed too, if it is, dont add.
                        }
                        log.debug(f"to_update for add_role {add_role.id}:\n{to_update=}")
                        members_to_edit.update(to_update)
                        # update the members to edit dict with the members that need to be added the role
                        # if the role has not been added to the member already or if reapply is enabled
                
                if remove_role: # can be none due to zip_longest
                    if not remove_role.role: # incase the role has been deleted
                        self.cache[remove_role.guild_id].remove(remove_role) # delete it from cache, config will reflect later.
                        
                    else:
                        filtered_members = await remove_role.filter_members_with_role()
                        log.debug(f"filtered_members for remove_role {remove_role.id}:\n{filtered_members=}")
                        to_update = {
                            # filtering out the remove_role from the members roles
                            member: list(filter(lambda x: x.id != remove_role.id, members_to_edit.get(member, member.roles)))
                            for member in filtered_members
                        }
                        log.debug(f"to_update for remove_role {remove_role.id}:\n{to_update=}")
                        members_to_edit.update(to_update)
                        # update the members to edit dict with the members that need to be removed the role
            
            log.debug(f"{members_to_edit=}")
            
            for member, roles in members_to_edit.items():
                org_roles = member.roles
                # The original roles of the member.
                
                if org_roles == roles: 
                    # this condition could be true incase the same role is added for both adding 
                    # and removing in a certain interval
                    log.debug(f"Nothing to update for member {member.id}. Continuing...")
                    continue
                
                update_roles_for_member = set(roles).difference(org_roles).difference(await self.config.member(member).already_added()) 
                # the newly added roles for the member
                # this is a set of Role objects, which are:
                # 1. Not present in the member's roles
                # 2. Not already added to the member once before
                
                async with self.config.member(member).already_added() as already_added:
                    already_added.extend((r.id for r in update_roles_for_member if r.id not in already_added))
                    log.debug(f"{member.id=} {already_added=}")
                    # add the role object ids to the already_added list in config
                
                try:
                    await member.edit(roles=roles, reason="Updating TimedRoles.")
                    # completely edit the member with the new roles.
                except (discord.Forbidden):
                    log.error(f"Missing Permissions to edit {member.id} in guild {member.guild.id}")
                    announce_message += f"I do not have valid permissions to manage the roles of {member.mention}.\n\n"
                except Exception as e:
                    log.exception("Exception when editing member: ", exc_info=e)
                else:
                    log.debug(f"Roles have been updated for {member.id=}")
                    roles_that_were_added = set(roles).difference(org_roles)
                    roles_that_were_removed = set(org_roles).difference(roles)
                
                    announce_message += f"**{member.mention}'s roles have been updated: **"
                
                    if roles_that_were_added:
                        announce_message += f"\n**Added:** {humanize_list([r.mention for r in roles_that_were_added])}"
                        
                    if roles_that_were_removed:
                        announce_message += f"\n**Removed:** {humanize_list([r.mention for r in roles_that_were_removed])}"
                        
                    announce_message += "\n\n"
                
            if announce_message and (chan_id:=await self.config.guild(member.guild).announce_channel()):
                chan = member.guild.get_channel(chan_id)
                if chan:
                    embeds = [discord.Embed(title="TimeRole Updates!", description=page) for page in pagify(announce_message, delims=["\n\n"], page_length=2000)]
                    
                    for embed in embeds:
                        await chan.send(embed=embed)
                        
                else:
                    await self.config.guild(member.guild).announce_channel.set(None)
            
        await self.to_config()
                
    @role_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_red_ready()
        
        all_guilds = await self.config.all_guilds()
        
        if not all_guilds:
            log.debug("No guilds configured for timeroles.")
            return self
        
        for guild_id, guild_data in all_guilds.items():
            log.debug(f"Caching timerole for {guild_id=}")
            log.debug(f"{guild_data=}")
            self.cache[guild_id] = TimedRole.multiple_from_config(self.bot, guild_id, "add", guild_data["add_roles"]) + TimedRole.multiple_from_config(self.bot, guild_id, "remove", guild_data["remove_roles"])
            log.debug(f"{self.cache[guild_id]=}")
            
        log.debug("Cache initialized with %s guilds", len(self.cache))
            
        
        log.debug("TimedRoles loaded. role_task started.")
                
    @commands.group(name="timerole", invoke_without_command=True)
    async def timerole(self, ctx: commands.Context):
        """
        The base command for all timerole settings and configurations."""
        await ctx.send_help()
    
    @timerole.command(name="forcecheck", aliases=["force"], hidden=True)
    @commands.is_owner()
    async def timerole_force(self, ctx: commands.Context):
        async with ctx.typing():
            await ctx.send("Force checking roles in all registered guilds...")
            await self.role_loop()
            await ctx.send("Done.")
            
    @timerole.group(name="addrole", invoke_without_command=True)
    async def timerole_addrole(self, ctx: commands.Context, role: discord.Role = None, required_roles: commands.Greedy[discord.Role] = [], *, time: TimeConverter = None):
        """
        Set a role to be added to a member certain time after they have joined the server.
        
        This command doubles as a list command to show all conifgured timeroles to be added.
        
        The time is specified in the format `[days]d [hours]h [minutes]m [seconds]s`.
        """
        if not role or not time:
            all_roles =self.cache.get(ctx.guild.id)
            
            if not all_roles:
                await ctx.send("No timeroles to add are configured for this guild.")
                return
            
            data = [(f"@{r.role.name}", r.id, humanize_timedelta(timedelta=r.delay)) for r in all_roles if r.mode == "add"]
            headers = ["Role Name", "ID", "Delay after member join"]
            
            tabbed = tabulate(data, headers, tablefmt="rst", numalign="left", stralign="left")
            
            pages = []
            
            for page in pagify(tabbed, delims=["\n"], page_length=2500):
                page = f"Configured TimeRoles to add in __**{ctx.guild.name}**__" + "\n\n" + page + "\n\n"
                pages.append(box(page, lang="html"))

            if len(pages) == 1:
                return await ctx.send(pages[0])
            return await menu(ctx, pages, DEFAULT_CONTROLS)
        
        elif not role or not time:
            return await ctx.send_help()
        
        tr = TimedRole(ctx.bot, ctx.guild.id, role.id, time, [r.id for r in required_roles], "add")
        
        self.cache.setdefault(ctx.guild.id, []).append(tr)
        
        return await ctx.send(f"New TimeRole added! {role.mention} to be assigned **{humanize_timedelta(timedelta=tr.delay)}** after member join.")
    
    @timerole_addrole.command(name="delete", aliases=["remove", "del", "rm"])
    async def timerole_addrole_remove(self, ctx: commands.Context, role: discord.Role):
        """
        Remove an adding TimeRole from config.
        
        This role will no longer be applied."""
        
        found = list(filter(lambda r: r.id == role.id, self.cache.get(ctx.guild.id, [])))
        
        if not found:
            return await ctx.send("I couldn't find that timerole.")
        
        self.cache.get(ctx.guild.id).remove(found[0])
        
        return await ctx.send("That timerole has been removed and shall no longer be added.")
    
    @timerole.group(name="removerole", invoke_without_command=True)
    async def timerole_removerole(self, ctx: commands.Context, role: discord.Role = None, required_roles: commands.Greedy[discord.Role] = [], *, time: TimeConverter = None):
        """
        Set a role to be removed from a member certain time after they have joined the server.
        
        This command doubles as a list command to show all conifgured timeroles to be removed.
        
        The time is specified in the format `[days]d [hours]h [minutes]m [seconds]s`.
        """
        if not role and not time:
            all_roles =self.cache.get(ctx.guild.id)
            
            if not all_roles:
                await ctx.send("No timeroles to remove are configured for this guild.")
                return
            
            data = [(f"@{r.role.name}", r.id, humanize_timedelta(timedelta=r.delay)) for r in all_roles if r.mode == "remove"]
            headers = ["Role Name", "ID", "Delay after member join"]
            
            tabbed = tabulate(data, headers, tablefmt="rst", numalign="left", stralign="left")
            
            pages = []
            
            for page in pagify(tabbed, delims=["\n"], page_length=2500):
                page = f"Configured TimeRoles to remove in __**{ctx.guild.name}**__" + "\n\n" + page + "\n\n"
                pages.append(box(page, lang="html"))

            if len(pages) == 1:
                return await ctx.send(pages[0])
            return await menu(ctx, pages, DEFAULT_CONTROLS)
        
        elif not role or not time:
            return await ctx.send_help()
        
        tr = TimedRole(ctx.bot, ctx.guild.id, role.id, time, [r.id for r in required_roles], "remove")
        
        self.cache.setdefault(ctx.guild.id, []).append(tr)
        
        return await ctx.send(f"New TimeRole added! {role.mention} to be removed **{humanize_timedelta(timedelta=tr.delay)}** after member join.")
    
    @timerole_removerole.command(name="delete", aliases=["remove", "del", "rm"])
    async def timerole_removerole_remove(self, ctx: commands.Context, role: discord.Role):
        """
        Remove a removing TimeRole from config.
        
        This role will no longer be applied."""
        
        found = list(filter(lambda r: r.id == role.id, self.cache.get(ctx.guild.id, [])))
        
        if not found:
            return await ctx.send("I couldn't find that timerole.")
        
        self.cache.get(ctx.guild.id).remove(found[0])
        
        return await ctx.send("That timerole has been removed and shall no longer be removed from users.")
    
    @timerole.command(name="announcechannel", aliases=["announcementchannel", "chan", "channel"])
    async def timerole_announcechannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the channel to send announcements to.
        
        This channel will be used to send announcements about timeroles.
        """
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        
        return await ctx.send(f"Announcements will be sent to {channel.mention}.")
    
    @timerole.command(name="reapply")
    async def timerole_reapply(self, ctx: commands.Context, status: bool):
        """
        Set whether adding timeroles should be readded incase they somehow get removed from the member."""
        
        await self.config.guild(ctx.guild).reapply.set(status)
        
        return await ctx.send(f"Adding timeroles will be {'reapplied' if status else 'no longer reapplied'}.")
    
    @timerole.command(name="checkbots")
    async def timerole_checkbots(self, ctx: commands.Context, status: bool):
        """
        Set whether timeroles should be applied to bots."""
        
        await self.config.guild(ctx.guild).check_bots.set(status)
        
        return await ctx.send(f"Adding timeroles will be {'checked' if status else 'no longer checked'} for bots.")
    
    @timerole.command(name="showsettings", aliases=["settings", "ss", "show"])
    async def timerole_showsettings(self, ctx: commands.Context):
        """
        Show the current settings for this guild."""
        
        humanize_bool = lambda b: "Enabled" if b is True else "Disabled"
        
        chan_id = await self.config.guild(ctx.guild).announce_channel()
        chan = ctx.guild.get_channel(chan_id) if chan_id else None
        chan_str = f"#{chan.name}" if chan else "Not set"
        
        reapply = humanize_bool(await self.config.guild(ctx.guild).reapply())
        
        check_bots = humanize_bool(await self.config.guild(ctx.guild).check_bots())
        
        data = [("Announcement Channel", chan_str),
                ("Reapply", reapply),
                ("Check Bots", check_bots)]
        
        headers = ["Setting", "Value"]
        
        tabbed = tabulate(data, headers, tablefmt="rst", numalign="left", stralign="left")
        
        return await ctx.send(box(tabbed, lang="html"))
