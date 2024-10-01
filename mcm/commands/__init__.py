from ..abc import CompositeMetaClass  # noqa: I001
from .group import MCMGroup
from .mcm_vehicles import MCMVehicles
from .mcm_channels import MCMChannels
from .mcm_userstats import MCMUserStats
from .mcm_stateroles import MCMStateRoles
from .mcm_courses import MCMCourses
from .mcm import MCMTopLevel


class Commands(
    MCMGroup,
    MCMCourses,
    MCMTopLevel,
    MCMVehicles,
    MCMChannels,
    MCMStateRoles,
    MCMUserStats,
    metaclass=CompositeMetaClass,
):
    """Subclass all command classes"""
