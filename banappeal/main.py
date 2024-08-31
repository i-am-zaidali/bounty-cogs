import asyncio
import contextlib
import discord
from discord import app_commands
import discord.ui
import itertools
from redbot.core import commands, Config
from redbot.core.bot import Red
import typing
from .views import BannedGuildsSelect, AcceptRejectButton, ViewDisableOnTimeout
from discord.utils import maybe_coroutine
from redbot.core.utils import chat_formatting as cf
import logging

log = logging.getLogger("red.bounty.banappeal")

P = typing.ParamSpec("P")
T = typing.TypeVar("T")
MaybeAwaitable = typing.Union[T, typing.Coroutine[typing.Any, typing.Any, T]]
MaybeAwaitableFunc = typing.Callable[P, MaybeAwaitable[T]]
RT = typing.TypeVar("RT")


def catch(
    func: typing.Optional[MaybeAwaitableFunc[P, T]] = None,
    handler: MaybeAwaitableFunc[[BaseException], RT] = lambda x: None,
    exc_types: typing.Tuple[typing.Type[BaseException], ...] = (Exception,),
):
    """
    A wrapper function that catches exceptions and returns the result of the handler function

    Intended to be used in one liners, e.g.:
    ```py
    await catch(func, handler, exc_types)(*args, **kwargs)
    ```

    But can be used as a decorator as well, e.g.:
    ```
    @catch(handler, exc_types)
    async def func(*args, **kwargs):
        ...
        # do something that errors
        print("This will never be reached")
    ```"""

    def decorator(func: MaybeAwaitableFunc[P, T]):
        async def wrapper(*args: P.args, **kwargs: P.kwargs):
            try:
                return await discord.utils.maybe_coroutine(func, *args, **kwargs)
            except exc_types as e:
                return await maybe_coroutine(handler, e)

        return wrapper

    if func is None:
        return decorator

    return decorator(func)


