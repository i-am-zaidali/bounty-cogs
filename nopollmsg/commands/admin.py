from redbot.core import commands

from ..abc import MixinMeta


class Admin(MixinMeta):
    @commands.group(name="nopollmsg", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def nopollmsg(self, ctx: commands.Context):
        """Manage NoPollMessage settings."""
        await ctx.send_help()

    @nopollmsg.command(name="enable")
    @commands.admin_or_permissions(manage_guild=True)
    async def enable_nopollmsg(self, ctx: commands.Context):
        """Enable NoPollMessage in this server."""
        conf = self.db.get_conf(ctx.guild)
        if conf.enabled:
            await ctx.send("NoPollMessage is already enabled in this server.")
            return
        conf.enabled = True
        self.save()
        await ctx.send("NoPollMessage has been enabled in this server.")

    @nopollmsg.command(name="disable")
    @commands.admin_or_permissions(manage_guild=True)
    async def disable_nopollmsg(self, ctx: commands.Context):
        """Disable NoPollMessage in this server."""
        conf = self.db.get_conf(ctx.guild)
        if not conf.enabled:
            await ctx.send("NoPollMessage is already disabled in this server.")
            return
        conf.enabled = False
        self.save()
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
        conf = self.db.get_conf(ctx.guild)
        if not message:
            await ctx.send(
                "The current custom message is: `{}`".format(conf.custom_message)
            )
        conf.custom_message = message
        self.save()
        await ctx.send("Custom poll end message has been set for this server.")

    @set_custom_message.command(name="clear")
    @commands.admin_or_permissions(manage_guild=True)
    async def clear_custom_message(self, ctx: commands.Context):
        """Clear the custom poll end message for this server."""
        conf = self.db.get_conf(ctx.guild)
        conf.custom_message = ""
        self.save()
        await ctx.send("Custom poll end message has been cleared for this server.")
