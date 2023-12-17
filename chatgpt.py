from __future__ import annotations
import logging
from typing import Any, List, Optional, Tuple, Type
from openai import OpenAI, AsyncOpenAI
import os
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from retry import retry
import yaml
from typing import TypeVar
import source_utils
from sendable import Sendable
from dto import Function, FunctionParameter, FunctionParameters, MessageClassification, Tool, ToolDefinition
import re
import json


T = TypeVar("T", bound=object)

client = OpenAI(api_key=os.getenv("OpenAIAPI"))
aclient = AsyncOpenAI(api_key=os.getenv("OpenAIAPI"))


# Create an instance of the SentimentIntensityAnalyzer object
analyzer = SentimentIntensityAnalyzer()

exact_engine = "gpt-4"
fast_engine="gpt-3.5-turbo"

@retry(tries=3, delay=3, backoff=2, logger=logging.getLogger(__name__))
async def get_completion(messages :list[dict[str,str]], model:str=exact_engine, temperature:float=0.5, exact=False, tools:List[ToolDefinition]=[]) -> str:
    if exact:
        model=exact_engine
    request = {"model":model, "messages":messages, "temperature":temperature}
    if tools is not None and len(tools) > 0:
        request["tools"] = tools
    response = client.chat.completions.create(**request)
    if response is None:
        raise Exception("No response from OpenAI")
    return response.choices[0].message.content, response.choices[0].message.tool_calls

async def pipe_completion(messages : list[dict[str,str]], sendable: Sendable, model:str=exact_engine, tempeature:float=0.5, exact=True) -> str:
    if not exact:
        model=fast_engine
    pipe, done = sendable.get_pipe()
    completion = ""
    
    async for chunk in await aclient.chat.completions.create(model=model,
    messages=messages,
    stream=True):
        content = json.loads(chunk.json())["choices"][0].get("delta", {}).get("content")
        if content is not None and content != "":
            await pipe(content)
            completion += content
        else:
            await done()
    return completion

def get_body(message : str) -> str:
    try:
        message = message.split('```')[1]
        if message.lower().startswith('yaml'):
            message = message[4:]
            message = message.strip()
            if message.startswith(">") and not message.startswith(">\n"):
                message = ">\n  " + message[1:]
        return message.strip()
    except:
        return message.strip()
    
async def extract_topic(message : str) -> str:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to extract a topic from a sentence for searching Wikipedia with. I will supply you with a sentence, and I want you to tell me, in quotes, a word or phrase suitible for searching Wikipedia with. Please supply only the singular thing to search in quotes. For example, if I say 'I want to search Wikipedia for the meaning of life', you should say 'meaning of life' and nothing else."},
        {"role":"user","content":"What is the topic being discussed here? \"" + message + "\" Please only supply the topic in quotes. Make sure to include the quotes and nothing else except the topic in quotes."}
    ]
    result, tool_calls = await get_completion(convo)
    return result.replace('"', '').replace("'", "").rstrip().lstrip()

async def summarize(conversation: str) -> str:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to extract information from a conversational text for integration into a knowledge base, and return only the summarized content as a list without making reference to the request. Please summarize the entirety of the following text as a list of key factual and conversational datapoints from the conversation. Please supply as many important details in the summary as you can, including descriptions or summaries of all provided examples, and return only the bulleted list of datapoints. Include nothing but the list in your reply. Don't use words like \"summary\" or \"prior conversations\" in your reply unless they are part of the data in the list itself. Please remember to summarize ALL of the text, even if there are large spaces between words or paragraphs."},
        {"role":"user","content":"What is a highly detailed summary of this content? \"" + conversation[:3800] + "\" Please only supply the summary in quotes. Make sure to include the quotes and nothing else except the summary in quotes."}
    ]
    result, tool_calls = await get_completion(convo)
    return result.replace('"', '').replace("'", "").rstrip().lstrip()

