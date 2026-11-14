from typing import Protocol


class AiProvider(Protocol):
    async def generate(self, instructions: str, context: str) -> str: ...


class AiTimeoutError(Exception):
    pass


class AiUnavailableError(Exception):
    pass


class AiInvalidResponseError(Exception):
    pass
