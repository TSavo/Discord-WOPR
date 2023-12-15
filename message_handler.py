from typing import Protocol
from action import ConversationChangeException
from db import Database, UserUnion
from dto import Message
from intent import Intent
from intent_classifier import IntentClassifier
from sendable import Sendable
import chatgpt

class CustomHandler(Protocol):
    async def __call__(self, message: Message, database: Database, sendable: Sendable) -> None:
        ...
    
class MessageHandler:
    def __init__(self):
        self.custom_handlers: dict[str, CustomHandler] = {}
        self.intent_classifier = IntentClassifier()

    async def add_custom_handler(self, user:UserUnion, handler):
        self.custom_handlers[str(user.id)] = handler
    
    async def remove_custom_handler(self, user:UserUnion):
        if str(user.id) in self.custom_handlers:
            del self.custom_handlers[str(user.id)]

    async def handle_message(self, message: Message, database: Database, sendable: Sendable):
        if str(message.user.id) in self.custom_handlers:
            await self.custom_handlers[str(message.user.id)](message, database, sendable)
            del self.custom_handlers[str(message.user.id)]
            return
        intents = await self.intent_classifier.classify_intent(message, Intent.__subclasses__())
        while(len(intents) > 0): #No for loop here, because we might change state in the middle of the loop
            intent = intents.pop(0)
            actions = intent.get_actions()
            while(len(actions) > 0): #No for loop here, because we might change state in the middle of the loop
                action = actions.pop(0)
                try:
                    await action(message, database, sendable)
                except ConversationChangeException:
                    message.text = await chatgpt.remove_change_of_topic(message.text)
                    await self.handle_message(message, database, sendable)
                    return
