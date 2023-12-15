from typing import Union
import discord
from db import Database
from dto import Message
from message_handler import MessageHandler
from sendable import Sendable, Editable
from typing import Callable, Any, Tuple, Optional
DiscordSendableType = Union[discord.Webhook, discord.abc.Messageable]

class DiscordSendable(Sendable):
    def __init__(self, sendable: DiscordSendableType):
        self.sendable : DiscordSendableType = sendable
        self.editable : Optional[Editable] = None
        self.content : str = ""
        self.sent : int = 0
    async def send(self, message: str, view:Any = None) -> Editable:
        if view is not None:
            return Editable(await self.sendable.send(message, view=view))
        return Editable(await self.sendable.send(message))
    def get_pipe(self) -> Tuple[Callable[[str], Editable], Callable[[], None]]:
        async def pipe(message):
            nonlocal self
            self.content += message
            if len(self.content) > self.sent + 100:
                self.sent = len(self.content)
                if(self.editable is None):
                    self.editable = await self.send(self.content)
                else:
                    await self.editable.edit(self.content)
        async def done():
            nonlocal self
            if self.content == "":
                return
            if self.editable is None:
                await self.send(self.content)
            else:
                await self.editable.edit(self.content)
        return pipe, done

class DiscordHandler(MessageHandler):
    async def handle_discord_message(self, message: discord.Message, database: Database, sendable : DiscordSendableType):
        if isinstance(sendable, discord.Interaction):
            await self.handle_discord_interaction(Message.from_message(message), database, sendable)
        else:
            await self.handle_message(Message.from_message(message), database, DiscordSendable(sendable))

    async def handle_discord_interaction(self, message: Message, database: Database, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            await interaction.delete_original_response()
        except Exception:
            pass 
        return await self.handle_message(message, database, DiscordSendable(interaction.followup))
    