class BanAppeal(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        self.config.register_user(banned_from=[])
        self.config.register_member(has_appealed=False)
        self.user_install_link = (
            f"https://discord.com/oauth2/authorize?client_id={self.bot.application_id}"
        )
        self.config.register_guild(
            channel=None,
            questions=[],
            managers=[],
            toggle=False,
            appeal_messages={
                "accepted": "Your appeal was accepted and you have been unbanned from {guild_name}",
                "rejected": "Your appeal was rejected and you are still banned from {guild_name}",
                "second_chance": "Your appeal was rejected in {guild_name} but you can appeal a second time.",
            },
            ban_message=(
                "You have been banned from {guild_name}. "
                "To appeal this ban, please "
                f"[install the bot to your account](<https://discord.com/developers/docs/resources/application#installation-context>) "
                "with the following link: <{user_install_link}> or by clicking the button below this embed.\n"
                "After installing, run the `/appeal` command and it will guide you through what to do."
            ),
        )
        AcceptRejectButton.conf = self.config
        self.bot.add_dynamic_items(AcceptRejectButton)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(AcceptRejectButton)

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        ModCog = self.bot.get_cog("Mod")
        if not ModCog:
            log.debug("Mod cog not found")
            return
        if ctx.command.qualified_name.lower() != "ban" or ctx.cog != ModCog:
            # log.debug("Not a ban command")
            return

        if not await ctx.command.can_run(ctx):
            log.debug("Command can't be run by the invoker")
            return

        if not await self.config.guild(ctx.guild).toggle():
            log.debug("Ban appeals are disabled")
            return

        from redbot.cogs.mod.kickban import _

        user: typing.Union[discord.User, discord.Member]

        if len(ctx.args) > 2:
            user = ctx.args[2]

        else:
            try:
                user = await commands.UserConverter().convert(ctx, ctx.current_argument)
            except commands.BadArgument:
                log.debug(f"{ctx.current_parameter} is not a valid user")
                return

        # if not user.mutual_guilds:
        #     log.debug(f"{user} is not in any mutual guilds")
        #     return
        # there is no point in checking this incase the user has already installed the bot.

        banmsg: str = await self.config.guild(ctx.guild).ban_message()
        dm_toggle = await ModCog.config.guild(ctx.guild).dm_on_kickban()
        view = discord.ui.View().add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.url,
                url=self.user_install_link,
                label="Install the bot",
            )
        )
        if dm_toggle and isinstance(user, discord.Member):

            def dm_check(msg: discord.Message):
                conditions = (
                    msg.author.id == self.bot.user.id
                    and msg.channel.type
                    and msg.channel.type == discord.ChannelType.private
                    and msg.embeds
                    and msg.embeds[0].title
                    == cf.bold(
                        _("You have been banned from {guild}.").format(guild=ctx.guild)
                    )
                )
                return conditions

            try:
                msg: discord.Message = await self.bot.wait_for(
                    "message", check=dm_check, timeout=30
                )
            except asyncio.TimeoutError:
                pass

            else:
                log.debug("Found a message sent to the banned user.")
                embed = msg.embeds[0]
                embed.description = banmsg.format(
                    guild_name=ctx.guild.name,
                    user_install_link=self.user_install_link,
                )
                try:
                    log.debug("Editing the message to include the install link")
                    return await msg.edit(embed=embed, view=view)

                except discord.HTTPException:
                    log.debug("Failed to edit the message")
                    pass

        if banmsg:
            try:
                log.debug("Sending the ban message to the user")
                await user.send(
                    embed=discord.Embed(
                        description=banmsg.format(
                            guild_name=ctx.guild.name,
                            user_install_link=self.user_install_link,
                        ),
                        color=await ctx.embed_colour(),
                    ),
                    view=view,
                )

            except discord.Forbidden:
                log.debug("Failed to send the ban message to the user")
                channel = self.bot.get_channel(
                    await self.config.guild(ctx.guild).channel()
                )
                if not channel:
                    log.debug("Channel not found")
                    await ctx.send("Unable to dm the appeal message to the user.")

                else:
                    log.debug("Channel found")
                    await channel.send(
                        f"Unable to dm the appeal message to {user.mention}."
                    )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not await self.config.guild(guild).toggle():
            return

        banned_from: list[str]
        async with self.config.user(user).banned_from() as banned_from:
            if guild.id not in banned_from:
                banned_from.append(guild.id)

        await self.config.member_from_ids(guild.id, user.id).has_appealed.set(False)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not await self.config.guild(guild).toggle():
            return

        banned_from: list[str]
        async with self.config.user(user).banned_from() as banned_from:
            try:
                banned_from.remove(guild.id)
            except ValueError:
                pass

        await self.config.member_from_ids(guild.id, user.id).has_appealed.set(False)

    @app_commands.command(name="appeal")
    @app_commands.checks.cooldown(1, 180)
    @app_commands.user_install()
    @app_commands.allowed_contexts(dms=True, guilds=False, private_channels=False)
    async def appeal(self, interaction: discord.Interaction):
        """
        Appeal a ban
        """
        ctx = await commands.Context.from_interaction(interaction)
        banned_from = await self.config.user(ctx.author).banned_from()
        guilds = [self.bot.get_guild(g) for g in banned_from]

        guilds = [
            g
            for g in set(
                itertools.chain(
                    guilds, map(self.bot.get_guild, await self.config.all_guilds())
                )
            )
            if g is not None
            and await self.config.guild(g).toggle()
            and not await self.config.member_from_ids(
                g.id, interaction.user.id
            ).has_appealed()
            and await catch(g.fetch_ban)(interaction.user)
        ]

        if not guilds:
            return await interaction.response.send_message(
                "There are no servers that you are banned from with ban appeals enabled and where you have not appealed yet"
            )

        view = ViewDisableOnTimeout(ctx=ctx, timeout=60, timeout_message="Timed out")
        view.add_item(BannedGuildsSelect(guilds))
        await interaction.response.send_message(
            "Select a server to appeal from", view=view
        )
        view.message = interaction.original_response()

    @commands.group(name="appealset", aliases=["aset"])
    @commands.admin()
    async def appealset(self, ctx: commands.Context):
        """
        Set up ban appeal settings
        """

    @appealset.command(name="toggle")
    async def appealset_toggle(self, ctx: commands.Context):
        """
        Toggle ban appeal settings
        """
        current = await self.config.guild(ctx.guild).toggle()
        if current == False:
            if (
                not await self.config.guild(ctx.guild).channel()
                or not await self.config.guild(ctx.guild).questions()
                and not await self.config.guild(ctx.guild).managers()
            ):
                return await ctx.send(
                    "The channel and questions must be set before enabling ban appeals."
                )
        await self.config.guild(ctx.guild).toggle.set(not current)
        await ctx.send(
            f"{await self.config.guild(ctx.guild).toggle() and 'Enabled' or 'Disabled'} ban appeal settings"
        )

    @appealset.command(name="channel")
    async def appealset_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """
        Set ban appeal channel

        This is the channel where all appeals will be sent.
        """
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Set ban appeal channel to {channel.mention}")

    @appealset.group(name="questions", aliases=["qs", "question", "q"])
    async def appealset_questions(self, ctx: commands.Context):
        """
        Set ban appeal questions
        """

    @appealset_questions.command(name="add")
    async def appealset_questions_add(self, ctx: commands.Context, *, question: str):
        """
        Add a question
        """
        async with self.config.guild(ctx.guild).questions() as questions:
            if len(questions) == 5:
                return await ctx.send("You can only have 5 questions")
            questions.append(question)
        await ctx.send(f"Added question: {question}")

    @appealset_questions.command(name="remove")
    async def appealset_questions_remove(
        self, ctx: commands.Context, index: commands.positive_int
    ):
        """
        Remove a question
        """
        if index < 1:
            return await ctx.send_help()
        questions: list[str]
        async with self.config.guild(ctx.guild).questions() as questions:
            try:
                q = questions.pop(index - 1)
            except IndexError:
                return await ctx.send("Invalid index")
        await ctx.send(
            f"Removed question `{q}`. Please check the list again before removing another question."
        )

    @appealset_questions.command(name="list")
    async def appealset_questions_list(self, ctx: commands.Context):
        """
        List questions
        """
        questions = await self.config.guild(ctx.guild).questions()
        if not questions:
            return await ctx.send("No questions set")
        await ctx.send("\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)))

    @appealset.group(name="managers", aliases=["manager", "m"])
    async def appealset_managers(self, ctx: commands.Context):
        """
        Set ban appeal managers
        """

    @appealset_managers.command(name="add")
    async def appealset_managers_add(
        self,
        ctx: commands.Context,
        *,
        manager: typing.Union[discord.Member, discord.Role],
    ):
        """
        Add a manager
        """
        async with self.config.guild(ctx.guild).managers() as managers:
            if manager.id not in managers:
                managers.append(manager.id)

            else:
                return await ctx.send("Manager already exists")

        await ctx.send(f"Added manager: {manager.mention}")

    @appealset_managers.command(name="remove")
    async def appealset_managers_remove(
        self, ctx: commands.Context, manager: typing.Union[discord.Member, discord.Role]
    ):
        """
        Remove a manager
        """
        async with self.config.guild(ctx.guild).managers() as managers:
            try:
                managers.remove(manager.id)
            except ValueError:
                return await ctx.send("Manager not found")
        await ctx.send(f"Removed manager: {manager.mention}")

    @appealset_managers.command(name="list")
    async def appealset_managers_list(self, ctx: commands.Context):
        """
        List managers
        """
        managers = await self.config.guild(ctx.guild).managers()
        if not managers:
            return await ctx.send("No managers set")
        await ctx.send(
            "\n".join(
                f"{i}. {ctx.guild.get_role(m) or ctx.guild.get_member(m)}"
                for i, m in enumerate(managers, 1)
            )
        )

    @appealset.command(name="response", aliases=["responses", "r"])
    async def appealset_response(
        self,
        ctx: commands.Context,
        response_type: typing.Literal["accepted", "rejected", "second_chance"],
        *,
        response: str,
    ):
        """
        Set the message sent to a user when a ban appeal is accepted or rejected

        User `{guild_name}` to be replaced with the server name
        """
        async with self.config.guild(ctx.guild).appeal_messages() as messages:
            messages[response_type.lower()].append(response)
        await ctx.send(
            f"Updated `{response_type.replace('_', ' ')}` response: {response}"
        )

    @appealset.command(name="banmessage", aliases=["bm"])
    async def appealset_banmessage(
        self, ctx: commands.Context, *, message: str = ""
    ):
        """
        Set the message sent to a user when they are banned

        Use `{guild_name}` to be replaced with the server name
        and `{user_install_link}` to be replaced with the bot install link
        """
        await self.config.guild(ctx.guild).ban_message.set(message)
        await ctx.send("Updated ban message" if message else "Cleared ban message")

    @appealset.command(name="showsettings", aliases=["ss"])
    async def appealset_showsettings(self, ctx: commands.Context):
        """
        Show ban appeal settings
        """
        toggle = await self.config.guild(ctx.guild).toggle()
        channel = self.bot.get_channel(await self.config.guild(ctx.guild).channel())
        questions = (
            "\n".join(
                f"{i}. `{q}`"
                for i, q in enumerate(await self.config.guild(ctx.guild).questions(), 1)
            )
            or "Not set"
        )
        managers = (
            "\n".join(
                f"{i}. {getattr(ctx.guild.get_role(m) or ctx.guild.get_member(m), 'mention', f'Not found ({m})')}"
                for i, m in enumerate(await self.config.guild(ctx.guild).managers(), 1)
            )
            or "- None set"
        )
        appeal_messages = "\n".join(
            f"- {k.replace('_', ' ').title()}:\n  - `{v}`"
            for k, v in (await self.config.guild(ctx.guild).appeal_messages()).items()
        )
        ban_message = await self.config.guild(ctx.guild).ban_message()
        await ctx.send(
            f"**Toggle**:{toggle}\n**Channel**: {channel.mention if channel else 'Not set'}\n**Questions**:\n{questions}\n**Managers**:\n{managers}\n**Appeal messages**:\n{appeal_messages}\n**Ban message**:\n{cf.box(ban_message)}"
        )

    @appealset.command(name="resetappeal", aliases=["resetappeals"])
    async def appealset_resetappeal(
        self,
        ctx: commands.Context,
        user: typing.Optional[typing.Union[discord.User, int]] = None,
    ):
        """
        Reset the appeal status of all users
        """
        await self.config.clear_all_members()
        await ctx.send("Reset all users' appeal status")
