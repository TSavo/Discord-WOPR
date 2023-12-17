from __future__ import annotations
from abc import abstractmethod
from typing import Any, Dict
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncGenerator, List, Optional, Union
from uuid import uuid4
import discord

@dataclass
class Message:
    user:User
    text:str
    channel:Optional[Channel]
    guild:Optional[Guild]
    followup:List[str]
    datetime:datetime
    discord_message_id:int
    id:str = str(uuid4().hex)
    classifications:Optional[List[MessageClassification]] = None
    @staticmethod
    def from_message(message : discord.Message) -> Message:
        if isinstance(message.author, discord.User):
            #cast the author to a discord.user
            user = User.from_discord_user(message.author)
            return Message(user,
                       message.content,
                       Channel.from_discord_channel(message.channel), 
                       Guild.from_discord_guild(message.guild),
                       [],
                       message.created_at,
                       message.id)
        elif isinstance(message.author, discord.Member):
            user = User.from_discord_user(message.author._user)
            return Message(user,
                       message.content,
                       Channel.from_discord_channel(message.channel), 
                       Guild.from_discord_guild(message.guild),
                       [],
                       message.created_at,
                       message.id)
        else:
            raise NotImplementedError("Not implemented")
        

@dataclass
class Channel:
    id:str
    @staticmethod
    def from_discord_channel(channel : discord.abc.MessageableChannel) -> Channel:
        return Channel(
            id=str(channel.id),
        )
    def get_discord_channel(self, discord_client:discord.Client) -> Optional[Union[discord.abc.PrivateChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel, discord.TextChannel, discord.CategoryChannel]]:
        return discord_client.get_channel(int(self.id))
@dataclass
class Guild:
    id:str
    name:str
    @staticmethod
    def from_discord_guild(guild:Optional[discord.Guild]) -> Optional[Guild]:
        if guild is None:
            return None
        return Guild(
            id=str(guild.id),
            name=guild.name
        )
    def get_discord_guild(self, discord_client:discord.Client) -> Optional[discord.Guild]:
        return discord_client.get_guild(int(self.id))
@dataclass
class User:
    id:str
    name:str
    display_name:str
    discriminator:str
    avatar:Optional[discord.Asset]
    bot:bool
    system:bool
    @staticmethod
    def from_discord_user(user:discord.User) -> User:
        return User(
            id=str(user.id),
            name=user.name,
            display_name=user.display_name,
            discriminator=user.discriminator,
            avatar=user.avatar,
            bot=user.bot,
            system=user.system
        )
    def get_discord_user(self, discord_client:discord.Client) -> Optional[discord.User]:
        return discord_client.get_user(int(self.id))
    
@dataclass
class Conversation:
    system:dict[str,str]
    messages:List[dict[str, str]]
    summary:str
    id:str = str(uuid4().hex)
    @staticmethod
    def new_conversation(system:str = "You are a helpful AI assistant.") -> Conversation:
        return Conversation({"system":system},[], "The start of a brand new conversation")
    def set_system(self, system : str, message : str = "") -> None:
        self.system[system] = message
    def delete_system(self, system : str) -> None:
        del self.system[system]
    def get_conversation(self) -> List[dict[str, str]]:
        messages : List[dict[str,str]] = [{"role":"assistant","content":value} for value in self.system.values()]
        messages.extend(self.messages)
        copy : List[dict[str,str]] = []
        for x in range(0, len(messages)):
            copy.append(messages[x])
        return copy
    def add_user(self, user : str) -> None:
        if user is not None:
            self.messages.append({"role":"user","content":user})
    def add_assistant(self, assistant : str) -> None:
        if assistant is not None:
            self.messages.append({"role":"assistant","content":assistant})
    def delete_last_message(self) -> None:
        self.messages.pop()
    def add_tool_call(self, tool_call) -> None:
        self.messages.append({"role":"tool_call", "content":tool_call})
    def add_tool_call_result(self, tool_call_result : dict[str,str]) -> None:
        self.messages.append({"role":tool_call_result["role"], "name":tool_call_result["name"], "content":tool_call_result["content"]})
    def __str__(self) -> str:
        convo = ""
        for message in self.get_conversation():
            convo += message["role"] + " " + message.get("name", "") + ": " + message["content"] + "\n"
        return convo

