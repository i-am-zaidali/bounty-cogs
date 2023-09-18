import json
import math
from logging import getLogger
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import aiohttp
import discord
from discord.interactions import Interaction
from discord.ui import Button, Modal, Select, TextInput, View, button, select
from redbot.core import commands
from redbot.core.utils.views import SimpleMenu
from redbot.vendored.discord.ext import menus

log = getLogger("red.bounty.gamebanana.views")

if TYPE_CHECKING:
    from .main import RecordDict

base_url = "https://gamebanana.com/apiv11/"

humanize_bool = lambda b: "Yes" if b else "No"


class PageSource(menus.PageSource):
    def __init__(self, session: aiohttp.ClientSession, query: str):
        self.session = session
        self.query = query
        self._should_paginate: bool = False
        self._max_pages: int = 0
        self._requested_pages: dict[int, Tuple[List["RecordDict"], int, int]] = {}

    async def prepare(self):
        params = {
            "_nPage": 1,
            "_sOrder": "best_match",
            "_sModelName": "Mod",
            "_idGameRow": 16522,
            "_sSearchString": self.query,
            "_csvFields": "name",
        }
        async with self.session.get(base_url + "Util/Search/Results", params=params) as resp:
            try:
                data = await resp.json()
            except aiohttp.ContentTypeError:
                data = json.loads(await resp.text())
            except aiohttp.ClientError as e:
                return None

            self._requested_pages[1] = (data["_aRecords"], data["_aMetadata"]["_nRecordCount"], 15)

            self._max_pages = math.ceil(
                data["_aMetadata"]["_nRecordCount"] / data["_aMetadata"]["_nPerpage"]
            )
            self._should_paginate = self._max_pages > 1

    async def get_page(self, page_number: int) -> Tuple[List["RecordDict"], int, int]:
        if page_number in self._requested_pages:
            return self._requested_pages[page_number]
        params = {
            "_nPage": page_number,
            "_sOrder": "best_match",
            "_sModelName": "Mod",
            "_idGameRow": 16522,
            "_sSearchString": self.query,
            "_csvFields": "name",
        }
        async with self.session.get(base_url + "Util/Search/Results", params=params) as resp:
            try:
                data = await resp.json()
            except aiohttp.ContentTypeError:
                data = json.loads(await resp.text())
            except aiohttp.ClientError as e:
                return e
            try:
                print(data["_aMetadata"]["_bIsComplete"])
            except Exception:
                print(data)
            return self._requested_pages.setdefault(
                page_number,
                (
                    data["_aRecords"],
                    data["_aMetadata"]["_nRecordCount"],
                    data["_aMetadata"]["_nPerpage"],
                ),
            )

    async def format_page(
        self, menu: SimpleMenu, entries: Union[Tuple[List["RecordDict"], int, int], Exception]
    ):
        if isinstance(entries, Exception):
            log.exception("Error fetching search results:", exc_info=entries)
            return discord.Embed(title="Error (check logs)", description=str(entries))
        records, record_count, per_page = entries
        embed = discord.Embed(
            title=f"Search results for {self.query}",
            description=f"{record_count} results found.",
            color=await menu.ctx.embed_color(),
        )
        for record in records:
            field_name = f"{record['_sName']}  by {record['_aSubmitter']['_sName']}"
            field_value = (
                f"[CLICK HERE TO VIEW]({record['_sProfileUrl']})\n\n"
                + (f"*Version:* {record['_sVersion']}\n" if record.get("_sVersion") else "")
                + f"*Game:* [{record['_aGame']['_sName']}]({record['_aGame']['_sProfileUrl']})\n"
                + f"*Like count:* {record.get('_nLikeCount', 0):,}\n"
                + f"*View count:* {record['_nViewCount']:,}\n"
                + f"*Date added:* <t:{record['_tsDateAdded']}:F> (<t:{record['_tsDateAdded']}:R>)\n"
                + f"*Date modified:* <t:{record['_tsDateModified']}:F> (<t:{record['_tsDateModified']}:R>)\n\u200b"
            )
            embed.add_field(name=field_name, value=field_value, inline=False)

        max_pages = math.ceil(record_count / per_page)
        try:
            embed.set_thumbnail(url=records[0]["_aGame"]["_sIconUrl"])
        except Exception:
            pass
        if max_pages != 0:
            embed.set_footer(text=f"Page {menu.current_page}/{max_pages}")
        else:
            embed.add_field(name="No results found", value="Try a different query")
        return embed

    async def is_paginating(self):
        return self._should_paginate

    async def get_max_pages(self):
        return self._max_pages


class QueryModal(Modal):
    query_input = TextInput(
        label="What do you wanna search for?",
        placeholder="Enter a query",
        min_length=3,
        max_length=100,
    )

    def __init__(self, menu_view: "Paginator"):
        super().__init__(title="Enter your new query", timeout=180.0)
        self.menu_view = menu_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.menu_view.change_source(
            PageSource(self.menu_view.source.session, self.query_input.value)
        )
        await self.menu_view.edit_message(interaction)


