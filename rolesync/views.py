import discord
from discord.ui import View, Select
from redbot.core import commands


class GuildSelect(Select["GuildSelectView"]):
    def __init__(self, ctx: commands.Context, guilds: list[discord.Guild]):
        super().__init__(placeholder="Select guilds to sync role to", min_values=1, max_values=2)
        self.ctx = ctx
        self.guilds = guilds

        for guild in guilds[:25]:
            self.add_option(label=guild.name, value=str(guild.id))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.chosen_guilds = [self.ctx.bot.get_guild(int(val)) for val in self.values]
        self.view.stop()


class GuildSelectView(View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=60)
        self.chosen_guilds: list[discord.Guild]
        self.bot = ctx.bot
        self.user = ctx.author
        req_perms = discord.Permissions(
            manage_guild=True, manage_roles=True, manage_permissions=True
        )
        guilds = [
            guild
            for guild in self.bot.guilds
            if guild.me.guild_permissions >= req_perms
            and guild.get_member(self.user.id) is not None
            and guild.get_member(self.user.id).guild_permissions >= req_perms
        ]
        self.add_item(GuildSelect(ctx, guilds))

    async def interaction_check(self, inter: discord.Interaction):
        if not inter.user.id == self.user.id:
            await inter.response.send_message("You cannot use this menu.", ephemeral=True)
            return False

        return True
