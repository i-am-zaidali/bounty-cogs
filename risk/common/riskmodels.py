import asyncio
import enum
import itertools
import random
import typing

import discord
import pydantic
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from risk.common.map_generator import RiskMapGenerator

from . import Base

if typing.TYPE_CHECKING:
    from risk.main import Risk

T = typing.TypeVar("T")

color_names = {
    (214, 32, 199): "Pink",
    (214, 47, 32): "Red",
    (224, 220, 92): "Yellow",
    (217, 149, 54): "Orange",
    (52, 194, 95): "Green",
    (128, 34, 179): "Purple",
}


class RangeDict(dict[range, T]):
    def __getitem__(self, key: int) -> T:
        for r in self:
            if key in r:
                return super().__getitem__(r)
        raise KeyError(key)

    def __setitem__(self, key: int | range, value: T) -> None:
        if isinstance(key, range):
            super().__setitem__(key, value)

        elif isinstance(key, int):
            for r in self:
                if key in r:
                    super().__setitem__(r, value)
                    return
            raise KeyError(key)

        else:
            raise TypeError(f"key must be int or range, not {type(key)}")

    def __delitem__(self, key: range) -> None:
        raise NotImplementedError("deletion of ranges is not supported")

    def __iter__(self) -> typing.Iterator[range]:
        return super().__iter__()

    def __contains__(self, key: int | range | typing.Any) -> bool:
        if isinstance(key, (int, range)):
            return any(key == r or key in r for r in self)
        else:
            return False

    def __repr__(self) -> str:
        return f"RangeDict({super().__repr__()})"


class Continent(enum.IntEnum):
    NORTH_AMERICA = 5
    SOUTH_AMERICA = 2
    EUROPE = 5
    AFRICA = 3
    ASIA = 7
    AUSTRALIA = 2

    def __init__(self, capture_armies_award: int):
        super().__init__()
        self.territories = list["Territory"]()


territory_ranges = RangeDict(
    {
        range(0, 9): Continent.NORTH_AMERICA,
        range(9, 13): Continent.SOUTH_AMERICA,
        range(13, 20): Continent.EUROPE,
        range(20, 26): Continent.AFRICA,
        range(26, 38): Continent.ASIA,
        range(38, 42): Continent.AUSTRALIA,
    }
)


class Territory(enum.IntEnum):
    ALASKA = 0
    ALBERTA = enum.auto()
    CENTRAL_AMERICA = enum.auto()
    EASTERN_UNITED_STATES = enum.auto()
    GREENLAND = enum.auto()
    NORTHWEST_TERRITORY = enum.auto()
    ONTARIO = enum.auto()
    QUEBEC = enum.auto()
    WESTERN_UNITED_STATES = enum.auto()

    ARGENTINA = enum.auto()
    BRAZIL = enum.auto()
    PERU = enum.auto()
    VENEZUELA = enum.auto()

    GREAT_BRITAIN = enum.auto()
    ICELAND = enum.auto()
    NORTHERN_EUROPE = enum.auto()
    SCANDINAVIA = enum.auto()
    SOUTHERN_EUROPE = enum.auto()
    UKRAINE = enum.auto()
    WESTERN_EUROPE = enum.auto()

    CONGO = enum.auto()
    EAST_AFRICA = enum.auto()
    EGYPT = enum.auto()
    MADAGASCAR = enum.auto()
    NORTH_AFRICA = enum.auto()
    SOUTH_AFRICA = enum.auto()

    AFGHANISTAN = enum.auto()
    CHINA = enum.auto()
    INDIA = enum.auto()
    IRKUTSK = enum.auto()
    JAPAN = enum.auto()
    KAMCHATKA = enum.auto()
    MIDDLE_EAST = enum.auto()
    MONGOLIA = enum.auto()
    SIAM = enum.auto()
    SIBERIA = enum.auto()
    URAL = enum.auto()
    YAKUTSK = enum.auto()

    EASTERN_AUSTRALIA = enum.auto()
    INDONESIA = enum.auto()
    NEW_GUINEA = enum.auto()
    WESTERN_AUSTRALIA = enum.auto()

    def __init__(self, id: int):
        self.continent = territory_ranges[self.value]
        self.continent.territories.append(self)


