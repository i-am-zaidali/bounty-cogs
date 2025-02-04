import discord
from redbot.core import commands

from ..abc import CompositeMetaClass, MixinMeta

ordinals = [
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
]


class Listeners(MixinMeta, metaclass=CompositeMetaClass):
    """
    Subclass all listeners in this directory so you can import this single Listeners class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """

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

        conf = self.db.get_conf(member.guild.id)
        async with conf:
            conf.recently_joined_msgs[member.id] = 0

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        conf = self.db.get_conf(member.guild.id)
        if not conf.recently_joined_msgs.get(member.id):
            return
        async with conf:
            conf.recently_joined_msgs.pop(member.id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        conf = self.db.get_conf(message.guild.id)
        conf.recently_joined_msgs.setdefault(message.author.id, 0)
        conf.recently_joined_msgs[message.author.id] += 1
        amount = conf.recently_joined_msgs[message.author.id]

        if (
            conf.alert_channel
            and (channel := message.guild.get_channel(conf.alert_channel))
            and conf.recently_joined_msgs.get(message.author.id) is not None
        ):
            embed = discord.Embed(
                title=f"{message.author.display_name} ({message.author.id})'s first words!",
                description=f"""
                {message.author.mention} just {"said their first words in the server!" if amount == 1 else f"sent their {self.get_ordinal(amount)} message in the server!"}
                Here's a preview:
                > [{self.trim_string(message.content, max_length=100)}]({message.jump_url})
                > Sent at: {discord.utils.format_dt(message.created_at, "F")}
                > Channel: {message.channel.mention}""",
                color=discord.Color.green(),
            )
            await channel.send(embed=embed)

        if amount > conf.alert_x_messages:
            async with conf:
                conf.recently_joined_msgs.pop(message.author.id, None)
