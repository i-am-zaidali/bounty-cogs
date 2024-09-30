from ..abc import CompositeMetaClass
from .settings import Settings
from .user import User


class Commands(Settings, User, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