async def summarize_data(data: str) -> str:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to create detailed summaries of content. I will supply you with some content, and I want you to tell me, in quotes, a summary of the conversation. Please supply as many important details in the summary as you can."},
        {"role":"user","content":"What is a highly detailed summary of this content? \"" + data[:3800] + "\" Please only supply the summary in quotes. Make sure to include the quotes and nothing else except the summary in quotes."}
    ]
    result, tool_calls = await get_completion(convo)
    return result.replace('"', '').replace("'", "").rstrip().lstrip()

def is_positive(message : str) -> bool:
    scores = analyzer.polarity_scores(message)
    return scores['compound'] > 0

async def get_is_request_to_change_topics(context : str, user_input : str) -> bool:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to identify if a sententce is a request to to talk about something were already discussing, or a change in topics. I will supply you with a sentence, and I want you to tell me, in quotes, if this is a request to change topics or not. Please supply an explnation for your answer. For example, if I say 'Can we talk about my dog instead?', you should say 'yes because it's asking to talk about a dog instead of the current topic', but if I say something context free, or related to what i was previously discussing, you should say 'no its on topic' and nothing else."},
        {"role":"system","content":"Previously I was talking about: " + context},
        {"role":"user","content":"Is this an explicit or obvious request to change topics? \"" + user_input + "\""}
    ]
    result, tool_calls = await get_completion(convo)
    result = result.replace('"', '').replace("'", "").rstrip().lstrip()
    return is_positive(result)

async def get_new_or_existing_conversation(old_conversations : str, user_input : str):
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to identify if a question is related to a prior conversation, or if it is a new conversation. I will supply you with a conversation, and I want you to tell me, in quotes, if this is a new conversation or if it is related to a prior conversation. Please supply only the prior conversatyion in quotes, or say 'new conversation' if this is a new conversation. For example, if I say 'I want to know if this is a new conversation or related to a prior conversation', you should say 'new conversation' or 'The prior conversation about prior conversations.' and nothing else."},
        {"role":"system","content":"Here are the prior conversations:\n" + old_conversations},
        {"role":"user","content":"Is this a new conversation or related to a prior conversation? \"" + user_input + "\" Please only supply the prior conversation in quotes, or say 'new conversation' if this is a new conversation. Make sure to include the specific conversation number. I need the number, not the topic. For example, if I say 'I want to know if this is a new conversation or related to a prior conversation. Please give me the related conversation number, or 'new conversation' if this is a new conversation. Remember, I really want the number of the conversation, like 3 or 5."}
    ]
    result, tool_calls = await get_completion(convo)
    result = result.replace('"', '').replace("'", "").rstrip().lstrip()
    if "new conversation" in result.lower() and re.search(r"\d+", result) is None:
        return -1
    number = re.search(r"\d+", result)
    if number is None:
        return -1
    return int(number.group(0))

async def summarize_knowledge(conversation_summary: str) -> str:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to summarize a series of conversations into a knowledge base. I will supply you with a list of summaries of prior conversations we have had, and I want you to write a paragraph or three containing the key datapoints from all the conversations. Make sure to include key datapoints from all the conversations."},
        {"role":"system","content":"Here are the summaries of prior conversations:\n" + conversation_summary},
        {"role":"user","content":"What is the knowledge base of our prior conversations? Please write a paragraph or three containing the key datapoints from all the conversations. Make sure to include key datapoints from all the conversations."}
    ]
    result, tool_calls = await get_completion(convo)
    return result.replace('"', '').replace("'", "").rstrip().lstrip()

