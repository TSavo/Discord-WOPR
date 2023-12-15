from abc import abstractmethod
from typing import List, TypeVar, Union
from action import Action, ChangeCurrentConversationAction, ConversationCompletionAction, ConversationSummaryAction, CreateToolAction, RememberAction, UpdateKnowledgeAction
from db import Database
from dto import Message
from sendable import Sendable

class Intent():
    def __init__(self, descriptions:List[str], actions:List[Action]):
        self.descriptions = descriptions
        self.actions = actions
    def get_descriptions(self) -> List[str]:
        return self.descriptions
    def get_actions(self) -> List[Action]:
        return self.actions
class SubIntent():
    def __init__(self, descriptions:List[str], actions:List[Action]):
        self.descriptions = descriptions
        self.actions = actions
    def get_descriptions(self) -> List[str]:
        return self.descriptions
    def get_actions(self) -> List[Action]:
        return self.actions

IntentType = Union[TypeVar("Intent", bound=Intent), TypeVar("SubIntent", bound=SubIntent)]

class TopicChangeIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to change the topic.", "An implict request to discuss something unrelated to what we have been discussing."], [ChangeCurrentConversationAction(), UpdateKnowledgeAction(), ConversationCompletionAction(), ConversationSummaryAction()])

class NoOpIntent(Intent):
    def __init__(self):
        super().__init__(["None of the above."], [ConversationCompletionAction(), ConversationSummaryAction()])

class PleasantryIntent(Intent):
    def __init__(self):
        super().__init__(["Just a greeting, affirmation, platitude, or pleasantry and nothing more.", "A frieldly greeting or pleasantry."], NoOpIntent().get_actions())

class InquiryIntent(Intent):
    def __init__(self):
        super().__init__(["A question or comment, specifically about what just happened.", "A question or comment regarding what was just discussed.", "Something that was relevant to the conversation we have been having."], NoOpIntent().get_actions())

class RememberIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to remember a detail or a set of details.","An explicit request to keep something in mind or to note something for the future."], [RememberAction()])
        
class CreateToolIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to create a tool."], [CreateToolAction()])