coords = {
    Territory.AFGHANISTAN: (1993, 761),
    Territory.ALASKA: (225, 322),
    Territory.ALBERTA: (466, 480),
    Territory.ARGENTINA: (772, 1594),
    Territory.BRAZIL: (912, 1300),
    Territory.CENTRAL_AMERICA: (474, 891),
    Territory.CHINA: (2358, 898),
    Territory.CONGO: (1599, 1493),
    Territory.EAST_AFRICA: (1722, 1328),
    Territory.EASTERN_AUSTRALIA: (2749, 1647),
    Territory.EASTERN_UNITED_STATES: (662, 780),
    Territory.EGYPT: (1582, 1154),
    Territory.GREAT_BRITAIN: (1264, 685),
    Territory.GREENLAND: (1022, 204),
    Territory.ICELAND: (1270, 429),
    Territory.INDIA: (2177, 1068),
    Territory.INDONESIA: (2464, 1442),
    Territory.IRKUTSK: (2363, 549),
    Territory.JAPAN: (2716, 744),
    Territory.KAMCHATKA: (2645, 277),
    Territory.MADAGASCAR: (1892, 1770),
    Territory.MIDDLE_EAST: (1833, 996),
    Territory.MONGOLIA: (2398, 704),
    Territory.NEW_GUINEA: (2715, 1396),
    Territory.NORTH_AFRICA: (1352, 1243),
    Territory.NORTHERN_EUROPE: (1481, 691),
    Territory.NORTHWEST_TERRITORY: (443, 310),
    Territory.ONTARIO: (640, 526),
    Territory.PERU: (755, 1385),
    Territory.QUEBEC: (842, 520),
    Territory.UKRAINE: (1745, 569),
    Territory.SCANDINAVIA: (1470, 445),
    Territory.SIAM: (2406, 1142),
    Territory.SIBERIA: (2198, 348),
    Territory.SOUTH_AFRICA: (1639, 1759),
    Territory.SOUTHERN_EUROPE: (1494, 843),
    Territory.URAL: (2047, 489),
    Territory.VENEZUELA: (708, 1121),
    Territory.WESTERN_AUSTRALIA: (2581, 1751),
    Territory.WESTERN_EUROPE: (1260, 950),
    Territory.WESTERN_UNITED_STATES: (456, 701),
    Territory.YAKUTSK: (2420, 273),
}


class ArmyDenominations(enum.IntEnum):
    INFANTRY = 1
    CAVALRY = 5
    ARTILLERY = 10


class Card(Base):
    army: typing.Optional[ArmyDenominations]
    territory: typing.Optional[Territory]

    def __str__(self):
        if self.army is None:
            return "Wildcard"
        return f"{self.territory.name}: {self.army.name}"

    def __repr__(self):
        return str(self)


cards: list[Card] = []

for continent in Continent:
    cycle = itertools.cycle(ArmyDenominations)
    for territory in continent.territories:
        card = Card(army=next(cycle), territory=territory)
        cards.append(card)

cards.extend(
    # wildcards
    [
        Card(army=None, territory=None),
        Card(army=None, territory=None),
    ]
)


class Player(Base):
    id: int
    turn: int
    color: tuple[int, int, int]
    initial_roll: int = pydantic.Field(default_factory=lambda: random.randint(1, 6))
    cards: list[Card] = pydantic.Field(default_factory=list)
    armies: int = 0
    captured_territories: dict[Territory, int] = pydantic.Field(default_factory=dict)

    """A dictionary mapping each territory to the amount of armies placed on it"""

    @property
    def total_armies(self) -> int:
        return sum(self.armies)

    @property
    def mention(self):
        return f"<@{self.id}>"


class TurnPhase(enum.Enum):
    ARMY_CALCULATION = enum.auto()
    CARD_TRADE = enum.auto()
    INITIAL_ARMY_PLACEMENT = enum.auto()
    PLACE_ARMIES = enum.auto()
    ATTACK = enum.auto()
    FORTIFY = enum.auto()

    FORCED_CARD_TRADE = enum.auto()

    @property
    def required(self) -> bool:
        match self:
            case (
                TurnPhase.ARMY_CALCULATION
                | TurnPhase.INITIAL_ARMY_PLACEMENT
                | TurnPhase.PLACE_ARMIES
                | TurnPhase.FORCED_CARD_TRADE
            ):
                return True

            case _:
                return False

    def next(self):
        match self:
            case TurnPhase.ARMY_CALCULATION:
                return TurnPhase.CARD_TRADE

            case TurnPhase.INITIAL_ARMY_PLACEMENT:
                return TurnPhase.INITIAL_ARMY_PLACEMENT

            case TurnPhase.PLACE_ARMIES:
                return TurnPhase.ATTACK

            case TurnPhase.ATTACK:
                return TurnPhase.FORTIFY

            case TurnPhase.FORTIFY:
                return TurnPhase.ARMY_CALCULATION

            case _:
                return TurnPhase.PLACE_ARMIES


class RiskState(Base):
    host: int
    players: list[Player] = pydantic.Field(default_factory=list, max_items=6)
    territories: dict[Territory, int | None] = pydantic.Field(
        default_factory=lambda: dict.fromkeys(Territory), repr=False
    )
    turn: int = -1
    turn_phase: TurnPhase = TurnPhase.PLACE_ARMIES
    turn_phase_completed: bool = False
    turn_armies_received: bool = False
    turn_territories_captured: int = 0
    draw_pile: list[Card] = pydantic.Field(
        default_factory=lambda: sorted(cards.copy(), key=lambda _: random.random())
    )

    card_sets_traded: int = 0

    COLORS: set[tuple[int, int, int]] = pydantic.Field(
        default_factory=lambda: set(color_names)
    )

    @property
    def turn_player(self) -> Player:
        return self.players[self.turn]

    @pydantic.model_validator(mode="after")
    def sort_players_properly(self):
        self.players.sort(key=lambda p: p.turn)
        return self

    def next_turn(self):
        self.turn = (self.turn + 1) % len(self.players)
        self.turn_phase_completed = False
        self.turn_armies_received = False
        self.turn_territories_captured = 0

    async def format_embed(self, inter: discord.Interaction[Red]):
        cog = (
            inter.cog
            if isinstance(inter, commands.Context)
            else inter.client.get_cog("Risk")
        )

        territory_armies = {
            coords[terr]: str(self.players[turn].captured_territories[terr])
            if turn is not None
            else "?"
            for terr, turn in self.territories.items()
        }

        territory_colors = {
            coords[terr]: self.players[turn].color
            if turn is not None
            else (128, 128, 128)
            for terr, turn in self.territories.items()
        }

        image = await asyncio.to_thread(
            RiskMapGenerator.color_territories,
            clear_image_path=bundled_data_path(cog) / "risk_board.png",
            territory_colors=territory_colors,
            territory_armies=territory_armies,
        )

        return discord.File(image, filename="risk_board.png")