class NewQuery(Button["Paginator"]):
    async def callback(self, interaction: discord.Interaction):
        return await interaction.response.send_modal(QueryModal(self.view))


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
    def __init__(self, *, emoji=None, label=None, style=discord.ButtonStyle.green, disabled=False):
        super().__init__(style=style, label=label, emoji=emoji, disabled=disabled)


class CloseButton(Button["Paginator"]):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red, label="Close", emoji="<a:ml_cross:1050019930617155624>"
        )

    async def callback(self, interaction: discord.Interaction):
        await (self.view.message or interaction.message).delete()
        self.view.stop()


class ForwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}")

    async def callback(self, interaction: discord.Interaction):
        if self.view.current_page == await self.view.source.get_max_pages():
            self.view.current_page = 1
        else:
            self.view.current_page += 1

        await self.view.edit_message(interaction)


class BackwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}")

    async def callback(self, interaction: discord.Interaction):
        if self.view.current_page == 1:
            self.view.current_page = await self.view.source.get_max_pages()
        else:
            self.view.current_page -= 1

        await self.view.edit_message(interaction)


class LastItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = await self.view.source.get_max_pages()

        await self.view.edit_message(interaction)


class FirstItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = 1

        await self.view.edit_message(interaction)


class PageButton(PaginatorButton):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, disabled=True)

    def _change_label(self):
        self.label = f"Page {self.view.current_page}/{self.view.source._max_pages}"


class PaginatorSelect(Select["Paginator"]):
    @classmethod
    async def with_pages(cls, view: "Paginator", placeholder: str = "Select a page:"):
        pages: int
        pages: int = await view.source.get_max_pages() or 0
        if pages > 25:
            minus_diff = 0
            plus_diff = 25
            if 12 < view.current_page < pages - 25:
                minus_diff = view.current_page - 12
                plus_diff = view.current_page + 13
            elif view.current_page >= pages - 25:
                minus_diff = pages - 25
                plus_diff = pages
            options = [
                discord.SelectOption(
                    label=f"Page #{i+1}", value=i, description=f"Go to page {i+1}"
                )
                for i in range(minus_diff, plus_diff)
            ]
        else:
            options = [
                discord.SelectOption(label=f"Page #{i}", value=i, description=f"Go to page {i}")
                for i in range(1, pages + 1)
            ]

        return cls(options=options, placeholder=placeholder, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page = int(self.values[0])

        await self.view.edit_message(interaction)


class Paginator(ViewDisableOnTimeout):
    def __init__(
        self,
        source: menus.PageSource,
        start_index: int = 1,
        timeout: int = 30,
        use_select: bool = False,
        extra_items: List[discord.ui.Item] = None,
    ):
        super().__init__(timeout=timeout)

        self.ctx: commands.Context
        self._source = source
        self.use_select: bool = use_select
        self.current_page: int = start_index
        self.extra_items: list[discord.ui.Item] = extra_items or []

    @property
    def source(self):
        return self._source

    async def update_buttons(self, edit=False):
        self.clear_items()
        pages = await self.source.get_max_pages() or 0
        buttons_to_add: List[Button] = (
            [FirstItemButton(), BackwardButton(), PageButton(), ForwardButton(), LastItemButton()]
            if pages > 2
            else [BackwardButton(), PageButton(), ForwardButton()]
            if pages > 1
            else []
        )
        if self.use_select and pages > 1:
            buttons_to_add.append(await PaginatorSelect.with_pages(self))

        buttons_to_add.append(CloseButton())

        for button in buttons_to_add:
            self.add_item(button)

        for item in self.extra_items:
            self.add_item(item)

        await self.update_items(edit)

    async def update_items(self, edit: bool = False):
        pages = await self.source.get_max_pages() or 0
        for i in self.children:
            if isinstance(i, PageButton):
                i._change_label()
                continue

            elif self.current_page == 1 and isinstance(i, FirstItemButton):
                i.disabled = True
                continue

            elif self.current_page == pages and isinstance(i, LastItemButton):
                i.disabled = True
                continue

            elif (um := getattr(i, "update", None)) and callable(um) and edit:
                i.update()

            i.disabled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    async def edit_message(self, inter: discord.Interaction):
        page = await self.get_page(self.current_page)

        await self.update_buttons(True)
        await inter.response.edit_message(**page)
        self.message = inter.message

    async def change_source(
        self,
        source,
        start: bool = False,
        ctx: Optional[commands.Context] = None,
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
            raise TypeError("Expected {0!r} not {1.__class__!r}.".format(PageSource, source))

        self._source = source
        self.current_page = 1
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
        ret = {"view": self}
        if isinstance(value, dict):
            ret.update(value)
        elif isinstance(value, str):
            ret.update({"content": value, "embed": None})
        elif isinstance(value, discord.Embed):
            ret.update({"embed": value, "content": None})
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
