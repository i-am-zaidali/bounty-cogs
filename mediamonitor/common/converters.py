import enum
import importlib.util
import logging

from redbot.core import commands

if importlib.util.find_spec("regex"):
    import regex as re
else:
    import re

log = logging.getLogger("red.mediamonitor.converters")


"Respectfully ~stolen~ borrowed from TrustyJaid's ReTrigger: https://github.com/TrustyJAID/Trusty-cogs/blob/44953b9720eece306fe4ba5c95356b17c70b5934/retrigger/converters.py#L719C1-L736C22"


class ValidRegex(commands.Converter):
    """
    This will check to see if the provided regex pattern is valid
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        try:
            re.compile(argument)
            result = argument
        except Exception as e:
            err_msg = f"`{argument}` is not a valid regex pattern: {e}"
            log.error(
                "Retrigger invalid regex error: Pattern %s Reason %s", argument, e
            )
            raise commands.BadArgument(err_msg)
        return result


class MemoryUnits(enum.IntFlag):
    B = 1
    KB = 2
    MB = 3
    GB = 4
    TB = 5


class ReadableMemoryToBytes(commands.Converter):
    """
    This will convert human readable memory units to bytes.
    Examples: 10MB, 5 GB, 2048kb
    """

    def __init__(
        self,
        allowed_units: MemoryUnits = MemoryUnits.B
        | MemoryUnits.KB
        | MemoryUnits.MB
        | MemoryUnits.GB
        | MemoryUnits.TB,
    ) -> None:
        super().__init__()
        self.allowed_units = allowed_units

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        pattern = r"^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)$"
        match = re.match(pattern, argument.strip(), re.IGNORECASE)
        if not match:
            raise commands.BadArgument(
                f"`{argument}` is not a valid memory size format. Examples: 10MB, 5 GB, 2048kb"
            )

        size_str, unit_str = match.groups()
        size = float(size_str)
        unit_str = unit_str.upper()

        unit_multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024**2,
            "GB": 1024**3,
            "TB": 1024**4,
        }

        if unit_str not in unit_multipliers:
            raise commands.BadArgument(
                f"`{unit_str}` is not a recognized memory unit. Use B, KB, MB, GB, or TB."
            )

        unit_enum = MemoryUnits[unit_str]
        if not (self.allowed_units & unit_enum):
            allowed = ", ".join([u.name for u in MemoryUnits if self.allowed_units & u])
            raise commands.BadArgument(
                f"`{unit_str}` is not an allowed memory unit. Allowed units are: {allowed}."
            )

        bytes_size = int(size * unit_multipliers[unit_str])
        return bytes_size


def bytes_to_readable_memory(size_in_bytes: int) -> str:
    """
    Converts bytes to a human-readable memory size format.
    Examples: 10MB, 5 GB, 2048kb
    """
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024**2:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024**3:
        return f"{size_in_bytes / 1024**2:.2f} MB"
    elif size_in_bytes < 1024**4:
        return f"{size_in_bytes / 1024**3:.2f} GB"
    else:
        return f"{size_in_bytes / 1024**4:.2f} TB"


TimeConverter = commands.get_timedelta_converter(
    allowed_units=["days", "hours", "minutes"]
)