async def find_similar_conversations(conversations : str) -> Optional[Tuple[int, int]]:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to find similar conversations. I will supply you with a list of conversations, and I want you to tell me, in quotes, if there are any conversations that are discussing related topics. Please supply the conversation by number, for example, 'Conversations 2 and 4 are simiar, and 7 and 3 are similar.' and nothing else."},
        {"role":"system","content":"Here are the conversations in question:\n" + conversations},
        {"role":"user","content":"Is there any similar conversation that are discussing related topics? Please list the conversation by number, for example, 'Conversations 2 and 4 are simiar."}
    ]
    result, tool_calls = await get_completion(convo)
    result = result.replace('"', '').replace("'", "").rstrip().lstrip()
    #find 2 numbers
    numbers = re.findall(r"\d+", result)
    if len(numbers) < 2:
        return None
    return int(numbers[0]), int(numbers[1])

async def merge_conversations(conversation1 : str, conversation2 : str) -> list[dict[str,str]]:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to merge two conversations. I will supply you with two conversations, and I want you to make up a new conversation that merges the two conversations into a single conversation."},
        {"role":"user","content":"Here are the two conversations to merge:"},
        {"role":"user","content":"Conversation 1:\n```\n" + conversation1 + "\n```\n"},
        {"role":"user","content":"Conversation 2:\n```\n" + conversation2 + "\n```\n"},
        {"role":"user","content":"Please produce a new conversation that merges the two conversations into a single conversation."}
    ]
    result, tool_calls = await get_completion(convo)
    result = result.replace('"', '').replace("'", "").rstrip().lstrip()
    result = [ {"role":x[0].strip().lower(), "content":x[1].strip()} for x in [ x.split(":") for x in result.split("\n") if x.strip() != "" and ":" in x and ("assistant" in x.lower() or "user" in x.lower() or "system" in x.lower()) ] ]
    return result

async def extract_urls(query : str) -> List[dict[str,str]]:
    convo = [
        {"role":"system","content":"You are a helpful ai assistant who knows how to given a message, guess the url i should be querying, and make a good query for that specific url as to what I should search it for. You will take the message i give you, and you will tell me what url i should query, and what query I should search that url for given that message. Remember to take into account the nature of the website when answering the question."},
        {"role":"user","content":f"Your first example is, \"{query}\" What is the url of the company or brand mentioned there, or what urls might be relevant what is being discussed, ignoring any questions or statements that don't make sense, and what should i query them for specifically in quotes? I just want the url and the query, please dont mention what I should not search for or the reasoning. Do NOT put the url in quotes, as that will only confuse me. Format your response in yaml, with an array of NAME, URL and QUERY pairs."}         
    ]
    result = (await get_completion(convo)).replace('"', '').replace("'", "").rstrip().lstrip()
    
    try:
        result = result.split("```")[1]
        if result.lower().startswith("yaml"):
            result = result[4:]
        result = yaml.load(result, Loader=yaml.Loader)
        output = []
        for i in result:
            out = {"context":query}
            for k, v in i.items():
                value = v.replace('"', '').replace("'", "").rstrip().lstrip().replace("\\", "")
                if "site:" in value:
                    value = value[:value.index("site:")].strip()
                out[k.lower()] = value
            output.append(out)
        return output
    except:
        return []
    
async def async_summarize_knowledge(conversation_summary: str, pipe, done) -> str:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to summarize a series of conversations into a knowledge base. I will supply you with a list of summaries of prior conversations we have had, and I want you to write a paragraph or three containing the key datapoints from all the conversations. Make sure to include key datapoints from all the conversations."},
        {"role":"system","content":"Here are the summaries of prior conversations:\n" + conversation_summary},
        {"role":"user","content":"What is the knowledge base of our prior conversations? Please write a paragraph or three containing the key datapoints from all the conversations. Make sure to include key datapoints from all the conversations."}
    ]
    await async_send_to_ChatGPT(convo, pipe, done)
    try:
        result = get_body(result)
        result = yaml.load(result, Loader=yaml.Loader)
        out = {"context":convo}
        for k, v in result.items():
            value = v.replace('"', '').replace("'", "").rstrip().lstrip().replace("\\", "")
            if "site:" in value:
                value = value[:value.index("site:")].strip()
            out[k.lower()] = value
        return out
    except:
        return None

