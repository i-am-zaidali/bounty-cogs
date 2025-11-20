from ..abc import CompositeMetaClass
from .pollendmessage import PollEndMessageListener


class Listeners(PollEndMessageListener, metaclass=CompositeMetaClass):
    """
    Subclass all listeners in this directory so you can import this single Listeners class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """
