"""
MIT License

Copyright (c) 2020-2023 phenom4n4n
Copyright (c) 2023-present i-am-zaidali

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import contextlib
import logging
import re
import types
import typing
from collections import Counter
from copy import copy

import discord
from discord.app_commands.transformers import Choice, CommandParameter
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate
from tabulate import tabulate

from ..abc import MixinMeta
from ..converters import (
    GlobalTagConverter,
    GuildTagConverter,
    PastebinConverter,
    TagConverter,
    TagName,
    TagScriptConverter,
)
from ..objects import (
    ApplicationCommand,
    SlashTag,
    pk_refined_mapping,
)
from ..utils import ARGUMENT_NAME_DESCRIPTION, chunks, dev_check, menu
from ..views import ConfirmationView, OptionPickerView

TAG_RE = re.compile(r"(?i)(\[p\])?\b(slash\s?)?tag'?s?\b")

CHOICE_RE = re.compile(r".{1,100}:.{1,100}")

CHOICE_LIMIT = 25

log = logging.getLogger("red.phenom4n4n.slashtags.commands")


def _sub(match: re.Match) -> str:
    if match.group(1):
        return "[p]slashtag global"

    repl = "global "
    name = match.group(0)
    repl += name
    if name.istitle():
        repl = repl.title()
    return repl


def copy_doc(original: typing.Union[commands.Command, types.FunctionType]):
    def decorator(overriden: typing.Union[commands.Command, types.FunctionType]):
        doc = (
            original.help
            if isinstance(original, commands.Command)
            else original.__doc__
        )
        doc = TAG_RE.sub(_sub, doc)

        if isinstance(overriden, commands.Command):
            overriden._help_override = doc
        else:
            overriden.__doc__ = doc
        return overriden

    return decorator


class Commands(MixinMeta):
    @commands.guild_only()
    @commands.group(aliases=["st"])
    async def slashtag(self, ctx: commands.Context):
        """
        Slash Tag management with TagScript.

        These commands use TagScriptEngine.
        [This site](https://phen-cogs.readthedocs.io/en/latest/index.html) has documentation on how to use TagScript blocks.
        """

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag.command("add", aliases=["create", "+"])
    async def slashtag_add(
        self,
        ctx: commands.Context,
        tag_name: TagName(check_global=False),
        *,
        tagscript: TagScriptConverter,
    ):
        """
        Add a slash tag with TagScript.

        [Slash tag usage guide](https://phen-cogs.readthedocs.io/en/latest/slashtags/slashtags.html)
        """
        await self.create_slash_tag(ctx, tag_name, tagscript, is_global=False)

    async def create_slash_tag(
        self,
        ctx: commands.Context,
        tag_name: str,
        tagscript: str,
        *,
        is_global: bool = False,
        command_type: discord.AppCommandType = discord.AppCommandType.chat_input,
    ):
        options: typing.List[CommandParameter] = []
        guild_id = None if is_global else ctx.guild.id
        if command_type == discord.AppCommandType.chat_input:
            try:
                description = await self.send_and_query_response(
                    ctx,
                    "What should the tag description to be? (maximum 100 characters)",
                    pred=MessagePredicate.length_less(101, ctx),
                )
            except asyncio.TimeoutError:
                return await ctx.send("Tag addition timed out.")
        else:
            description = ""

        if command_type == discord.AppCommandType.chat_input:
            result = await ConfirmationView.confirm(
                ctx,
                "Would you like to add arguments to this tag?",
                cancel_message=None,
            )
            if result is True:
                await self.get_options(ctx, options)

        command = ApplicationCommand(
            self,
            id=None,
            application_id=self.application_id,
            name=tag_name,
            description=description,
            guild_id=guild_id,
            options=options,
            type=command_type,
        )
        try:
            await command.register()
        except discord.Forbidden as error:
            log.error(
                "Failed to create command {command!r} on guild {ctx.guild!r}",
                exc_info=error,
            )
            text = (
                "Looks like I don't have permission to add Slash Commands here. Reinvite me "
                "with this invite link and try again: <https://discordapp.com/oauth2/authorize"
                f"?client_id={self.bot.user.id}&scope=bot%20applications.commands>"
            )
            return await ctx.send(text)
        except Exception:
            log.error("Failed to create command {command!r} on guild {ctx.guild!r}")
            # exc info unneeded since error handler should print it, however info on the command options is needed
            raise

        tag = SlashTag(
            self,
            tagscript,
            guild_id=guild_id,
            author_id=ctx.author.id,
            command=command,
        )
        try:
            resp = await tag.initialize()
        except Exception:
            await tag.delete(True)
            log.exception("Failed to initialize tag {tag!r} on guild {ctx.guild!r}")
            raise
        await ctx.send(resp)

    async def get_options(
        self, ctx: commands.Context, options: typing.List[CommandParameter]
    ) -> typing.List[CommandParameter]:
        added_required = False
        for i in range(1, 11):
            try:
                option = await self.get_option(ctx, added_required=added_required)
                if not option.required:
                    added_required = True
            except asyncio.TimeoutError:
                await ctx.send("Adding this argument timed out.", delete_after=15)
                break

            options.append(option)
            if i == 10:
                break

            result = await ConfirmationView.confirm(
                ctx,
                "Would you like to add another argument?",
                cancel_message=None,
            )
            if not result:
                break
        return options

    async def send_and_query_response(
        self,
        ctx: commands.Context,
        query: str,
        pred: MessagePredicate = None,
        *,
        timeout: int = 60,
    ) -> str:
        if pred is None:
            pred = MessagePredicate.same_context(ctx)
        ask = await ctx.send(query)
        try:
            message = await self.bot.wait_for("message", check=pred, timeout=timeout)
        except asyncio.TimeoutError:
            await self.delete_quietly(ask)
            raise
        await self.delete_quietly(ask)
        await self.delete_quietly(message)
        return message.content

    async def get_choices(
        self, ctx: commands.Context, option_type: discord.AppCommandOptionType
    ) -> typing.List[Choice]:
        converters = {
            discord.AppCommandOptionType.string: str,
            discord.AppCommandOptionType.integer: int,
            discord.AppCommandOptionType.number: float,
        }
        query = (
            "Send the list of choice names and values you would like to add as choices to "
            "the tag. Choice names and values should be seperated by `:`, and each choice "
            "should be seperated by `|`. Examples:\n**String option type**: `dog:Doggo|cat:Catto`\n**Integer option type**: `One:1|Two:2|Three:3`\n**Number option type**: `PI:3.14|E:2.71828`"
        )
        response = await self.send_and_query_response(ctx, query)
        choices = []
        for choice_text in response.split("|"):
            if ":" not in choice_text:
                await ctx.send(
                    f"Failed to parse `{choice_text}` to a choice as its name and value "
                    "weren't seperated by a `:`.",
                    delete_after=15,
                )
                continue
            if not CHOICE_RE.match(choice_text):
                await ctx.send(
                    f"Failed to parse `{choice_text}` to a choice as "
                    "its name or value exceeded the 100 character limit.",
                    delete_after=15,
                )
                continue
            name, value = choice_text.split(":", 1)
            try:
                value = converters[option_type](value)

            except ValueError:
                await ctx.send(
                    f"Failed to parse `{choice_text}` to a choice as "
                    f"its value couldn't be converted to a {option_type.name}.\n"
                    f"If your option type is integer, make sure the value is a whole number. and simialrly for float, the value must be a decimal number. "
                    f"For string option type, anything is accepted.",
                    delete_after=15,
                )
                continue
            choice = Choice(name=name, value=value)
            choices.append(choice)
            if len(choices) >= CHOICE_LIMIT:
                await ctx.send(f"Reached max choices ({CHOICE_LIMIT}).")
                break
        return choices

    async def get_option(
        self, ctx: commands.Context, *, added_required: bool = False
    ) -> CommandParameter:
        name_desc = [
            "What should the argument name be and description be?",
            "The argument name and description should be split by a `:`.",
            "Example: `member:A member of this server.`\n",
            "*Slash argument names may not exceed 32 characters and can only contain characters "
            "that are alphanumeric or '_' or '-'.",
            "The argument description must be less than or equal to 100 characters.*",
        ]
        name_pred = MessagePredicate.regex(ARGUMENT_NAME_DESCRIPTION, ctx)
        await self.send_and_query_response(ctx, "\n".join(name_desc), name_pred)
        match = typing.cast("re.Match[str]", name_pred.result)
        name, description = match.group(1).lower(), match.group(2)
        option_type = await OptionPickerView.pick(
            ctx, "What should the argument type be?"
        )
        if option_type is None:
            raise asyncio.TimeoutError
        if not added_required:
            text = (
                "Is this argument required?\n*Keep in mind that if you choose to make this "
                "argument optional, all following arguments must also be optional.*"
            )
            required = await ConfirmationView.confirm(ctx, text, cancel_message=None)
        else:
            await ctx.send(
                "This argument was automatically made optional as the previous one was optional.",
                delete_after=15,
            )
            required = False

        choices = []
        if option_type in [
            discord.AppCommandOptionType.string,
            discord.AppCommandOptionType.integer,
            discord.AppCommandOptionType.number,
        ]:
            text = "Would you like to add pre-defined choices to this argument?"
            if await ConfirmationView.confirm(ctx, text, cancel_message=None):
                choices = await self.get_choices(ctx, option_type)

        return CommandParameter(
            pk_refined_mapping.get(name.lower(), name.lower()).replace(" ", "_"),
            _rename=name,
            description=description,
            required=required,
            type=option_type,
            choices=choices,
        )

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag.command("message")
    async def slashtag_message(
        self,
        ctx: commands.Context,
        tag_name: TagName(check_global=False, check_regex=False),
        *,
        tagscript: TagScriptConverter,
    ):
        """
        Add a message command tag with TagScript.

        [Slash tag usage guide](https://phen-cogs.readthedocs.io/en/latest/slashtags/slashtags.html)
        """
        await self.create_slash_tag(
            ctx,
            tag_name,
            tagscript,
            is_global=False,
            command_type=discord.AppCommandType.message,
        )

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag.command("user")
    async def slashtag_user(
        self,
        ctx: commands.Context,
        tag_name: TagName(check_global=False, check_regex=False),
        *,
        tagscript: TagScriptConverter,
    ):
        """
        Add a user command tag with TagScript.

        [Slash tag usage guide](https://phen-cogs.readthedocs.io/en/latest/slashtags/slashtags.html)
        """
        await self.create_slash_tag(
            ctx,
            tag_name,
            tagscript,
            is_global=False,
            command_type=discord.AppCommandType.user,
        )

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag.command("pastebin", aliases=["++"])
    async def slashtag_pastebin(
        self,
        ctx: commands.Context,
        tag_name: TagName(check_global=False),
        *,
        link: PastebinConverter,
    ):
        """
        Add a slash tag with a Pastebin link.
        """
        await self.create_slash_tag(ctx, tag_name, link, is_global=False)

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag.group("edit", aliases=["e"], invoke_without_command=True)
    async def slashtag_edit(
        self,
        ctx: commands.Context,
        tag: GuildTagConverter,
        *,
        tagscript: TagScriptConverter,
    ):
        """Edit a slash tag."""
        await ctx.send(await tag.edit_tagscript(tagscript))

    @slashtag_edit.command("tagscript")
    async def slashtag_edit_tagscript(
        self,
        ctx: commands.Context,
        tag: GuildTagConverter,
        *,
        tagscript: TagScriptConverter,
    ):
        """Edit a slash tag's TagScript."""
        await self.slashtag_edit(ctx, tag, tagscript=tagscript)

    @slashtag_edit.command("name")
    async def slashtag_edit_name(
        self,
        ctx: commands.Context,
        tag: GuildTagConverter,
        *,
        name: TagName(check_global=False),
    ):
        """Edit a slash tag's name."""
        await ctx.send(await tag.edit_name(name))

    @slashtag_edit.command("description")
    async def slashtag_edit_description(
        self, ctx: commands.Context, tag: GuildTagConverter, *, description: str
    ):
        """Edit a slash tag's description."""
        await ctx.send(await tag.edit_description(description))

    @slashtag_edit.command("arguments", aliases=["options"])
    async def slashtag_edit_arguments(
        self, ctx: commands.Context, tag: GuildTagConverter
    ):
        """
        Edit a slash tag's arguments.

        See [this documentation page](https://phen-cogs.readthedocs.io/en/latest/slashtags/slash_arguments.html) for more information on slash tag arguments.
        """
        await tag.edit_options(ctx)

    @slashtag_edit.command("argument", aliases=["option"])
    async def slashtag_edit_argument(
        self, ctx: commands.Context, tag: GuildTagConverter, argument: str
    ):
        """Edit a single slash tag's argument by name."""
        await tag.edit_single_option(ctx, argument)

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag.command("remove", aliases=["delete", "-"])
    async def slashtag_remove(self, ctx: commands.Context, *, tag: GuildTagConverter):
        """Delete a slash tag."""
        await ctx.send(await tag.delete())

    @slashtag.command("info")
    async def slashtag_info(self, ctx: commands.Context, *, tag: TagConverter):
        """Get info about a slash tag that is stored on this server."""
        await tag.send_info(ctx)

    @slashtag.command("raw")
    async def slashtag_raw(self, ctx: commands.Context, *, tag: GuildTagConverter):
        """Get a slash tag's raw content."""
        await tag.send_raw_tagscript(ctx)

    @classmethod
    def format_tagscript(cls, tag: SlashTag, limit: int = 60) -> str:
        backslash = "\\"  # due to escape sequences not being allowed in py<3.12
        title = f"`{backslash if tag.type is discord.AppCommandType.chat_input else f'[{tag.type.name.lower()}]'}{tag.name}` - "
        limit -= len(title)
        tagscript = tag.tagscript
        if len(tagscript) > limit - 3:
            tagscript = tagscript[:limit] + "..."
        tagscript = tagscript.replace("\n", " ")
        return f"{title}{discord.utils.escape_markdown(tagscript)}"

    async def view_slash_tags(
        self,
        ctx: commands.Context,
        tags: typing.Dict[int, SlashTag],
        *,
        is_global: bool,
    ):
        description = [
            self.format_tagscript(tag)
            for tag in sorted(tags.values(), key=lambda t: t.name)
        ]
        description = "\n".join(description)

        e = discord.Embed(color=await ctx.embed_color())
        if is_global:
            slash_tags = "global slash tags"
            e.set_author(name="Global Slash Tags", icon_url=ctx.me.display_avatar.url)
        else:
            slash_tags = "slash tags"
            e.set_author(
                name="Stored Slash Tags", icon_url=getattr(ctx.guild, "icon_url", None)
            )

        embeds = []
        pages = list(pagify(description))
        for index, page in enumerate(pages, 1):
            embed = e.copy()
            embed.description = page
            embed.set_footer(text=f"{index}/{len(pages)} | {len(tags)} {slash_tags}")
            embeds.append(embed)
        await menu(ctx, embeds)

    @slashtag.command("list")
    async def slashtag_list(self, ctx: commands.Context):
        """View stored slash tags."""
        tags = self.guild_tag_cache[ctx.guild.id]
        if not tags:
            return await ctx.send("There are no slash tags on this server.")
        await self.view_slash_tags(ctx, tags, is_global=False)

    async def show_slash_tag_usage(
        self, ctx: commands.Context, guild: discord.Guild = None
    ):
        tags = self.guild_tag_cache[guild.id] if guild else self.global_tag_cache
        if not tags:
            message = (
                "This server has no slash tags."
                if guild
                else "There are no global slash tags."
            )
            return await ctx.send(message)
        counter = Counter({tag.name: tag.uses for tag in tags.copy().values()})
        e = discord.Embed(title="Slash Tag Stats", color=await ctx.embed_color())
        embeds = []
        for usage_data in chunks(counter.most_common(), 10):
            usage_chart = box(tabulate(usage_data, headers=("Tag", "Uses")), "prolog")
            embed = e.copy()
            embed.description = usage_chart
            embeds.append(embed)
        await menu(ctx, embeds)

    @slashtag.command("usage", aliases=["stats"])
    async def slashtag_usage(self, ctx: commands.Context):
        """
        See slash tag usage stats.

        **Example:**
        `[p]slashtag usage`
        """
        await self.show_slash_tag_usage(ctx, ctx.guild)

    @commands.is_owner()
    @slashtag.command("restore", hidden=True)
    async def slashtag_restore(
        self,
        ctx: commands.Context,
        tag: SlashTag = commands.param(
            converter=typing.Optional[TagConverter], default=None
        ),
    ):
        """Restore all slash tags from the database."""
        if tag:
            await ctx.send(await tag.restore())

        else:
            await self.restore_tags(ctx, ctx.guild)

    @commands.is_owner()
    @slashtag.command("clear", hidden=True)
    async def slashtag_clear(self, ctx: commands.Context):
        """Clear all slash tags for this server."""
        result = await ConfirmationView.confirm(
            ctx,
            "Are you sure you want to delete all slash tags on this server?",
            cancel_message="Ok, not deleting slash tags.",
        )
        if not result:
            return
        guild: discord.Guild = ctx.guild
        await self.http.put_guild_slash_commands(guild.id, [])
        for tag in copy(self.guild_tag_cache[guild.id]).values():
            tag.remove_from_cache()
        self.guild_tag_cache[guild.id].clear()
        await self.config.guild(guild).tags.clear()
        await ctx.send("Slash tags deleted.")

    @commands.is_owner()
    @slashtag.group("global")
    @copy_doc(slashtag)
    async def slashtag_global(self, ctx: commands.Context):
        pass

    @slashtag_global.command("add")
    @copy_doc(slashtag_add)
    async def slashtag_global_add(
        self,
        ctx: commands.Context,
        tag_name: TagName(global_priority=True),
        *,
        tagscript: TagScriptConverter,
    ):
        await self.create_slash_tag(ctx, tag_name, tagscript, is_global=True)

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag_global.command("message")
    @copy_doc(slashtag_message)
    async def slashtag_global_message(
        self,
        ctx: commands.Context,
        tag_name: TagName(global_priority=True, check_regex=False),
        *,
        tagscript: TagScriptConverter,
    ):
        await self.create_slash_tag(
            ctx,
            tag_name,
            tagscript,
            is_global=True,
            command_type=discord.AppCommandType.message,
        )

    @commands.mod_or_permissions(manage_guild=True)
    @slashtag_global.command("user")
    @copy_doc(slashtag_user)
    async def slashtag_global_user(
        self,
        ctx: commands.Context,
        tag_name: TagName(global_priority=True, check_regex=False),
        *,
        tagscript: TagScriptConverter,
    ):
        await self.create_slash_tag(
            ctx,
            tag_name,
            tagscript,
            is_global=True,
            command_type=discord.AppCommandType.user,
        )

    @slashtag_global.command("pastebin", aliases=["++"])
    @copy_doc(slashtag_pastebin)
    async def slashtag_global_pastebin(
        self,
        ctx: commands.Context,
        tag_name: TagName(check_global=False),
        *,
        link: PastebinConverter,
    ):
        await self.create_slash_tag(ctx, tag_name, link, is_global=True)

    @slashtag_global.group("edit", aliases=["e"], invoke_without_command=True)
    @copy_doc(slashtag_edit)
    async def slashtag_global_edit(
        self,
        ctx: commands.Context,
        tag: GlobalTagConverter,
        *,
        tagscript: TagScriptConverter,
    ):
        await ctx.send(await tag.edit_tagscript(tagscript))

    @slashtag_global_edit.command("tagscript")
    @copy_doc(slashtag_edit_tagscript)
    async def slashtag_global_edit_tagscript(
        self,
        ctx: commands.Context,
        tag: GlobalTagConverter,
        *,
        tagscript: TagScriptConverter,
    ):
        await self.slashtag_global_edit(ctx, tag, tagscript=tagscript)

    @slashtag_global_edit.command("name")
    @copy_doc(slashtag_edit_name)
    async def slashtag_global_edit_name(
        self,
        ctx: commands.Context,
        tag: GlobalTagConverter,
        *,
        name: TagName(global_priority=True),
    ):
        await ctx.send(await tag.edit_name(name))

    @slashtag_global_edit.command("description")
    @copy_doc(slashtag_edit_description)
    async def slashtag_global_edit_description(
        self, ctx: commands.Context, tag: GlobalTagConverter, *, description: str
    ):
        await ctx.send(await tag.edit_description(description))

    @slashtag_global_edit.command("arguments", aliases=["options"])
    @copy_doc(slashtag_edit_arguments)
    async def slashtag_global_edit_arguments(
        self, ctx: commands.Context, tag: GlobalTagConverter
    ):
        await tag.edit_options(ctx)

    @slashtag_global_edit.command("argument", aliases=["option"])
    @copy_doc(slashtag_edit_argument)
    async def slashtag_global_edit_argument(
        self, ctx: commands.Context, tag: GlobalTagConverter, argument: str
    ):
        await tag.edit_single_option(ctx, argument)

    @slashtag_global.command("remove", aliases=["delete", "-"])
    @copy_doc(slashtag_remove)
    async def slashtag_global_remove(
        self, ctx: commands.Context, *, tag: GlobalTagConverter
    ):
        await ctx.send(await tag.delete())

    @slashtag_global.command("info")
    @copy_doc(slashtag_info)
    async def slashtag_global_info(
        self, ctx: commands.Context, *, tag: GlobalTagConverter
    ):
        await tag.send_info(ctx)

    @slashtag_global.command("raw")
    @copy_doc(slashtag_raw)
    async def slashtag_global_raw(
        self, ctx: commands.Context, *, tag: GlobalTagConverter
    ):
        await tag.send_raw_tagscript(ctx)

    @slashtag_global.command("list")
    @copy_doc(slashtag_list)
    async def slashtag_global_list(self, ctx: commands.Context):
        tags = self.global_tag_cache
        if not tags:
            return await ctx.send("There are no global slash tags.")
        await self.view_slash_tags(ctx, tags, is_global=True)

    @slashtag_global.command("usage", aliases=["stats"])
    @copy_doc(slashtag_usage)
    async def slashtag_global_usage(self, ctx: commands.Context):
        await self.show_slash_tag_usage(ctx)

    @slashtag_global.command("restore", hidden=True)
    @copy_doc(slashtag_restore)
    async def slashtag_global_restore(
        self,
        ctx: commands.Context,
        tag: SlashTag = commands.param(converter=GlobalTagConverter, default=None),
    ):
        """Restore all slash tags from the database."""
        if tag:
            await tag.restore()

        else:
            await self.restore_tags(ctx)

    @commands.is_owner()
    @commands.group(aliases=["slashset"])
    async def slashtagset(self, ctx: commands.Context):
        """Manage SlashTags settings."""

    @slashtagset.command("settings")
    async def slashtagset_settings(self, ctx: commands.Context):
        """View SlashTags settings."""
        eval_command = f"✅ (**{self.eval_command}**)" if self.eval_command else "❎"
        testing_enabled = "✅" if self.testing_enabled else "❎"
        description = [
            f"Application ID: **{self.application_id}**",
            f"Eval command: {eval_command}",
            f"Test cog loaded: {testing_enabled}",
        ]
        embed = discord.Embed(
            color=0xC9C9C9,
            title="SlashTags Settings",
            description="\n".join(description),
        )
        await ctx.send(embed=embed)

    @slashtagset.command("appid")
    async def slashtagset_appid(self, ctx: commands.Context, id: int = None):
        """
        Manually set the application ID for [botname] slash commands if it differs from the bot user ID.

        This only applies to legacy bots. If you don't know what this means, you don't need to worry about it.
        """
        app_id = id or self.bot.user.id
        await self.config.application_id.set(app_id)
        self.application_id = app_id
        await ctx.send(f"Application ID set to `{id}`.")

    @commands.check(dev_check)
    @slashtagset.command("addeval")
    async def slashtagset_addeval(self, ctx: commands.Context):
        """Add a slash eval command for debugging."""
        if self.eval_command:
            return await ctx.send("An eval command is already registered.")
        slasheval = ApplicationCommand(
            self,
            name="eval",
            description="SlashTags debugging eval command. Only bot owners can use this.",
            options=[
                CommandParameter(
                    name="body", description="Code body to evaluate.", required=True
                )
            ],
        )
        await slasheval.register()
        await self.config.eval_command.set(slasheval.id)
        self.eval_command = slasheval.id
        await ctx.send("`/eval` has been registered.")

    @commands.check(dev_check)
    @slashtagset.command("rmeval")
    async def slashtagset_rmeval(self, ctx: commands.Context):
        """Remove the slash eval command."""
        if not self.eval_command:
            return await ctx.send("The eval command hasn't been registered.")
        with contextlib.suppress(discord.HTTPException):
            await self.http.remove_slash_command(self.eval_command)
        await self.config.eval_command.clear()
        self.eval_command = None
        await ctx.send("`/eval` has been deleted.")

    @slashtagset.command("testing")
    async def slashtagset_testing(
        self, ctx: commands.Context, true_or_false: bool = None
    ):
        """
        Load or unload the SlashTag interaction development test cog.
        """
        target_state = (
            true_or_false
            if true_or_false is not None
            else not await self.config.testing_enabled()
        )
        if target_state is self.testing_enabled:
            loaded = "loaded" if target_state else "unloaded"
            return await ctx.send(
                f"The SlashTag interaction testing cog is already {loaded}."
            )

        await self.config.testing_enabled.set(target_state)
        if target_state:
            loaded = "Loaded"
            self.add_test_cog()
        else:
            loaded = "Unloaded"
            self.remove_test_cog()
        await ctx.send(f"{loaded} the SlashTag interaction testing cog.")
