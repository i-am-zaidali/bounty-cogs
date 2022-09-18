from datetime import datetime
from typing import Dict, Optional, Tuple, Union

import aiohttp
from redbot.core import commands
from redbot.core.bot import Red

from .model import NoExitParser, validate_end_time


class SoftRes:
    BASE_URL = "https://softres.it/api/"

    RAID_GET = BASE_URL + "raid/"
    RAID_CREATE = BASE_URL + "raid/create"
    RAID_VERIFYTOKEN = BASE_URL + "raid/verifytoken"
    RAID_VERIFYDISCORD = BASE_URL + "raid/verifydiscord"
    RAID_UPDATE = BASE_URL + "raid/update"
    RAID_PLUS = BASE_URL + "raid/plus"

    def __init__(self, bot: Red, session: Optional[aiohttp.ClientSession] = None):
        self.bot = bot
        self._session = session or aiohttp.ClientSession()

    async def _request(self, url: str, *, method="GET", json={}, headers={}) -> Union[Dict, str]:
        async with self._session.request(method, url, json=json, headers=headers) as resp:
            if resp.status == 200:
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return await resp.text()
            else:
                raise Exception(f"Error: {resp.status} {resp.reason}")

    async def create_raid(self, **kwargs) -> Tuple[str, str]:
        if not "faction" in kwargs:
            kwargs["faction"] = "Horde"

        if not "instance" in kwargs:
            raise KeyError("Missing instance")

        json = await self._request(self.RAID_CREATE, method="POST", json=kwargs)

        return json["token"], json["raidId"]

    async def update_raid(self, **kwargs):
        if not kwargs:
            raise KeyError("Missing arguments")

        await self._request(self.RAID_UPDATE, method="POST", json=kwargs)

        return await self.get_raid(kwargs["token"], kwargs["raid"]["raidId"])

    async def get_raid(self, token: str, raid_id: str):
        return await self._request(
            self.RAID_GET + f"/{raid_id}", method="GET"  # , json={"token": token, "id": raid_id}
        )

    async def get_gargul_data(self, token: str, raid_id: str) -> str:
        return await self._request(
            self.BASE_URL + f"payload/{raid_id}/gargul", method="POST", json={"token": token}
        )


class SRFlags(commands.Converter):

    # faction             Joi.string().regex(/^Alliance|Horde$/).required(),
    # instance            Joi.string().valid(...itemsUtil.lootTableZones).required(),
    # edition             Joi.string().regex(/^classic|tbc|wotlk$/),
    # discord             Joi.boolean(),
    # discordId           Joi.string().regex(/^\d{17,19}$/),
    # discordInvite       Joi.string().allow(null).allow('').regex(/^(https?:\/\/)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/[a-zA-Z0-9]+$/),
    # banned              Joi.array().items(Joi.number().integer()).max(512),
    # lock                Joi.boolean(),
    # amount              Joi.number().integer().min(1).max(10),
    # preset              Joi.number().integer().min(0).max(5),
    # note                Joi.string().max(512).allow(''),
    # raidDate            Joi.date().iso().allow(null),
    # lockRaidDate        Joi.boolean(),
    # allowDuplicate      Joi.boolean(),
    # hideReserves        Joi.boolean(),
    # itemLimit           Joi.number().integer().min(0).max(10),
    # plusModifier        Joi.number().integer().min(1).max(25),
    # plusType            Joi.number().integer().min(0).max(1),
    # characterNotes      Joi.boolean(),
    # restrictByClass     Joi.boolean(),
    # id                  Joi.string().regex(/^\d{17,19}$/)

    _parser = NoExitParser()

    _parser.add_argument(
        "-f", "--faction", choices=["Alliance", "Horde"], dest="faction", default="Horde"
    )
    _parser.add_argument(
        "--i",
        "--instance",
        type=str.lower,
        choices=[
            "aq20",
            "aq40",
            "mc",
            "bwl",
            "onyxia",
            "zg",
            "dragonsofnightmare",
            "naxxramas",
            "kara",
            "magtheridon",
            "gruul",
            "doomwalker",
            "doomlordkazzak",
            "worldbosses",
            "gruulmag",
            "ssc",
            "tempestkeep",
            "ssctempestkeep",
            "hyjal",
            "blacktemple",
            "bthyjal",
            "za",
            "sunwellplateau",
        ],
        required=True,
    )
    _parser.add_argument("--e", "--edition", choices=["classic", "tbc", "wotlk"], default="tbc")
    _parser.add_argument("--di", "--discord-invite", dest="discordInvite", default="")
    _parser.add_argument("--l", "--lock", action="store_true")
    _parser.add_argument("--a", "--amount", type=int, choices=range(1, 11), default=1)
    _parser.add_argument("--p", "--preset", type=int, choices=range(0, 6))
    _parser.add_argument("--n", "--note", default="")
    _parser.add_argument("--d", "--date", nargs="+", dest="raidDate")
    _parser.add_argument("--ad", "--allow-duplicate", action="store_true", dest="allowDuplicate")
    _parser.add_argument("--hr", "--hide-reserves", action="store_true", dest="hideReserves")
    _parser.add_argument("--il", "--item-limit", type=int, dest="itemLimit", choices=range(0, 11))
    _parser.add_argument(
        "--pm", "--plus-modifier", type=int, dest="plusModifier", choices=range(1, 26)
    )
    _parser.add_argument("--pt", "--plus-type", type=int, dest="plusType", choices=range(0, 2))
    _parser.add_argument("--cn", "--character-notes", action="store_true", dest="characterNotes")
    _parser.add_argument(
        "--rc", "--restrict-by-class", action="store_true", dest="restrictByClass"
    )

    async def convert(self, ctx: commands.Context, argument: str) -> Dict:
        v = vars(self._parser.parse_args(argument.split(" ")))

        if v["raidDate"]:
            v["raidDate"] = validate_end_time(v["raidDate"]).isoformat()

        else:
            v["raidDate"] = datetime.now().isoformat()

        v = dict(filter(lambda x: x[1] is not None, v.items()))

        return v
