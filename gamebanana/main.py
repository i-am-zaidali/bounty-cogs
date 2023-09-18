from typing import List, TypedDict

import aiohttp
import discord
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red

from .views import NewQuery, PageSource, Paginator

prefixes = {"_s": str, "_n": int, "_b": bool, "_ts": int, "_a": dict}  # timestamps

base_url = "https://gamebanana.com/apiv11/"
_sample_request = "https://gamebanana.com/apiv11/Util/Search/Results?_nPage=1&_sOrder=best_match&_sSearchString=fubuki and friends&_csvFields=name,description,article,attribs,studio,owner,credits"

_sample_response = {
    "_aMetadata": {
        "_nRecordCount": 999,
        "_nPerpage": 15,
        "_bIsComplete": False,
        "_aSectionMatchCounts": [
            {
                "_sModelName": "App",
                "_sPluralTitle": "Apps",
                "_sDescription": "Mini programs that enhance the site",
                "_sIconClasses": "SubmissionTypeSmall App",
                "_nMatchCount": 34,
            },
            ...,
        ],
    },
    "_aRecords:": [
        {
            "_idRow": 360260,
            "_sModelName": "Mod",
            "_sSingularTitle": "Mod",
            "_sIconClasses": "SubmissionType Mod",
            "_sName": "Fubuki X Caramelldansen Custom Chart",
            "_sProfileUrl": "https://gamebanana.com/mods/360260",
            "_tsDateAdded": 1645752358,
            "_tsDateModified": 1645752358,
            "_bHasFiles": True,
            "_aTags": [],
            "_aPreviewMedia": {
                "_aImages": [
                    {
                        "_sType": "screenshot",
                        "_sBaseUrl": "https://images.gamebanana.com/img/ss/mods",
                        "_sFile": "62182ceee756c.jpg",
                        "_sFile220": "220-90_62182ceee756c.jpg",
                        "_sFile530": "530-90_62182ceee756c.jpg",
                        "_sFile100": "100-90_62182ceee756c.jpg",
                        "_hFile220": 123,
                        "_wFile220": 220,
                        "_hFile530": 298,
                        "_wFile530": 530,
                        "_hFile100": 56,
                        "_wFile100": 100,
                    },
                    {
                        "_sType": "screenshot",
                        "_sBaseUrl": "https://images.gamebanana.com/img/ss/mods",
                        "_sFile": "62182ea940377.jpg",
                        "_sFile100": "100-90_62182ea940377.jpg",
                        "_hFile100": 56,
                        "_wFile100": 100,
                    },
                ]
            },
            "_aSubmitter": {
                "_idRow": 1876214,
                "_sName": "Elonds",
                "_bIsOnline": False,
                "_bHasRipe": False,
                "_sProfileUrl": "https://gamebanana.com/members/1876214",
                "_sAvatarUrl": "https://images.gamebanana.com/static/img/defaults/avatar.gif",
            },
            "_aGame": {
                "_idRow": 8694,
                "_sName": "Friday Night Funkin'",
                "_sProfileUrl": "https://gamebanana.com/games/8694",
                "_sIconUrl": "https://images.gamebanana.com/img/ico/games/62082c1edaf3d.png",
            },
            "_aRootCategory": {
                "_sName": "Executables",
                "_sProfileUrl": "https://gamebanana.com/mods/cats/3827",
                "_sIconUrl": "https://images.gamebanana.com/img/ico/ModCategory/60382d91c4839.png",
            },
            "_sVersion": "",
            "_bIsObsolete": False,
            "_sInitialVisibility": "show",
            "_bHasContentRatings": False,
            "_nLikeCount": 3,
            "_bWasFeatured": False,
            "_nViewCount": 1187,
            "_bIsOwnedByAccessor": False,
        },
        ...,
    ],
}


class ResponseDict(TypedDict):
    _aMetadata: dict
    _aRecords: List[dict]


class RecordDict(TypedDict):
    _idRow: int
    _sModelName: str
    _sSingularTitle: str
    _sIconClasses: str
    _sName: str
    _sProfileUrl: str
    _tsDateAdded: int
    _tsDateModified: int
    _bHasFiles: bool
    _aTags: List[str]
    _aPreviewMedia: dict
    _aSubmitter: dict
    _aGame: dict
    _aRootCategory: dict
    _sVersion: str
    _bIsObsolete: bool
    _sInitialVisibility: str
    _bHasContentRatings: bool
    _nLikeCount: int
    _bWasFeatured: bool
    _nViewCount: int
    _bIsOwnedByAccessor: bool


class GameBanana(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        await self.session.close()

    @commands.hybrid_group("gamebanana", fallback="help", aliases=["gb"])
    async def gb(self, ctx: commands.Context):
        """GameBanana commands"""
        return await ctx.send_help()

    @gb.command(name="search", aliases=["s"], usage="<query>")
    @app_commands.describe(
        query="The query to search for", private="Whether to send the menu ephemerally"
    )
    async def gb_search(
        self, ctx: commands.Context, *, query: commands.Range[str, 3], private: bool = False
    ):
        """Search for mods on the gamebanana website for the game: Hatsune Miku: Project DIVA Mega Mix+"""
        source = PageSource(self.session, query)
        menu = Paginator(
            source, 1, 60, True, [NewQuery(style=discord.ButtonStyle.green, label="Change Query")]
        )
        await menu.start(ctx, ephemeral=private)
