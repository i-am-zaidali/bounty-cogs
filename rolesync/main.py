from operator import attrgetter

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .views import GuildSelectView


class RoleSync(commands.Cog):
    """A cog that syncs roles and their properties across multiple servers."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        self.config.register_guild(roles={}, synced_roles={})

    @commands.group(name="rolesync", aliases=["rsync"], invoke_without_command=True)
    @commands.guild_only()
    @commands.is_owner()
    async def rs(self, ctx: commands.Context):
        """Sync role states between guilds"""
        await ctx.send_help()

    @rs.command(name="add")
    async def rs_add(self, ctx: commands.Context, role: discord.Role):
        """Add a role to sync between guild

        The role argument must be a role mention or ID.
        The guilds argument accepts guild IDs"""
        view = GuildSelectView(ctx)
        if not view.guilds or len(view.guilds) < 2:
            return await ctx.send(
                """
                Not enough guilds found to select where roles can be synced.
                The user and the bot must have the following permissions in the guilds:
                - manage_guild
                - manage_roles
                - manage_permissions
                """.strip()
            )
        msg = await ctx.send(
            "Please select a max of 2 guilds from the below list where the given role will be synced.",
            view=view,
        )
        if await view.wait():
            [setattr(item, "disabled", True) for item in view.children]
            await msg.edit(view=view)
            return await ctx.send("Sync cancelled.")

        guilds = view.chosen_guilds

        async with self.config.guild(ctx.guild).roles() as roles:
            roles[role.id] = list(
                set(roles.get(role.id, [])).union(map(attrgetter("id"), guilds))
            )

            for guild in guilds:
                async with self.config.guild(guild).synced_roles() as synced_roles:
                    if not synced_roles.get(str(role.id)):
                        synced_roles[role.id] = (
                            await guild.create_role(
                                name=role.name,
                                permissions=role.permissions,
                                colour=role.colour,
                                hoist=role.hoist,
                                mentionable=role.mentionable,
                                reason=f"Synced from {ctx.guild.name}",
                            )
                        ).id

            await ctx.tick()
            return await ctx.send(f"Synced {role.mention} in given guilds")

    @rs.command(name="remove")
    async def rs_remove(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from being synced between guilds."""
        async with self.config.guild(ctx.guild).roles() as roles:
            role_id_str = str(role.id)
            if role_id_str not in roles:
                return await ctx.send("This role is not synced to any guilds.")

            for gid in roles[role_id_str]:
                guild = self.bot.get_guild(gid)
                if guild is None:
                    continue

                async with self.config.guild(guild).synced_roles() as synced_roles:
                    if role_id_str in synced_roles:
                        sr = guild.get_role(synced_roles[role_id_str])
                        if sr is not None:
                            await sr.delete(reason=f"Unsynced from {ctx.guild.name}")
                        # Remove the role from the synced_roles in this guild
                        del synced_roles[role_id_str]

            # Remove the role from the original guild's roles list
            del roles[role_id_str]

        await ctx.tick()
        return await ctx.send(f"Removed {role.mention} from sync")

    @rs.command(name="list")
    async def rs_list(self, ctx: commands.Context):
        """List synced roles"""
        roles = await self.config.guild(ctx.guild).roles()
        if not roles:
            return await ctx.send("No roles are synced in this guild.")

        messages = []
        current_message = ""

        for role_id, guilds in roles.items():
            role = ctx.guild.get_role(int(role_id))
            if role is None:
                continue

            role_info = f"- {role.mention} synced in {len(guilds)} guilds\n"
            for gid in guilds:
                guild = self.bot.get_guild(gid)
                if guild is None:
                    continue
                synced_role_id = await self.config.guild(guild).synced_roles.get_raw(role_id, default=None)
                if synced_role_id is None:
                    continue
                synced_role = guild.get_role(synced_role_id)
                if not synced_role:
                    continue
                role_info += f"\t- {guild.name}: {synced_role.id}\n"

            role_info += "\n"

            # Check if adding this role info would exceed the 2000 character limit
            if len(current_message) + len(role_info) > 2000:
                messages.append(current_message)
                current_message = role_info
            else:
                current_message += role_info

        # Append the last message if it contains any content
        if current_message:
            messages.append(current_message)

        for message in messages:
            await ctx.send(message)

    @rs.command(name="forcesync", aliases=["fsync"])
    async def rs_fsync(self, ctx: commands.Context):
        roles = await self.config.guild(ctx.guild).roles()
        if not roles:
            return await ctx.send("No roles are synced in this guild.")

        for role_id, guilds in roles.items():
            role = ctx.guild.get_role(int(role_id))
            if role is None:
                continue

            role1 = {
                "name": role.name,
                "permissions": role.permissions,
                "colour": role.colour,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
            }

            for gid in guilds:
                guild = self.bot.get_guild(gid)
                if guild is None:
                    continue

                synced_role_id = await self.config.guild(guild).synced_roles.get_raw(str(role_id), default=None)
                if synced_role_id is None:
                    continue

                r = guild.get_role(synced_role_id)
                if r is None:
                    await ctx.send(f"Role with ID {synced_role_id} not found in guild {guild.name}.")
                    continue

                role2 = {
                    "name": r.name,
                    "permissions": r.permissions,
                    "colour": r.colour,
                    "hoist": r.hoist,
                    "mentionable": r.mentionable,
                }

                if role1 != role2:
                    await r.edit(
                        name=role.name,
                        permissions=role.permissions,
                        colour=role.colour,
                        hoist=role.hoist,
                        mentionable=role.mentionable,
                    )

        await ctx.tick()

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        async with self.config.guild(before.guild).roles() as roles:
            if str(before.id) not in roles:
                return

            for gid in roles[str(before.id)]:
                guild = self.bot.get_guild(gid)
                if guild is None:
                    continue

                async with self.config.guild(guild).synced_roles() as synced_roles:
                    if str(before.id) in synced_roles:
                        sr = guild.get_role(synced_roles[str(before.id)])
                        if sr is None:
                            continue
                        await sr.edit(
                            name=after.name,
                            permissions=after.permissions,
                            colour=after.colour,
                            hoist=after.hoist,
                            mentionable=after.mentionable,
                        )
