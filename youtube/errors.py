class APIError(Exception):
    def __init__(self, status_code: int, raw_data) -> None:
        self.status_code = status_code
        self.raw_data = raw_data
        super().__init__(f"{status_code=} {raw_data=}")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self!s})"

class InvalidYoutubeCredentials(Exception):
    pass


class YoutubeQuotaExceeded(Exception):
    pass