from abc import ABC, ABCMeta, abstractmethod
from typing import TYPE_CHECKING

from discord.ext.commands.cog import CogMeta

if TYPE_CHECKING:
    from redbot.core.bot import Red

    from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB

    @abstractmethod
    async def save(self) -> None:
        raise NotImplementedError
