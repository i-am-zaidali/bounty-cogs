import discord
from redbot.core.bot import Red

from .utilviews import SelectView
from .viewdisableontimeout import ViewDisableOnTimeout, disable_items

__all__ = ["AutoDebindView"]


class AutoDebindView(ViewDisableOnTimeout):
    def __init__(self, ctx, members_to_debind: list[int]):
        super().__init__(timeout=180, allowed_to_interact=[ctx.author.id])

        self.members_to_debind = members_to_debind

    @discord.ui.button(label="Debind All", style=discord.ButtonStyle.danger)
    async def debind_all(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        from ..main import MissionChiefMetrics

        assert isinstance(interaction.client, Red)

        cog = interaction.client.get_cog("MissionChiefMetrics")
        assert isinstance(cog, MissionChiefMetrics)

        conf = cog.db.get_conf(interaction.guild.id)
        userlist = ""
        async with conf:
            for memberid in self.members_to_debind:
                mem = conf.get_member(memberid)
                mem.username, mem.registration_date = None, None
                userlist += (
                    f"- <@{memberid}> ({memberid})\n  - {mem.username}\n"
                )

        disable_items(self)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            "All members have been de-registered.", ephemeral=True
        )

        assert interaction.guild is not None

        logchan = interaction.guild.get_channel(conf.logchannel)
        if logchan:
            embed = discord.Embed(
                color=await interaction.client.get_embed_color(logchan),
                title="Members De-Registered",
                description=f"{len(self.members_to_debind)} members have been de-registered by {interaction.user.mention} ({interaction.user.id}).\n"
                + userlist,
                timestamp=interaction.message.created_at,
            )

            await logchan.send(embed=embed)

    @discord.ui.button(
        label="Debind Selected", style=discord.ButtonStyle.danger
    )
    async def debind_selected(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        from ..main import MissionChiefMetrics

        assert isinstance(interaction.client, Red)

        cog = interaction.client.get_cog("MissionChiefMetrics")
        assert isinstance(cog, MissionChiefMetrics)

        disable_items(self)
        await interaction.response.edit_message(view=self)

        conf = cog.db.get_conf(interaction.guild.id)

        selview = SelectView(
            "Select members to debind",
            [
                discord.SelectOption(label=f"{mid}", value=str(mid))
                for mid in self.members_to_debind
            ],
        )
        await interaction.followup.send(view=selview)

        if await selview.wait():
            return await interaction.followup.send(
                "You took too long to respond. Operation cancelled.",
                ephemeral=True,
            )

        userlist = ""
        async with conf:
            for mid in selview.selected:
                mem = conf.get_member(int(mid))
                userlist += f"- <@{mid}> ({mid})\n  - {mem.username}\n"
                mem.username, mem.registration_date = None, None

        logchan = interaction.guild.get_channel(conf.logchannel)
        if logchan:
            embed = discord.Embed(
                color=await interaction.client.get_embed_color(logchan),
                title="Members De-Registered",
                description=f"{len(self.members_to_debind)} members have been de-registered by {interaction.user.mention} ({interaction.user.id}).\n"
                + userlist,
                timestamp=interaction.message.created_at,
            )

            await logchan.send(embed=embed)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        disable_items(self)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("Operation cancelled.", ephemeral=True)