async def classify_intent(categories : List[str], query : str, context: Optional[str] = None, tools : List[ToolDefinition] = []) -> Optional[List[str]]:
    convo = [ 
        {"role":"system", "content": "You are a classification agent that knows how to classify text as being related or similar or losely described by one or more of the options listed, or \"None of the above.\" if it doesnt match any of the listed options."},
        {"role":"system", "content":"For example you would reply with:\n```yaml\n- This is the first option that was chosen.\n- This is the second option chosen.\n```\n Assuming those two options are similar or related. Make sure you block quote the output as YAML as an array. You should avoid \"None of the above.\" if the answer is in any way related to another answer."},
        {"role":"user", "content": "Here's the list of possible options:\n```yaml\n" + "\n".join(f"- {j}" for j in categories) + "\n```"}]
    if context is not None:
        convo += [{"role": "user", "content": "For context: " + context}]
    convo += [{"role": "user", "content": f'Please classify this message as one or more of the above options listed:\n"{query}"'}]
    result, tool_calls = await get_completion(convo, temperature=0, tools=tools)
    if result is None:
        return None, tool_calls
    try:
        result = get_body(result)
        output = []
        result = yaml.load(result, Loader=yaml.Loader)
        if isinstance(result, str):
            result = [result]
        for r in result:
            for c in categories:
                if c.lower() in r.lower():
                    output.append(c)
        return output, tool_calls if len(output) > 0 else None, tool_calls
    except:
        return None, None

async def extract_preferences(message) -> dict[str,str]:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant capable of taking a message and extracting a key/value set of preferences and giving the value back as YAML."},
        {"role":"system","content":"""For example, if I were to say to you, "Remember to always call me Sir, and my Birthday is 10/10/1990" you would say:
```yaml
"My name": "Sir"
"My birthday": "10/10/1990"
"Always call me": "Sir"
```"""},
        {"role":"user","content":"Please convert the following into a YAML map of preferences: " + message}
    ]
    result = await get_completion(convo)
    try:
        result = get_body(result)
        result = yaml.load(result, Loader=yaml.Loader)
        return result
    except:
        return {}
    
async def remove_change_of_topic(message : str) -> str:
    convo = [
        {"role":"system", "content":"You are a helpful AI assistant who knows how to take a a statement or request to discuss a specific topic or change a topic, and reword the request to eliminate the request to change the topic and any mentions of \"instead\", leaving only the subject as a new request or statement."},
        {"role":"system", "content":"For example, if I say to you, \"Can we discuss Queen Elizabeth instead of talking about this? Did she die according to Wikipedia?\", you would reply with,\n```yaml\nDid Queen Elizabeth die accoring to Wikipedia?```\n and nothing else. If it doesnt mention a topic change just quote it directly as your reply. Output the new request as a YAML string."},
        {"role":"user", "content":"Please reformat this to not include the mention of change of topic: \"" + message + "\". Remember to output the result as a YAML string, and don't use words like \"instead\" in your reply."}
    ]
    result = await get_completion(convo)
    try:
        return get_body(result)
    except:
        return message
        
async def get_git_repo_and_options(message) -> dict[str,str]:
    convo = [
        {"role":"system","content":"You are a helpful AI assistant who knows how to extract git urls from requests to do things with git, as well as the associated git command and options required to pull off the request, and return the results as a blockquoted yaml map."},
        {"role":"system","content":"""For example, if i said, "Please clone the stable branch of https://github.com/Significant-Gravitas/Auto-GPT" you would reply:
```yaml
repo: Auto-GPT
executable: git
command: clone
url: https://github.com/Significant-Gravitas/Auto-GPT
options: --branch stable
```
"""},
        {"role":"user","content":"Please convert the following into a YAML map: " + message}
    ]
    result = (await get_completion(convo))
    try:
        result = result.split("```")[1]
        if result.lower().startswith("yaml"):
            result = result[4:]
        result = yaml.load(result, Loader=yaml.Loader)
        return result
    except:
        return {}
    

async def get_structured_classification(message: str, cls: Type[T], constraints: dict[str, List[str]] = {}, additional_context: str = None, tools:List[dict[str,Any]] = []) -> List[T]:
    con = "".join((f"The \"{k}\" parameter MUST be one of the following values:\n```yaml\n"
                   + "\n".join(f"- {x}" for x in v)
                   + "\n```\n")
                  for k, v in constraints.items())
    convo = [{"role": "system", "content": "You are a helpful AI assistant who knows how to extract structured data from a message or messages, and return the results as a blockquoted yaml array of " + cls.__name__ + " object shaped dictionaries, one for each part of what is said."}]
    convo += [{"role": "system", "content": "The message may contain multiple requests, in which case you should return an object for each portion of the message. For example, if the request was to grab a web page, and summarize it, that would be a Scrape the Web object, followed by a Summarize object. You would return an object for each intent, with the appropriate data for each."}]
    convo += [{"role":"system", "content": "It's very important that you break up complex requests into smaller requests, and return an object for each request. It is necessary to use step by step logic to describe the steps involved and break up the steps into smaller, matchable contraints. For example, if the request is 'Are there more Jews that speak Hewbew than Arabic?', and one of the options is to search the web, or to summarize, you would generate an object to search the web for the number of Jews who are Arabic speakers, and another object to search the web for the number of Jews who are Hebrew speakers, and another object to summarize the data. You would return an object for each of the three requests. However if there's a computational engine available, you might just return a single object to query the computational engine for the answer, and not return any objects for the other two requests. You should always return an object for each request, and you should always break up complex requests into smaller requests where appropriate, matching the best intention of the request to the best available set of constraints to satify the request in the most accurate and optimal way possible."}]
    convo += [{"role":"system", "content": "You should also look for opportunities to invoke tool functions to satisfy requests, and if invoking a tool, simply classify the intent as being a pleasantry."}]
    convo += [{"role":"system","content": f"Here are the Python classes that the YAML object must deserialize to:\n```python\n{source_utils.get_source(cls)}\n```"}]
    if len(con) > 0:
        convo += [{"role": "system", "content": con}]
    if additional_context is not None:
        convo += [{"role": "system", "content": "Here's some additional context for the request. Be sure and include relevant information from here when additional information can be synthasized, for example relevant API keys or other secrets: " + additional_context}]
    convo += [{"role": "system", "content": "Be sure you escape any inner quotes in strings. Don't forget!!!"}]
    convo += [{"role": "user", "content": f'Be sure you escape any inner quotes in strings. Don\'t forget!!! Please convert the following into a blockquoted YAML dictionary or array of dictionaries that follows the above constraints: "{message}"\n'}]
    result, tool_calls = await get_completion(convo, tools=tools)
    if result is None:
        return [], tool_calls
    result = get_body(result)
    result = source_utils.from_yaml(result, cls)
    if not isinstance(result, list):
        result = [result]
    return result, tool_calls