@dataclass
class UserValues:
    user:User
    values:dict[str,str]
    def get_value(self, key : str) -> str:
        return self.values[key]
    def set_value(self, key : str, value : str) -> None:
        self.values[key] = value
    def delete_value(self, key : str) -> None:
        del self.values[key]
    def __str__(self) -> str:
        value = ""
        for key in self.values:
            value += key + ": " + self.values[key] + "\n"
        return value

class UserSettings(UserValues):
    pass

class UserPreferences(UserValues):
    pass

@dataclass
class UserConversation:
    user_id:str
    conversation:Conversation
    conversation_id:str
@dataclass
class UserCurrentConversation:
    user_id:str
    conversation_id:str

@dataclass
class DataSource:
    id:str
    name:str
    url:str
    roles:List[str]
    @abstractmethod
    async def query(self, query : str, context:Optional[dict[str,str]]) -> AsyncGenerator[str, None]:
        pass

@dataclass
class ExternalDataSource(DataSource):
    endpoints:List[Endpoint]
    
@dataclass
class QueryParam:
    name:str
    required:bool
    default:Optional[str]
    parameter_type:str
    roles:List[str]

@dataclass
class Endpoint:
    name: str
    path: str
    query_params: List[QueryParam]
    response_format: str
    method: str
    roles: List[str]


@dataclass
class Tool:
    type: str
    function: Function

import dataclasses
@dataclass
class MessageClassification:
  original_message:str #The original message from the user
  message_part:str #The part of the message that is classified
  intent:Optional[str] = None #The intent of the message part
  categories:List[str] = dataclasses.field(default_factory=list) #The categories of the message part
  reply:Optional[str] = None #The reply to the message part
  justifications_for_reply:List[Justification] = dataclasses.field(default_factory=list) #The justifications for the reply
  follow_up_items:List[MessageClassification] = dataclasses.field(default_factory=list) #The follow up items for the message part
  function:Optional[str] = None #The function to call for the message part
  function_parameters:Optional[dict[str,str]] = None #The parameters to call the function with

@dataclass
class Justification:
    subject:Optional[str] = None
    object:Optional[str] = None
    intent:Optional[str] = None
    action:Optional[str] = None
    description:Optional[str] = None
    
@dataclass
class FunctionParameterValue:
    type:str
    value:Any
@dataclass
class FunctionParameter:
    type: str
    description: str

@dataclass
class FunctionParameters:
    type: str
    properties: Dict[str, FunctionParameter]
    required: List[str]

@dataclass
class Function:
    name: str
    description: str
    parameters: FunctionParameters

@dataclass
class ToolDefinition:
    name: str = ""
    description: str = "" #Description of the tool
    static_parameters: dict[str, FunctionParameterValue] = dataclasses.field(default_factory=dict[str, FunctionParameterValue]) #Static parameters for the tool
    tool: Tool = dataclasses.field(default_factory=Tool) #The tool itself
    pip_packages: List[str] = dataclasses.field(default_factory=list[str]) #The pip packages required for the tool
    python: str = "" #The python code for the tool
    example_invocation: str = "" #An example invocation of the tool that has all the parameters supplied and asserts the results are correct. This will be appended to the code and run to verify the tool works. Do not create any unnecessary objects, just invoke the function with the parameters then assert result.txt has the correct value.
    
    def getCode(self, args) -> str:
        code = self.python
        code += "\n"
        static_args = {static_parameter: self.static_parameters[static_parameter].value for static_parameter in self.static_parameters}
        code += "args = " + str(static_args) + "\n"    
        code += "args.update(" + str(args) + ")\n"
        code += self.tool.function.name + "(**args)\n"
        return code
    
    def getExampleInvocation(self) -> str:
        return self.python + "\n" + self.example_invocation + "\n"
    

@dataclass
class Knowledge:
    value:str
    description:str