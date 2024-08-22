import datetime
import typing

import discord
from discord.ui import Button, Select, View
from redbot.core import commands, Config
from redbot.vendored.discord.ext import menus
from redbot.core.utils.views import ConfirmView
from redbot.core.bot import Red
from redbot.core.modlog import create_case


__all__ = [
    "Paginator",
    "PaginatorButton",
    "CloseButton",
    "ForwardButton",
    "BackwardButton",
    "LastItemButton",
    "FirstItemButton",
    "PageButton",
    "PaginatorSelect",
    "PaginatorSourceSelect",
]


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


def enable_items(self: View):
    for i in self.children:
        i.disabled = False


async def interaction_check(ctx: commands.Context, interaction: discord.Interaction):
    if not ctx.author.id == interaction.user.id:
        await interaction.response.send_message(
            "You aren't allowed to interact with this bruh. Back Off!", ephemeral=True
        )
        return False

    return True


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(self, **kwargs):
        self.message: discord.Message = None
        self.ctx: commands.Context = kwargs.pop("ctx", None)
        self.timeout_message: str = kwargs.pop("timeout_message", None)
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)
            if self.timeout_message and self.ctx:
                await self.ctx.send(self.timeout_message)

        self.stop()


class PaginatorButton(Button["Paginator"]):
    def __init__(
        self, *, emoji=None, label=None, style=discord.ButtonStyle.green, disabled=False
    ):
        super().__init__(style=style, label=label, emoji=emoji, disabled=disabled)


class CloseButton(Button["Paginator"]):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red,
            label="Close",
            emoji="\N{CROSS MARK}",
        )

    async def callback(self, interaction: discord.Interaction):
        await (self.view.message or interaction.message).delete()
        self.view.stop()


class ForwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        max_pages = self.view.source.get_max_pages()
        if (
            self.view.current_page == (max_pages - 1)
            or self.view.current_page >= max_pages
        ):
            self.view.current_page = 0
        else:
            self.view.current_page += 1

        await self.view.edit_message(interaction)


class BackwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        max_pages = self.view.source.get_max_pages()
        if self.view.current_page == 0 or self.view.current_page >= max_pages:
            self.view.current_page = max_pages - 1
        else:
            self.view.current_page -= 1

        await self.view.edit_message(interaction)


class LastItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = self.view.source.get_max_pages() - 1

        await self.view.edit_message(interaction)


class FirstItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = 0

        await self.view.edit_message(interaction)


class PageButton(PaginatorButton):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, disabled=True)

    def _change_label(self):
        self.label = (
            f"Page {self.view.current_page+1}/{self.view.source.get_max_pages()}"
        )