async def get_tool_spec(description: str) -> ToolDefinition:
    convo = [{"role": "system", "content": "You are a helpful AI assistant who knows how to take desciptions of tools and convert them into a YAML map of tool specifications."}]
    functionParameterSource = '\n'.join(["   " + line for line in source_utils.get_source(FunctionParameter).split("\n")])
    functionParametersSource = '\n'.join(["   " + line for line in source_utils.get_source(FunctionParameters).split("\n")])
    functionSource = '\n'.join(["   " + line for line in source_utils.get_source(Function).split("\n")])
    toolSource = '\n'.join(["   " + line for line in source_utils.get_source(Tool).split("\n")])
    toolDefinitionSource = '\n'.join(["   " + line for line in source_utils.get_source(ToolDefinition).split("\n")])

    convo += [{"role": "user", "content": '''I am developing a bot in Python that integrates with the ChatGPT API. This bot uses a set of Python classes to represent tools that can be invoked via the chat completion api. The classes are as follows:

1. **`FunctionParameter`**: Defines a parameter for a function, including `type` (data type of the parameter) and `description` (what the parameter is for).
   ```python
''' + functionParameterSource + '''
   ```

2. **`FunctionParameters`**: Details the parameters a function takes, including `type` (data type, e.g., 'Dict'), `properties` (dictionary mapping names to `FunctionParameter` instances), and `required` (list of required parameter names).
   ```python
''' + functionParametersSource + '''
   ```

3. **`Function`**: Describes a function that the tool can call, including `name`, `description`, and `parameters` (an instance of `FunctionParameters`).
   ```python
''' + functionSource + '''
   ```

4. **`Tool`**: Represents a tool that can be invoked, containing `type` and `function` (an instance of `Function`).
   ```python
''' + toolSource + '''
   ```

I am now looking to create a specific tool. The description of the tool is as follows:
```
''' + description + '''
```

**Important Notes:**
- The parameters defined in the `Tool` class unioned with the static_parameters must have a direct and invariant relationship with the parameters used in the Python code for the tool's implementation.
- All output from the Python code be print()-ed AND returned as a string. If additional files are generated, they should also be placed in the `/` directory, and their file names should be print()-ed and returned as a line break seperated string. This is particularly important for the tool's execution within a Dockerized environment, ensuring that output data can be easily retrieved and managed.
- If the relationship between the `Tool` parameters, the Python implementation parameters, the static_parameters, and the output handling is not immediately obvious, please ask for additional details to ensure accuracy.

Based on this description, please provide the following:
1. A `Tool` class instance representing this tool. The 'type' fields use Javascript typing, so that needs to be 'string' not 'str' in the parameter descriptions.
2. Python code for the tool implementation with a function defined ensuring that the parameters in the `Tool` class PLUS the static values are directly and invariantly represented in the Python function, and that all output either print()-ed, or written to disk and the file names are print()-ed, with any additional files placed in `/`. The python should just define the function, not invoke it. This MUST be a string, the python variable of the ToolDescription class.
3. A description of the tool and how to use it, including any relevant schemas for the input and output data.
4. Any static parameters for the invocation such as api keys or other static parameters that are NOT part of the function signature. They MUST be part of the python function parameters, but MUST NOT be in the Tool definition.
5. A unique and descriptive name and a highly descriptive type for the Tool (type on Tool), knowing that the names and types in the system need to be unique and highly descriptive of what they do. The name and the type should be the same and should be highly descriptive (good: "Specific Program Search Tool With API Key", bad: "QueryTool").
6. A unit test, or example invocation, with all the parameters supplied hard coded, and an assertion that the output is correct. This is to ensure that the tool works as expected. The unit test should be a string, the example_invocation variable of the ToolDescription class.

static_parameters MUST be in the Python function parameters but MUST NOT be in the Tool FunctionParameters. static_parameters MUST NOT be default parameters in the python. They are used to hold secrets like api keys and MUST be part of the python function signature and MUST be excluded from the Tool FunctionParameters.

Use the following @dataclass to represent your output, and blockquote it in YAML as a single serialized ToolDescription object:
```python
''' + toolDefinitionSource + '''
```

Do NOT discuss the solution. JUST output YAML for a ToolDescription object I can deserialize. You don't need to redefine the classes provided either. Do NOT include the Tool classes in the python. Just give me a serialized ToolDescription with the Tool, and the python for the tool implementation. Again, DO NOT repeat the tool and function and associated dataclasses in the output. Make sure the python is a string in the python variale of the ToolDescription class. Do NOT include class definitions or type hints in the YAML.
'''}]
    result, tool_calls = await get_completion(convo)
    result = get_body(result)
    result = source_utils.from_yaml(result, ToolDefinition)
    return result