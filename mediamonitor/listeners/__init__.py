from ..abc import CompositeMetaClass
from .messages import MessageListeners


class Listeners(MessageListeners, metaclass=CompositeMetaClass):
    """
    Subclass all listeners in this directory so you can import this single Listeners class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """
