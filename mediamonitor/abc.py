from abc import ABC, ABCMeta, abstractmethod
from typing import TYPE_CHECKING

from discord.ext.commands.cog import CogMeta

if TYPE_CHECKING:
    import multiprocessing.pool

    from redbot.core.bot import Red

    from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.re_pool: multiprocessing.pool.Pool

    @abstractmethod
    def save(self) -> None:
        pass
