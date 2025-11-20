import typing as t

import discord
from redbot.core import Config, commands


class NoPollMsg(commands.Cog):
    """A cog to suppress discord's built in poll end message and
    optionally replace with a custom message."""

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "enabled": False,
            "custom_message": "The poll for [{poll_question}]({poll_url}) has ended! The winning option was: `{winning_option}` with `{winning_votes}` votes out of {total_votes} votes.",
        }
        self.config.register_guild(**default_guild)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    def get_poll_format_map(self, message: discord.Message) -> dict[str, t.Any]:
        """Generate the format map for the poll end message."""
        fields = message.embeds[0].fields
        format_map: dict[str, t.Any] = {}
        for field in fields:
            if field.name == "poll_question_text":
                format_map["poll_question"] = field.value
            elif field.name == "victor_answer_text":
                format_map["winning_option"] = field.value
            elif field.name == "victor_answer_votes":
                format_map["winning_votes"] = int(field.value)
            elif field.name == "total_votes":
                format_map["total_votes"] = int(field.value)

        message.reference.guild_id = message.guild.id
        format_map["poll_url"] = message.reference.jump_url
        return format_map

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if self.db.get_conf(message.guild).enabled is False:
            return
        if message.type == discord.MessageType.poll_result:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

            custom_message = self.db.get_conf(message.guild).custom_message
            if not custom_message:
                return
            format_map = self.get_poll_format_map(message)
            await message.channel.send(custom_message.format_map(format_map))

    @commands.group(name="nopollmsg", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def nopollmsg(self, ctx: commands.Context):
        """Manage NoPollMessage settings."""
        await ctx.send_help()

    @nopollmsg.command(name="enable")
    @commands.admin_or_permissions(manage_guild=True)
    async def enable_nopollmsg(self, ctx: commands.Context):
        """Enable NoPollMessage in this server."""
        conf = await self.config.guild(ctx.guild).all()
        if conf["enabled"]:
            await ctx.send("NoPollMessage is already enabled in this server.")
            return
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("NoPollMessage has been enabled in this server.")

    @nopollmsg.command(name="disable")
    @commands.admin_or_permissions(manage_guild=True)
    async def disable_nopollmsg(self, ctx: commands.Context):
        """Disable NoPollMessage in this server."""
        conf = await self.config.guild(ctx.guild).all()
        if not conf["enabled"]:
            await ctx.send("NoPollMessage is already disabled in this server.")
            return
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("NoPollMessage has been disabled in this server.")

    @nopollmsg.group(name="custommessage", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def set_custom_message(self, ctx: commands.Context, *, message: str = ""):
        """Set a custom poll end message for this server.

        You can use the following placeholders in your message:
        - {poll_question}
        - {poll_url}
        - {winning_option}
        - {winning_votes}
        - {total_votes}

        use `[p]nopollmsg custommessage clear` to remove the custom message completely.
        """
        conf = await self.config.guild(ctx.guild).all()
        if not message:
            await ctx.send(
                "The current custom message is: `{}`".format(conf["custom_message"])
            )
        await self.config.guild(ctx.guild).custom_message.set(message)
        await ctx.send("Custom poll end message has been set for this server.")

    @set_custom_message.command(name="clear")
    @commands.admin_or_permissions(manage_guild=True)
    async def clear_custom_message(self, ctx: commands.Context):
        """Clear the custom poll end message for this server."""
        await self.config.guild(ctx.guild).custom_message.set("")
        await ctx.send("Custom poll end message has been cleared for this server.")
