import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.vendored.discord.ext import menus

from .views import Paginator


class FirstWords(commands.Cog):
    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            alert_channel=None,
            alert_x_messages=1,
            recently_joined_msgs={},
        )

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    @staticmethod
    def trim_string(string: str, *, max_length: int):
        return string[:max_length] + "..." if len(string) > max_length else string

    @staticmethod
    def get_ordinal(number: int) -> str:
        if 10 <= number % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
        return f"{number}{suffix}"

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        async with self.config.guild(
            member.guild
        ).recently_joined_msgs() as recently_joined_msgs:
            recently_joined_msgs[member.id] = 0

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        conf: dict[int, int] = await self.config.guild(
            member.guild
        ).recently_joined_msgs()
        if not conf.get(member.id):
            return
        async with self.config.guild(
            member.guild
        ).recently_joined_msgs() as recently_joined_msgs:
            recently_joined_msgs.pop(member.id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        conf = await self.config.guild(message.guild).all()
        id = str(message.author.id)
        if conf["recently_joined_msgs"].get(id) is None:
            return
        conf["recently_joined_msgs"][id] += 1
        amount = conf["recently_joined_msgs"][id]

        if (
            conf["alert_channel"]
            and (channel := message.guild.get_channel(conf["alert_channel"]))
            and conf["recently_joined_msgs"].get(id) is not None
        ):
            embed = discord.Embed(
                title=f"{message.author.display_name} ({id})'s first words!",
                description=f"""
                {message.author.mention} just {"said their first words in the server!" if amount == 1 else f"sent their {self.get_ordinal(amount)} message in the server!"}
                Here's a preview:
                > [{self.trim_string(message.content, max_length=100)}]({message.jump_url})
                > Sent at: {discord.utils.format_dt(message.created_at, "F")}
                > Channel: {message.channel.mention}""",
                color=discord.Color.green(),
            )
            await channel.send(embed=embed)

        async with self.config.guild(
            message.guild
        ).recently_joined_msgs() as recently_joined_msgs:
            if amount > conf["alert_x_messages"]:
                recently_joined_msgs.pop(id, None)

            else:
                recently_joined_msgs[id] = amount

    @commands.group(name="firstwords")
    @commands.admin()
    async def firstwords(self, ctx: commands.Context):
        """First Words cog settings"""

    @firstwords.command(name="alertchannel")
    async def alertchannel(
        self, ctx: commands.Context, channel: discord.TextChannel | None = None
    ):
        """Set the channel for first words alerts"""
        await self.config.guild(ctx.guild).alert_channel.set(
            channel.id if channel else None
        )
        await ctx.send(
            f"Alert channel set to {channel.mention}"
            if channel
            else "Alert channel removed"
        )

    @firstwords.command(name="alertmessages")
    async def alertmessages(self, ctx: commands.Context, amount: int):
        """Set the amount of messages sent to alert on"""
        await self.config.guild(ctx.guild).alert_x_messages.set(amount)
        await ctx.send(f"Alerting on {amount} messages")

    @firstwords.command(name="stillsilent")
    async def stillsilent(self, ctx: commands.Context):
        """Shows a paginated list of users that have been silent since they joined the server."""

        conf = await self.config.guild(ctx.guild).all()

        class StillSilentSource(menus.ListPageSource):
            async def format_page(self, menu: Paginator, items: list[discord.Member]):
                return discord.Embed(
                    title="Silent Users",
                    description="\n".join(
                        [
                            f"{ind}. {m.mention} ({m.id})\n"
                            f"  - Joined at: {discord.utils.format_dt(m.joined_at, 'F')}\n"
                            f"  - Messages sent: {conf['recently_joined_msgs'].get(str(m.id)):,}\n"
                            for ind, m in enumerate(items)
                        ]
                    ),
                    timestamp=menu.ctx.message.created_at,
                )

        silent_members = [
            member
            for m in conf["recently_joined_msgs"]
            if (member := ctx.guild.get_member(int(m))) is not None
        ]
        if not silent_members:
            await ctx.send("No silent users yet.")
            return

        paginator = Paginator(StillSilentSource(silent_members, per_page=6))
        await paginator.start(ctx)
