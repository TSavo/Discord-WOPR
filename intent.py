from abc import abstractmethod
from typing import List, TypeVar, Union
from action import Action, ChangeCurrentConversationAction, ConversationCompletionAction, ConversationSummaryAction, CreateToolAction
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
        super().__init__(["An explicit request to change the topic.", "An implict request to discuss something unrelated to what we have been discussing."], [ChangeCurrentConversationAction(), ConversationCompletionAction(), ConversationSummaryAction()])

class NoOpIntent(Intent):
    def __init__(self):
        super().__init__(["None of the above."], [ConversationCompletionAction(), ConversationSummaryAction()])

class PleasantryIntent(Intent):
    def __init__(self):
        super().__init__(["Just a greeting, affirmation, platitude, or pleasantry and nothing more.", "A frieldly greeting or pleasantry."], NoOpIntent().get_actions())

class InquiryIntent(Intent):
    def __init__(self):
        super().__init__(["A question or comment, specifically about what just happened.", "A question or comment regarding what was just discussed.", "Something that was relevant to the conversation we have been having.", "A question regarding what has already been discussed in the current conversation that does not require a tool or function call."], NoOpIntent().get_actions())

class RememberIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to remember a detail or a set of details.","An explicit request to keep something in mind or to note something for the future."], NoOpIntent().get_actions())

class ForgetIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to forget a detail or a set of details.","An explicit request to forget something."], NoOpIntent().get_actions())

class CreateToolIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to create a tool."], [CreateToolAction()])

class UseToolIntent(Intent):
    def __init__(self):
        super().__init__(["An explicit request to use or invoke an existing tool or function.", "A request that can be best satisfied by invoking a tool or function.", "Specific instructions that can be satisfied by invoking a tool or function."], NoOpIntent().get_actions())
