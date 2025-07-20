import typing

import discord
from discord.ui import Button, Select
from redbot.core import commands
from redbot.core.bot import Red
from redbot.vendored.discord.ext import menus

from . import ViewDisableOnTimeout, interaction_check

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
        if self.view.current_page == (self.view.source.get_max_pages() - 1):
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
        if self.view.current_page == 0:
            self.view.current_page = self.view.source.get_max_pages() - 1
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
            f"Page {self.view.current_page + 1}/{self.view.source.get_max_pages()}"
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
                *(
                    {"label": f"Page # {x}", "description": f"Go to page {x}"}
                    for x in range(1, pages + 1)
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

        self.ctx: typing.Union[commands.Context, discord.Interaction]
        self._source = source
        self.use_select: bool = use_select
        self._start_from = start_index
        self.current_page: int = start_index
        self.extra_items: list[discord.ui.Item] = extra_items or []

    @property
    def source(self):
        return self._source

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.author, interaction)

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
            else [BackwardButton(), PageButton(), ForwardButton()]
            if pages > 1
            else []
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
        try:
            page = await self.source.get_page(page_num)
        except IndexError:
            self.current_page = 0
            page = await self.source.get_page(self.current_page)
        await self.update_buttons()
        value = await self.source.format_page(self, page)
        ret = {"view": self}
        if isinstance(value, dict):
            ret.update(value)
        elif isinstance(value, str):
            ret.update({"content": value, "embed": None})
        elif isinstance(value, discord.Embed):
            ret.update({"embed": value, "content": None})
        return ret

    async def start(
        self,
        ctx: typing.Optional[commands.Context] = None,
        interaction: typing.Optional[discord.Interaction[Red]] = None,
        ephemeral: bool = True,
    ):
        """
        Used to start the menu displaying the first page requested.

        Parameters
        ----------
            ctx: `commands.Context`
                The context to start the menu in.
        """
        if not ctx and not interaction:
            raise RuntimeError("Cannot start without a context or interaction object.")
        await self.source._prepare_once()
        self.author = ctx.author if ctx else interaction.user
        self.ctx = ctx or interaction
        kwargs = await self.get_page(self.current_page)
        if self.message:
            self.message = await self.message.edit(**kwargs)
        elif ctx:
            self.message = await ctx.send(**kwargs, ephemeral=ephemeral)
        elif interaction:
            if interaction.is_expired():
                self.message = await interaction.channel.send(**kwargs)

            elif interaction.response.is_done():
                self.message = await interaction.followup.send(
                    **kwargs, ephemeral=ephemeral, wait=True
                )
            else:
                await interaction.response.send_message(**kwargs, ephemeral=ephemeral)
                self.message = await interaction.original_response()

        return self.message
