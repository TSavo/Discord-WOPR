from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import List

import discord

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
        preferences = database.get_preferences(message.user)
        if preferences is not None:
            preference_summary = "\n".join([k + ": " + str(v) for k, v in preferences.items()])
            conversation.set_system("preferences", "I have the following preferences:\n" + preference_summary)
        if conversation.summary is not None:
            conversation.set_system("summary", "Here's a summary of the conversation so far:\n" + conversation.summary)
        if database.get_knowledge(message.user) is not None:
            conversation.set_system("knowledge", "Here's some background knowledge I have:\n" + database.get_knowledge(message.user))
        conversation.add_user(message.text)
        database.set_conversation(message.user, conversation)
        completion = await chatgpt.pipe_completion(conversation.get_conversation(), sendable)
        conversation.add_assistant(completion)
        database.set_conversation(message.user, conversation)
class ConversationSummaryAction(Action):
    def __init__(self):
        super().__init__("Conversation Summary Action", "Set a summary of the current conversation on it.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        conversation = database.get_current_conversation(message.user)
        if conversation is None:
            return
        conversation.summary = await chatgpt.summarize("Summary: " + conversation.summary + "\n" + str(conversation))
        #compress the conversation into the last 50 or less "role":"assistant"/"user" messages
        #work from the tail to the head, copying everything that's not "role":"assistant"/"user" and the last 50 "role":"assistant"/"user" messages
        if len(str(conversation)) > 2500:
            conversation_list = conversation.messages[::-1]
            compressed_conversation = []
            count = 0
            conversation_list.reverse()
            for msg in conversation_list:
                if (msg["role"] == "assistant" or msg["role"] == "user") and count < 2000:
                    compressed_conversation.append(msg)
                    count += len(str(msg))
                elif msg["role"] != "assistant" and msg["role"] != "user":
                    compressed_conversation.append(msg)
                    count += len(str(msg))
            compressed_conversation.reverse()
            conversation.messages = compressed_conversation
        database.set_conversation(message.user, conversation)
        
class UpdateKnowledgeAction(Action):
    def __init__(self):
        super().__init__("Update Knowledge Action", "Update the knowledge base of the user.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        conversations = database.get_conversations(message.user)
        summaries = ""
        for i, convo in enumerate(conversations, start=0):
            summaries += f"{i}. {convo.summary}\n"
        knowledge = await chatgpt.summarize_knowledge(summaries)
        database.set_knowledge(message.user, knowledge)
        
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
        conversation_index = await chatgpt.get_new_or_existing_conversation(summaries, message.text)
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
@dataclass
class RememberRequest():
    knowledge_key:str
    thing_to_remember:str
    appropiate_response:str
    def __str__(self):
        return f"RememberRequest({self.knowledge_key}, {self.thing_to_remember}, {self.appropiate_response})"
    def __repr__(self):
        return str(self)
    def __eq__(self, other):
        return self.knowledge_key == other.knowledge_key and self.thing_to_remember == other.thing_to_remember and self.appropiate_response == other.appropiate_response
    def __hash__(self):
        return hash((self.knowledge_key, self.thing_to_remember, self.appropiate_response))
    
class RememberAction(Action):
    def __init__(self): 
        super().__init__("Remember Action", "An explicit request to remember something or keep something in mind for later.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        request = await chatgpt.get_structured_classification(message.text, RememberRequest)
        if request is None:
            await sendable.send("I don't understand what you're asking me to remember.")
            return
        if not isinstance(request, list):
            request = [request]
        for r in request:
            database.set_preference(message.user, r.knowledge_key, r.thing_to_remember)
            await sendable.send(f"{r.appropiate_response}")
        

class CreateToolButton(discord.ui.View): # Create a class called MyView that subclasses discord.ui.View
    def __init__(self, tool_spec :ToolDefinition, database : Database):
        super().__init__()
        self.tool_spec = tool_spec
        self.database = database
    @discord.ui.button(label="Create this tool.", style=discord.ButtonStyle.primary)
    async def button_callback(self, interaction, button):
        await interaction.response.send_message("Creating the tool.")
        self.database.add_tool(interaction.user, self.tool_spec)
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_callback(self, interaction, button):
        await interaction.delete_original_response()
    
            
class CreateToolAction(Action):
    def __init__(self):
        super().__init__("Create Tool Action", "An explicit request to create a tool.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable) -> None:
        definition = await chatgpt.get_tool_spec(message.text)
        if definition is None:
            await sendable.send("I don't understand what you're asking me to create.")
            return
        #Convert the tool spec into a user friendly message
        tool_spec = ""
        tool_spec += f"Tool Name: {definition.name}\n"
        tool_spec += f"Tool Description: {definition.description}\n"
        tool_spec += f"Tool Function: {definition.tool.function.name}("
        for parameter in definition.tool.function.parameters.properties:
            tool_spec += f"{parameter}: {definition.tool.function.parameters.properties[parameter].type}, "
        tool_spec = tool_spec[:-2] + ")\n"
        if len(definition.static_parameters) > 0:
            tool_spec += f"Tool Static Parameters:\n"
            for name in definition.static_parameters:
                tool_spec += f"  {name}: {definition.static_parameters[name].value} ({definition.static_parameters[name].type})\n"
        tool_spec += f"Tool PIP Dependencies: "
        for dependency in definition.pip_packages:
            tool_spec += f"{dependency}, "
        tool_spec = tool_spec[:-2] + "\n"
        tool_spec += f"Tool Code:\n```python\n{definition.python}\n```\n"
        tool_spec += f"Tool Example Invocation:\n```python\n{definition.example_invocation}\n```\n"
        
        #await sendable.send(tool_spec)
        #send the tool spec to the user, then attach a button to the message that allows the user to create the tool
        await sendable.send(tool_spec, view=CreateToolButton(tool_spec, database))
        

from sendable import Sendable
from db import Database
from dto import Conversation, Message, ToolDefinition
import chatgpt
