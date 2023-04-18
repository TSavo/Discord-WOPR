from dataclasses import dataclass
from typing import Any, List, Optional, Type, Union
from chatgpt import classify_intent, extract_preferences, get_new_or_existing_conversation, remove_change_of_topic
from dto import Message, Conversation
from abc import abstractmethod
from db import Database
import discord
import chatgpt
from chatgpt import summarize

Sendable = Union[discord.Webhook, discord.abc.Messageable]

@dataclass
class Action:
    name:str
    description:str
    @abstractmethod
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        pass

class ConversationCompletionAction(Action):
    def __init__(self):
        super().__init__("Conversation Completion Action", "Complete the current conversation and send the completion.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        conversation = database.get_current_conversation(message.user)
        if conversation is None:
            conversation = Conversation.new_conversation()
        conversation.add_user(message.text)
        database.set_conversation(message.user, conversation)
        completion = await chatgpt.get_completion(conversation.get_conversation())
        conversation.add_assistant(completion)
        database.set_conversation(message.user, conversation)
        await sendable.send(completion)
class ConversationSummaryAction(Action):
    def __init__(self):
        super().__init__("Conversation Summary Action", "Set a summary of the current conversation on it.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        conversation = database.get_current_conversation(message.user)
        if conversation is None:
            return
        conversation.summary = await summarize(str(conversation))
        database.set_conversation(message.user, conversation)
class ConversationChangeException(Exception):
    pass
class ChangeCurrentConversationAction(Action):
    def __init__(self):
        super().__init__("Change Current Conversation Action", "Change the current conversation.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        conversation = database.get_current_conversation(message.user)
        if conversation is None:
            conversation = Conversation.new_conversation()
            database.set_conversation(message.user, conversation)
            database.set_current_conversation(message.user, conversation)
        conversations = database.get_conversations(message.user)
        summaries = ""
        for i, convo in enumerate(conversations, start=0):
            summaries += f"{i}. {convo.summary}\n"
        conversation_index = await get_new_or_existing_conversation(summaries, message.text)
        try:
            if conversation_index == -1:
                new_conversation = Conversation.new_conversation()
                database.set_conversation(message.user, new_conversation)
                database.set_current_conversation(message.user, new_conversation)
                await sendable.send("I think this is a new conversation. One moment please...")
                raise ConversationChangeException
            elif conversations[conversation_index].id == conversation.id:
                return
            else:
                await sendable.send("Im changing topics to a prior conversation. One moment please...")
                database.set_current_conversation(message.user, conversations[conversation_index])
                raise ConversationChangeException
        except:
            return

class RememberAction(Action):
    def __init__(self): 
        super().__init__("Remember Action", "An explicit request to remember something or keep something in mind for later.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        preference = await extract_preferences(message.text)
        if preference is None:
            await sendable.send("I don't understand what you're asking me to remember.")
            return
        for k, v in preference.items():
            database.set_preference(message.user, k, v)
            await sendable.send(f"{k} is now {v}.")
        response = await chatgpt.get_completion([{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"I need a response to this that says I will remember these things: \n" + str(message.text) + "\nPlease blockquote the reply as a YAML blockquote starting with ```yaml\n```"}])
        await sendable.send(response.split("```yaml")[1].split("```")[0])

@dataclass
class Intent:
    name:str
    description:str
    @classmethod
    def get_description(cls) -> str:
        return cls.description
    @abstractmethod
    def get_actions(self, message:Message) -> List[Action]:
        pass

class TopicChangeIntent(Intent):
    name:str="Topic Change Intent"
    description:str="An explicit request to change the topic, or an implict request to discuss something unrelated to what we have been discussing."
    def __init__(self):
        pass
    def get_actions(self, message: Message) -> List[Action]:
        return [ChangeCurrentConversationAction(), ConversationCompletionAction(), ConversationSummaryAction()]
class NoOpIntent(Intent):
    name:str = "NoOp Intent"
    description:str = "None of the above"
    def __init__(self):
        pass
    @staticmethod
    def get_actions(message: Message) -> List[Action]:
        return [ConversationCompletionAction(), ConversationSummaryAction()]

class PleasantryIntent(NoOpIntent):
    name:str = "Pleasantry Intent"
    description:str = "Just a greeting, affirmation, platitude, or pleasantry and nothing more."

class RememberIntent(Intent):
    name:str = "Remember Intent"
    description:str = "An explicit request to remember something."
    def __init__(self):
        pass
    def get_actions(self, message: Message) -> List[Action]:
        return [RememberAction()]

class IntentClassifier:
    async def classify_intent(self, message : Message) -> Type[Intent]:
        possible_intents = Intent.__subclasses__()
        descriptions = [x.get_description() for x in possible_intents]
        intent_index = await classify_intent(descriptions, message.text, message.context)
        return possible_intents[intent_index]

@dataclass
class MessageHandler:
    intent_classifier:IntentClassifier = IntentClassifier()
    async def handle_interaction(self, message : Message, database : Database, interaction : discord.Interaction):
        try:
            await interaction.response.defer()
            await interaction.delete_original_response()
        except:
            pass
        intent_type = await self.intent_classifier.classify_intent(message)
        intent = type(intent_type)()
        actions = intent.get_actions(message)
        try:
            for action in actions:
                await action(message, database, interaction.followup)
        except ConversationChangeException:
            message.text = await remove_change_of_topic(message.text)
            await self.handle_message(message, database, interaction.followup)

    async def handle_message(self, message: Message, database : Database, sendable : Sendable):
        intent_type = await self.intent_classifier.classify_intent(message)
        intent = intent_type() # type: ignore
        actions = intent.get_actions(message)
        try:
            for action in actions:
                await action(message, database, sendable)
        except ConversationChangeException:
            message.text = await remove_change_of_topic(message.text)
            await self.handle_message(message, database, sendable)

    async def send_conversation_for_completion(self, message: Message, database: Database, sendable: Sendable):
        await ConversationCompletionAction()(message, database, sendable)