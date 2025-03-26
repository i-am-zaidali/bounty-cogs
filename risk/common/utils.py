import itertools
import typing

T = typing.TypeVar("T")


def chunks(
    iterable: typing.Iterable[T], size: int
) -> typing.Generator[typing.List[T], None, None]:
    """Yield successive n-sized chunks from l."""
    if size < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, size)):
        yield batch
