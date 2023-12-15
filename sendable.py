from abc import abstractmethod
from typing import Callable, Any, Tuple


class Editable():
    def __init__(self, editable: Any):
        self.editable = editable
    async def edit(self, content):
        await self.editable.edit(content=content)
    async def delete(self):
        await self.editable.delete_original_message()

class Sendable():
    @abstractmethod
    async def send(self, message:str, view: Any = None) -> Editable:
        raise NotImplementedError("Not implemented")
    def get_pipe(self) -> Tuple[Callable[[str], Editable], Callable[[], None]]:
        raise NotImplementedError("Not implemented")
    


