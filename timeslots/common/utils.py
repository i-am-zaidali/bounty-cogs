import datetime
import itertools
import typing

T = typing.TypeVar("T")
D_DT = typing.TypeVar("D_DT", datetime.date, datetime.datetime)


def chunks(iterable: typing.Iterable[T], n: int):
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, n)):
        yield batch


def dates_iter(
    start: D_DT, end: D_DT | None = None
) -> typing.Generator[D_DT, typing.Any, None]:
    end = type(start).max if end is None else end
    while start <= end:
        yield start
        start += datetime.timedelta(days=1)


Missing = object()


def all_min(
    iterable: typing.Iterable[T],
    key: typing.Callable[[T], typing.Any] = lambda x: x,
    *,
    sortkey: typing.Optional[typing.Callable[[T], typing.Any]] = Missing,
) -> list[T]:
    """A simple one liner function that returns all the least elements of an iterable instead of just one like the builtin `min()`.

    !!!!!! SORT THE DATA PRIOR TO USING THIS FUNCTION !!!!!!
    or pass the `sortkey` argument to this function which will be passed to the `sorted()` builtin to sort the iterable

    A small explanation of what it does from bard:
    - itertools.groupby() groups the elements in the iterable by their key value.
    - map() applies the function lambda x: (x[0], list(x[1])) to each group.
      This function returns a tuple containing the key of the group and a list of all of the elements in the group.
    - min() returns the tuple with the minimum key value.
    - [1] gets the second element of the tuple, which is the list of all of the minimum elements in the iterable.
    """
    if not iterable:
        return []
    if sortkey is not Missing:
        iterable = sorted(iterable, key=sortkey)
    try:
        return min(
            ((x[0], list(x[1])) for x in itertools.groupby(iterable, key=key)),
            key=lambda x: x[0],
        )[1]

    except ValueError:
        return []