class PaginatorSelect(Select["Paginator"]):
    @classmethod
    async def with_pages(cls, view: "Paginator", placeholder: str = "Select a page:"):
        pages: int
        pages: int = view.source.get_max_pages() or 0
        if getattr(view.source, "custom_indices", None):
            indices: list[dict[str, str]] = typing.cast(
                list, view.source.custom_indices
            )
        else:
            indices = [
                *map(
                    lambda x: {
                        "label": f"Page # {x}",
                        "description": f"Go to page {x}",
                    },
                    range(1, pages + 1),
                )
            ]

        if pages > 25:
            minus_diff = 0
            plus_diff = 25
            if 12 < view.current_page < pages - 25:
                minus_diff = view.current_page - 12
                plus_diff = view.current_page + 13
            elif view.current_page >= (pages - 25):
                minus_diff = pages - 25
                plus_diff = pages
            options = [
                discord.SelectOption(**indices[i], value=str(i))
                for i in range(minus_diff, plus_diff)
            ]
        else:
            options = [
                discord.SelectOption(**indices[i], value=str(i)) for i in range(pages)
            ]

        return cls(options=options, placeholder=placeholder, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = int(self.values[0])
        await self.view.edit_message(interaction)


class PaginatorSourceSelect(Select["Paginator"]):
    def __init__(
        self, options: dict[discord.SelectOption, menus.PageSource], placeholder: str
    ):
        self.sources = dict(map(lambda x: (x[0].value, x[1]), options.items()))
        _options = [*options.keys()]
        disabled = False
        if len(_options) == 1:
            _options[0].default = True
            disabled = True

        super().__init__(
            options=_options,
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        source = self.sources[self.values[0]]
        await self.view.change_source(source, False, self.view.ctx)
        await self.view.edit_message(interaction)


class Paginator(ViewDisableOnTimeout):
    def __init__(
        self,
        source: menus.PageSource,
        start_index: int = 0,
        timeout: int = 30,
        use_select: bool = False,
        extra_items: typing.List[discord.ui.Item] = None,
    ):
        super().__init__(timeout=timeout)

        self.ctx: commands.Context
        self._source = source
        self.use_select: bool = use_select
        self._start_from = start_index
        self.current_page: int = start_index
        self.extra_items: list[discord.ui.Item] = extra_items or []

    @property
    def source(self):
        return self._source

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    async def update_buttons(self, edit=False):
        self.clear_items()
        pages = self.source.get_max_pages() or 0
        buttons_to_add: typing.List[Button] = (
            [
                FirstItemButton(),
                BackwardButton(),
                PageButton(),
                ForwardButton(),
                LastItemButton(),
            ]
            if pages > 2
            else [BackwardButton(), PageButton(), ForwardButton()] if pages > 1 else []
        )
        if self.use_select and pages > 1:
            buttons_to_add.append(await PaginatorSelect.with_pages(self))

        for button in buttons_to_add:
            self.add_item(button)

        for item in self.extra_items:
            self.add_item(item)

        self.add_item(CloseButton())

        await self.update_items(edit)

    async def update_items(self, edit: bool = False):
        pages = (self.source.get_max_pages() or 1) - 1
        for i in self.children:
            if isinstance(i, PageButton):
                i._change_label()
                continue

            elif self.current_page == self._start_from and isinstance(
                i, FirstItemButton
            ):
                i.disabled = True
                continue

            elif self.current_page == pages and isinstance(i, LastItemButton):
                i.disabled = True
                continue

            elif (um := getattr(i, "update", None)) and callable(um) and edit:
                i.update()

            if i in self.extra_items:
                continue

            i.disabled = False

    async def edit_message(self, inter: discord.Interaction):
        page = await self.get_page(self.current_page)

        await self.update_buttons(True)
        await inter.response.edit_message(**page)
        self.message = inter.message

    async def change_source(
        self,
        source,
        start: bool = False,
        ctx: typing.Optional[commands.Context] = None,
        ephemeral: bool = True,
    ):
        """|coro|

        Changes the :class:`PageSource` to a different one at runtime.

        Once the change has been set, the menu is moved to the first
        page of the new source if it was started. This effectively
        changes the :attr:`current_page` to 0.

        Raises
        --------
        TypeError
            A :class:`PageSource` was not passed.
        """

        if not isinstance(source, menus.PageSource):
            raise TypeError(
                "Expected {0!r} not {1.__class__!r}.".format(menus.PageSource, source)
            )

        self._source = source
        self.current_page = self._start_from
        await source._prepare_once()
        if start:
            if ctx is None:
                raise RuntimeError("Cannot start without a context object.")
            await self.start(ctx, ephemeral=ephemeral)

        return self

    async def get_page(self, page_num: int) -> dict:
        await self.update_buttons()
        try:
            page = await self.source.get_page(page_num)
        except IndexError:
            self.current_page = 0
            page = await self.source.get_page(self.current_page)
        value = await self.source.format_page(self, page)
        ret = {}
        if isinstance(value, dict):
            if self.message and "file" in value:
                ret.update({"attachments": [value.pop("file")]})
            ret.update(value)
        elif isinstance(value, str):
            ret.update({"content": value, "embed": None})
        elif isinstance(value, discord.Embed):
            ret.update({"embed": value, "content": None})
        ret.update({"view": self})
        return ret

    async def start(self, ctx: commands.Context, ephemeral: bool = True):
        """
        Used to start the menu displaying the first page requested.

        Parameters
        ----------
            ctx: `commands.Context`
                The context to start the menu in.
        """
        await self.source._prepare_once()
        self.author = ctx.author
        self.ctx = ctx
        kwargs = await self.get_page(self.current_page)
        self.message: discord.Message = await getattr(self.message, "edit", ctx.send)(
            **kwargs, ephemeral=ephemeral
        )


class AcceptRejectButton(
    discord.ui.DynamicItem,
    template=r"BANAPPEAL_(?P<action>accept|reject)_(?P<user_id>\d{18,19})_(?P<guild_id>\d{18,19})",
):
    conf: Config

    def __init__(self, action: str, user: discord.User, guild: discord.Guild):
        self.action = action
        self.user = user
        self.guild = guild
        item = discord.ui.Button(
            label=f"{action.capitalize()}",
            emoji=action == "accept" and "✅" or "❌",
            custom_id=f"BANAPPEAL_{action}_{user.id}_{guild.id}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: typing.Match[str],
    ):
        return cls(
            match["action"],
            await interaction.client.get_or_fetch_user(int(match["user_id"])),
            (
                (interaction.guild and interaction.guild.id == int(match["guild_id"]))
                and interaction.guild
                or interaction.client.get_guild(int(match["guild_id"]))
            ),
        )

    async def interaction_check(self, interaction: discord.Interaction[Red]) -> bool:
        bot = interaction.client
        if await bot.is_admin(interaction.user) or await bot.is_owner(interaction.user):
            return True

        managers = await self.conf.guild(interaction.guild).managers()
        if interaction.user.id in managers or any(
            interaction.user.get_role(r) for r in managers
        ):
            return True

        await interaction.response.send_message(
            "You are not allowed to interact with this bruh. Back Off!",
            ephemeral=True,
        )
        return False

    async def callback(self, interaction: discord.Interaction[Red]) -> None:
        if "accept" in self.custom_id.lower():
            self.item.label = " User Appeal Accepted"
            self.item.style = discord.ButtonStyle.green
            self.item.disabled = True
            disable_items(self.view)
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send("Unbanning the user....", ephemeral=True)
            try:
                await interaction.guild.unban(self.user)

            except discord.NotFound:
                return await interaction.followup.send(
                    "The user is already unbanned in this server",
                    ephemeral=True,
                )

            await interaction.followup.send(
                f"User unbanned. DM'ing the user to inform them of the good news...",
                ephemeral=True,
            )
            await self.user.send(
                (
                    await self.conf.guild(interaction.guild).appeal_messages.accepted()
                ).format(guild_name=interaction.guild.name)
            )
            await interaction.followup.send("User has been informed", ephemeral=True)
            await self.conf.member_from_ids(
                interaction.guild.id, self.user.id
            ).has_appealed.set(False)
            await create_case(
                interaction.client,
                interaction.guild,
                datetime.datetime.now(datetime.timezone.utc),
                "unban",
                self.user,
                interaction.user,
                "Ban Appeal Accepted",
                channel=interaction.channel,
            )

        else:
            view = ConfirmView(interaction.user, disable_buttons=True)
            await interaction.response.send_message(
                f"Do you want to give {self.user.display_name} a second chance at appealing?",
                ephemeral=True,
                view=view,
            )
            view.message = await interaction.original_response()
            if await view.wait():
                await interaction.followup.send(
                    "You took too long to confirm your decision. Action Cancelled",
                    ephemeral=True,
                )
                return

            if view.result:
                self.item.disabled = True

                disable_items(self.view)
                await interaction.message.edit(view=self.view)
                await interaction.followup.send(
                    f"Informing the user that they have a second chance to appeal...",
                    ephemeral=True,
                )
                await self.user.send(
                    (
                        await self.conf.guild(
                            interaction.guild
                        ).appeal_messages.second_chance()
                    ).format(guild_name=interaction.guild.name)
                )
                await interaction.followup.send(
                    "User has been informed", ephemeral=True
                )
                await self.conf.member_from_ids(
                    interaction.guild.id, self.user.id
                ).has_appealed.set(False)
                return
            self.item.label = "User Appeal Rejected"
            self.item.style = discord.ButtonStyle.red
            self.item.disabled = True
            disable_items(self.view)
            await interaction.message.edit(view=self.view)

            await interaction.followup.send(
                f"User appeal rejected. DM'ing the user to inform them of the bad news...",
                ephemeral=True,
            )
            await self.user.send(
                (
                    await self.conf.guild(interaction.guild).appeal_messages.rejected()
                ).format(guild_name=interaction.guild.name)
            )
            await interaction.followup.send("User has been informed", ephemeral=True)


class BannedGuildsSelect(discord.ui.Select):
    def __init__(self, guilds: list[discord.Guild]):
        options = [
            discord.SelectOption(label=guild.name, value=str(guild.id))
            for guild in guilds
        ]
        super().__init__(placeholder="Select a guild", options=options)

    def remove_guild_from_options(self, guild_id: int):
        self.options = [
            option for option in self.options if int(option.value) != guild_id
        ]
        if not self.options:
            self.options.append(
                discord.SelectOption(
                    label="No servers available", value="0", default=True
                )
            )
            self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        guild_id = int(self.values[0])
        guild = interaction.client.get_guild(guild_id)
        if not guild:
            self.remove_guild_from_options(guild_id)
            await interaction.response.edit_message(view=self)
            return await interaction.followup.send(
                "Hmm it seems that server is not available anymore. Please select another one",
                ephemeral=True,
            )

        channel = guild.get_channel(
            await AcceptRejectButton.conf.guild(guild).channel()
        )
        if not channel:
            return await interaction.response.send_message_message(
                "The server does not have a ban appeal channel set. Please contact the admins directly",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            QuestionnaireModal(
                await AcceptRejectButton.conf.guild(guild).questions(),
                channel,
            )
        )
        self.disabled = True
        await interaction.message.edit(view=self.view)


class QuestionnaireModal(discord.ui.Modal):
    def __init__(self, questions: list[str], appeal_channel: discord.TextChannel):
        super().__init__(title="Questions for appealing ban", timeout=180)
        self.questions = questions
        self.appeal_channel = appeal_channel
        for ind, value in enumerate(self.questions, 1):
            setattr(
                self,
                f"question_{ind}",
                discord.ui.TextInput(
                    label=value, style=discord.TextStyle.long, placeholder="Answer here"
                ),
            )
            self.add_item(getattr(self, f"question_{ind}"))

    async def on_submit(self, interaction: discord.Interaction):
        answers = {}
        for ind, question in enumerate(self.questions, 1):
            tinput: discord.ui.TextInput = getattr(self, f"question_{ind}")
            answers[question] = tinput.value

        view = ConfirmView(interaction.user, disable_buttons=True)
        await interaction.response.send_message(
            (
                "Your answers are:\n"
                + "\n".join(
                    f"- **{question}**\n  - {answer}"
                    for question, answer in answers.items()
                )
                + "\n\nDo you want to submit this appeal?"
            ),
            ephemeral=True,
            view=view,
        )
        view.message = await interaction.original_response()
        if await view.wait():
            await interaction.followup.send(
                "You took too long to confirm your answers. Appeal cancelled",
                ephemeral=True,
            )
            return

        if view.result:
            await interaction.followup.send(
                "Your appeal is being submitted...", ephemeral=True
            )
            try:
                await self.appeal_channel.send(
                    f"**{interaction.user}** has submitted an appeal",
                    embed=discord.Embed(
                        title="Ban Appeal",
                        description="\n".join(
                            f"- **{question}**\n  - {answer}"
                            for question, answer in answers.items()
                        ),
                    ),
                    view=discord.ui.View(timeout=180)
                    .add_item(
                        AcceptRejectButton(
                            "accept", interaction.user, self.appeal_channel.guild
                        )
                    )
                    .add_item(
                        AcceptRejectButton(
                            "reject", interaction.user, self.appeal_channel.guild
                        )
                    ),
                )
                await AcceptRejectButton.conf.member_from_ids(
                    self.appeal_channel.guild.id, interaction.user.id
                ).has_appealed.set(True)

            except discord.Forbidden:
                await interaction.followup.send(
                    "I am unable to send your appeal to the admins. Please contact them directly",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                "Your appeal has been submitted. Please wait for the admins to review it. You will be dm'ed once a decision has been made",
                ephemeral=True,
            )

        else:
            await interaction.followup.send("Appeal cancelled", ephemeral=True)
            return

        self.stop()
