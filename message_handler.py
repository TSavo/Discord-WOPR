from dataclasses import dataclass, asdict
import logging
from typing import Any, List, Protocol
from action import ConversationChangeException, ConversationCompletionAction
from db import Database, UserUnion
import docker_runner
from dto import Function, FunctionParameter, FunctionParameters, Knowledge, Message, Knowledge, Tool, ToolDefinition
from intent import CreateToolIntent, InquiryIntent, Intent, RememberIntent, TopicChangeIntent
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

    async def create_tool(self, description:str) -> ToolDefinition:
        definition = await chatgpt.get_tool_spec(description)
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
        return tool_spec, definition  

    class ToolCall:
        def __init__(self, function:str, function_parameters:dict[str, Any]):
            self.function = function
            self.function_parameters = function_parameters
            
    async def run_tools(self, tools:List[ToolDefinition], tool_calls: List[ToolCall], message : Message, database : Database, sendable : Sendable) -> List[dict[str, Any]]:
        tool_call_results = []
        intents = []
        for tool_call in tool_calls:
            if tool_call.function == "create_tool":
                #create the tool
                tool_spec, definition = await self.create_tool(tool_call.function_parameters["description"])
                tool_call_results.append({"role": "function", "name": tool_call.function, "content": tool_spec, "tool": definition})
                intents.append(CreateToolIntent())
                logging.info(f"Created tool {definition.name}")
            elif tool_call.function == "remember":
                key = tool_call.function_parameters["knowledge_key"]
                description = tool_call.function_parameters["description"]
                value = tool_call.function_parameters["value"]
                database.set_knowledge(message.user, key, Knowledge(description, value))
                tool_call_results.append({"role": "function", "name": tool_call.function, "content": tool_call.function_parameters["appropriate_response"]})
                intents.append(InquiryIntent())
                logging.info(f"Remembered {key} as {value}")
            elif tool_call.function == "forget":
                key = tool_call.function_parameters["knowledge_key"]
                database.delete_knowledge(message.user, key)
                tool_call_results.append({"role": "function", "name": tool_call.function, "content": tool_call.function_parameters["appropriate_response"]})
                intents.append(InquiryIntent())
                logging.info(f"Forgot {key}")
            else:
                for tool in tools:
                    if tool.tool.function.name == tool_call.function:
                        result = await docker_runner.run_python_script(tool.getCode(tool_call.function_parameters), tool.pip_packages)
                        tool_call_results.append({"role": "function", "name": tool_call.function, "content": result})
                        logging.info(f"Tool call {tool_call.function} returned {result}")
                intents.append(InquiryIntent())
        return tool_call_results, intents
            
        
    async def handle_message(self, message: Message, database: Database, sendable: Sendable):
        if str(message.user.id) in self.custom_handlers:
            await self.custom_handlers[str(message.user.id)](message, database, sendable)
            del self.custom_handlers[str(message.user.id)]
            return
        logging.info("Handling message: " + str(message))
        #Try and do any tool invocations
        tools = database.get_tools(message.user)
        create_tool_tool = ToolDefinition("Create Tool", "Create a tool", tool = Tool("object", Function("create_tool", "This tool creates tools that can be invoked via chat completions. When the user asks for a new tool or function, this is the function to call to make that tool with. You shoul pass in a plain text description of exactly what that tool or function should do as a string including any static parameters that the tool might have, ideally what the user asked for, and any additional information that can be gleaned from the conversation that might be relevant to the creation of that tool. For example, if the conversation was about Wolfram Alpha, and then later the user asked for a tool to make a query against it, and specified their API key as XXXXXXX, the query for this tool would be \"Create a tool to query Wolfram Alpha and return the result. The website for Wolfram Alpha is 'https://wolframalpha.com'. Use this API key as a static value: 'XXXXXXX'.\"", FunctionParameters("object", {"description": FunctionParameter("string", "A plain text description of the tool to create including all the details necessary to create the tool including any static parameters.")}, ["description"]))))
        remember_tool = ToolDefinition("Remember Tool", "Remember something for later", tool = Tool("object", Function("remember", "This tool remembers something for later. It requires a unique key, a plain text description of what is being stored, and the actual value itself. For example, if the user said \"Remember my API key for Wolfram Alpha is XXXXXXX\", the key would be \"wolfram_alpha_api_key\", the description would be \"API key for Wolfram Alpha\", and the value would be \"XXXXXXX\".", FunctionParameters("object", {"knowledge_key": FunctionParameter("string", "A unique key for the knowledge to be stored."), "description": FunctionParameter("string", "A plain text description of the knowledge to be stored. This is meta-data for the value, like Wolfram Alpha API Key."), "value": FunctionParameter("string", "The actual knowledge to be stored."), "appropriate_response": FunctionParameter("string", "An appropriate response to the user after the knowledge has been stored.")}, ["knowledge_key", "description", "value", "appropriate_response"]))))
        forget_tool = ToolDefinition("Forget Tool", "Forget something", tool = Tool("object", Function("forget", "This tool forgets something that was previously remembered. It requires a unique key for the knowledge to be forgotten. For example, if the user said \"Forget my API key for Wolfram Alpha\", the key would be \"wolfram_alpha_api_key\".", FunctionParameters("object", {"knowledge_key": FunctionParameter("string", "A unique key for the knowledge to be forgotten.")}, ["knowledge_key"]))))
        tools.append(create_tool_tool)
        tools.append(remember_tool)
        tools.append(forget_tool)
        tool_specs = [{"type":"function", "function":asdict(tool.tool.function)} for tool in tools]
        logging.debug("Tool specs: " + str([tool.name for tool in tools]))
        tool_call_results = []
        intents, tool_calls, classifications = await self.intent_classifier.classify_intent(message, Intent.__subclasses__(), database, tools=tool_specs)
        my_tool_calls = []
        if classifications is not None:
            #check for tools
            for classification in classifications:
                if classification.function is not None:
                    classification.function = classification.function.replace("functions.", "")
                    #locate the tool
                    logging.info("Tool call: " + str(classification.function) + " " + str(classification.function_parameters))
                    my_tool_calls.append(self.ToolCall(classification.function, classification.function_parameters))
        if tool_calls is not None:
            for tool_call in tool_calls:
                tool_call.function.name = tool_call.function.name.replace("functions.", "")
                logging.info("Tool call: " + str(tool_call.function.name) + " " + str(tool_call.function.arguments))
                my_tool_calls.append(self.ToolCall(tool_call.function.name, tool_call.function.arguments))
        tool_call_results, more_intents = await self.run_tools(tools, my_tool_calls, message, database, sendable)
        if intents is None or len(intents) == 0:
            intents = more_intents
        while(len(intents) > 0): #No for loop here, because we might change state in the middle of the loop
            intent = intents.pop(0)
            logging.info("Handling intent: " + str(intent))
            actions = intent.get_actions()
            while(len(actions) > 0): #No for loop here, because we might change state in the middle of the loop
                action = actions.pop(0) 
                logging.info("Handling action: " + str(action))
                try:
                    await action(message, database, sendable, tool_call_results)
                except ConversationChangeException:
                    message.text = await chatgpt.remove_change_of_topic(message.text)
                    await self.handle_message(message, database, sendable)
                    return
