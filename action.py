from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
import json
from typing import List

import discord

@dataclass
class Action:
    name:str
    description:str
    @abstractmethod
    async def __call__(self, message : Message, database : Database, sendable : Sendable, tool_calls_results:List[dict[str,str]] = []) -> None:
        pass

class ConversationCompletionAction(Action):
    def __init__(self):
        super().__init__("Conversation Completion Action", "Complete the current conversation and send the completion.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable, tool_calls_results:List[dict[str,str]] = []) -> None:
        conversation = database.get_current_conversation(message.user)
        if conversation is None:
            conversation = Conversation.new_conversation()
        preferences = database.get_knowledge_base(message.user)
        if preferences is not None:
            preference_summary = "\n".join([k + ": " + str(v.value) + "(" + v.description + ")" for k, v in preferences.items()])
            conversation.set_system("preferences", "I have the following knowledge:\n" + preference_summary)
        if conversation.summary is not None:
            conversation.set_system("summary", "Here's a summary of the conversation so far:\n" + conversation.summary)
        conversation.add_user(message.text)
        if len(tool_calls_results) > 0:
            for tool_call_result in tool_calls_results:
                conversation.add_tool_call_result(tool_call_result)
        database.set_conversation(message.user, conversation)
        database.set_current_conversation(message.user, conversation)
        completion = await chatgpt.pipe_completion(conversation.get_conversation(), sendable)
        conversation.add_assistant(completion)
        database.set_conversation(message.user, conversation)

class ConversationSummaryAction(Action):
    def __init__(self):
        super().__init__("Conversation Summary Action", "Set a summary of the current conversation on it.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable, tool_calls_results:List[dict[str,str]] = []) -> None:
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
                if (msg["role"] == "assistant" or msg["role"] == "user" or msg["role"] == "function") and count < 2000:
                    compressed_conversation.append(msg)
                    count += len(str(msg))
                elif msg["role"] != "assistant" and msg["role"] != "user" and msg["role"] != "function":
                    compressed_conversation.append(msg)
                    count += len(str(msg))
            compressed_conversation.reverse()
            conversation.messages = compressed_conversation
        database.set_conversation(message.user, conversation)
                
class ConversationChangeException(Exception):
    pass
class ChangeCurrentConversationAction(Action):
    def __init__(self):
        super().__init__("Change Current Conversation Action", "Change the current conversation.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable, tool_calls_results:List[dict[str,str]] = []) -> None:
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
    async def __call__(self, message : Message, database : Database, sendable : Sendable, tool_calls_results:List[dict[str,str]] = []) -> None:
        #identify any tool creation requests
        for tool_call_result in tool_calls_results:
            if tool_call_result["name"] == "create_tool":
                tool_spec = tool_call_result["content"]
                definition = tool_call_result["tool"]
            await sendable.send(tool_spec, view=CreateToolButton(definition, database))
            
class UseToolAction(Action):
    def __init__(self):
        super().__init__("Use Tool Action", "An explicit request to use or invoke an existing tool or function.")
    async def __call__(self, message : Message, database : Database, sendable : Sendable, tool_calls_results:List[dict[str,str]] = []) -> None:
        return ConversationCompletionAction()(message, database, sendable, tool_calls_results)        

from sendable import Sendable
from db import Database
from dto import Conversation, Message, ToolDefinition
import chatgpt