territory_adjacency = {
    # North America
    Territory.ALASKA: [
        Territory.NORTHWEST_TERRITORY,
        Territory.ALBERTA,
        Territory.KAMCHATKA,
    ],
    Territory.ALBERTA: [
        Territory.ALASKA,
        Territory.NORTHWEST_TERRITORY,
        Territory.ONTARIO,
        Territory.WESTERN_UNITED_STATES,
    ],
    Territory.CENTRAL_AMERICA: [
        Territory.WESTERN_UNITED_STATES,
        Territory.EASTERN_UNITED_STATES,
        Territory.VENEZUELA,
    ],
    Territory.EASTERN_UNITED_STATES: [
        Territory.ONTARIO,
        Territory.QUEBEC,
        Territory.WESTERN_UNITED_STATES,
        Territory.CENTRAL_AMERICA,
    ],
    Territory.GREENLAND: [
        Territory.NORTHWEST_TERRITORY,
        Territory.ONTARIO,
        Territory.QUEBEC,
        Territory.ICELAND,
    ],
    Territory.NORTHWEST_TERRITORY: [
        Territory.ALASKA,
        Territory.ALBERTA,
        Territory.ONTARIO,
        Territory.GREENLAND,
    ],
    Territory.ONTARIO: [
        Territory.NORTHWEST_TERRITORY,
        Territory.ALBERTA,
        Territory.QUEBEC,
        Territory.EASTERN_UNITED_STATES,
        Territory.WESTERN_UNITED_STATES,
        Territory.GREENLAND,
    ],
    Territory.QUEBEC: [
        Territory.ONTARIO,
        Territory.EASTERN_UNITED_STATES,
        Territory.GREENLAND,
    ],
    Territory.WESTERN_UNITED_STATES: [
        Territory.ALBERTA,
        Territory.ONTARIO,
        Territory.EASTERN_UNITED_STATES,
        Territory.CENTRAL_AMERICA,
    ],
    # South America
    Territory.ARGENTINA: [Territory.BRAZIL, Territory.PERU],
    Territory.BRAZIL: [
        Territory.VENEZUELA,
        Territory.PERU,
        Territory.ARGENTINA,
        Territory.NORTH_AFRICA,
    ],
    Territory.PERU: [Territory.VENEZUELA, Territory.BRAZIL, Territory.ARGENTINA],
    Territory.VENEZUELA: [Territory.CENTRAL_AMERICA, Territory.BRAZIL, Territory.PERU],
    # Europe
    Territory.GREAT_BRITAIN: [
        Territory.ICELAND,
        Territory.SCANDINAVIA,
        Territory.NORTHERN_EUROPE,
        Territory.WESTERN_EUROPE,
    ],
    Territory.ICELAND: [
        Territory.GREENLAND,
        Territory.SCANDINAVIA,
        Territory.GREAT_BRITAIN,
    ],
    Territory.NORTHERN_EUROPE: [
        Territory.SCANDINAVIA,
        Territory.GREAT_BRITAIN,
        Territory.WESTERN_EUROPE,
        Territory.SOUTHERN_EUROPE,
    ],
    Territory.UKRAINE: [
        Territory.SCANDINAVIA,
        Territory.NORTHERN_EUROPE,
        Territory.SIBERIA,
        Territory.URAL,
        Territory.MONGOLIA,
    ],
    Territory.SCANDINAVIA: [
        Territory.ICELAND,
        Territory.NORTHERN_EUROPE,
        Territory.UKRAINE,
    ],
    Territory.SOUTHERN_EUROPE: [
        Territory.WESTERN_EUROPE,
        Territory.NORTHERN_EUROPE,
        Territory.NORTH_AFRICA,
        Territory.EGYPT,
        Territory.MIDDLE_EAST,
    ],
    Territory.WESTERN_EUROPE: [
        Territory.GREAT_BRITAIN,
        Territory.NORTHERN_EUROPE,
        Territory.SOUTHERN_EUROPE,
        Territory.NORTH_AFRICA,
    ],
    # Africa
    Territory.CONGO: [
        Territory.NORTH_AFRICA,
        Territory.EAST_AFRICA,
        Territory.SOUTH_AFRICA,
    ],
    Territory.EAST_AFRICA: [
        Territory.EGYPT,
        Territory.NORTH_AFRICA,
        Territory.CONGO,
        Territory.MADAGASCAR,
        Territory.MIDDLE_EAST,
    ],
    Territory.EGYPT: [
        Territory.NORTH_AFRICA,
        Territory.SOUTHERN_EUROPE,
        Territory.MIDDLE_EAST,
        Territory.EAST_AFRICA,
    ],
    Territory.MADAGASCAR: [Territory.EAST_AFRICA, Territory.SOUTH_AFRICA],
    Territory.NORTH_AFRICA: [
        Territory.BRAZIL,
        Territory.WESTERN_EUROPE,
        Territory.SOUTHERN_EUROPE,
        Territory.EGYPT,
        Territory.EAST_AFRICA,
        Territory.CONGO,
    ],
    Territory.SOUTH_AFRICA: [
        Territory.CONGO,
        Territory.EAST_AFRICA,
        Territory.MADAGASCAR,
    ],
    # Asia
    Territory.AFGHANISTAN: [
        Territory.URAL,
        Territory.UKRAINE,
        Territory.MIDDLE_EAST,
        Territory.INDIA,
    ],
    Territory.CHINA: [
        Territory.MONGOLIA,
        Territory.SIAM,
        Territory.INDIA,
        Territory.AFGHANISTAN,
        Territory.SIBERIA,
    ],
    Territory.INDIA: [
        Territory.MIDDLE_EAST,
        Territory.AFGHANISTAN,
        Territory.CHINA,
        Territory.SIAM,
    ],
    Territory.IRKUTSK: [
        Territory.SIBERIA,
        Territory.MONGOLIA,
        Territory.YAKUTSK,
        Territory.KAMCHATKA,
    ],
    Territory.JAPAN: [Territory.KAMCHATKA, Territory.MONGOLIA],
    Territory.KAMCHATKA: [
        Territory.ALASKA,
        Territory.JAPAN,
        Territory.IRKUTSK,
        Territory.MONGOLIA,
        Territory.YAKUTSK,
    ],
    Territory.MIDDLE_EAST: [
        Territory.SOUTHERN_EUROPE,
        Territory.EGYPT,
        Territory.EAST_AFRICA,
        Territory.INDIA,
        Territory.AFGHANISTAN,
    ],
    Territory.MONGOLIA: [
        Territory.SIBERIA,
        Territory.IRKUTSK,
        Territory.KAMCHATKA,
        Territory.JAPAN,
        Territory.CHINA,
    ],
    Territory.SIAM: [Territory.INDIA, Territory.CHINA, Territory.INDONESIA],
    Territory.SIBERIA: [
        Territory.URAL,
        Territory.UKRAINE,
        Territory.YAKUTSK,
        Territory.IRKUTSK,
        Territory.CHINA,
        Territory.MONGOLIA,
    ],
    Territory.URAL: [Territory.UKRAINE, Territory.SIBERIA, Territory.AFGHANISTAN],
    Territory.YAKUTSK: [Territory.SIBERIA, Territory.IRKUTSK, Territory.KAMCHATKA],
    # Australia
    Territory.EASTERN_AUSTRALIA: [Territory.NEW_GUINEA, Territory.WESTERN_AUSTRALIA],
    Territory.INDONESIA: [
        Territory.NEW_GUINEA,
        Territory.WESTERN_AUSTRALIA,
        Territory.SIAM,
    ],
    Territory.NEW_GUINEA: [Territory.INDONESIA, Territory.EASTERN_AUSTRALIA],
    Territory.WESTERN_AUSTRALIA: [Territory.EASTERN_AUSTRALIA, Territory.INDONESIA],
}
