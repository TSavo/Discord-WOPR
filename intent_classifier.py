from __future__ import annotations
import json
from typing import Any, List, Tuple, Type
from sortedcollections import OrderedSet
from db import Database
import dto
from intent import IntentType

class IntentClassifier:
    async def classify_intent(self, message : Message, intents : List[IntentType], database : Database, tools:List[Any]=[]) -> Tuple[List[Type[IntentType]], List[Any]]:
        descriptions = {}
        for intent in intents:
            winner = intent()
            for description in winner.get_descriptions():
                descriptions[description] = winner
        constraints = {"intent": list(descriptions.keys())}
        preferences = database.get_knowledge_base(message.user)
        pref_string = "\n".join([k + ": " + str(v.value) + " (" + v.description + ")" for k, v in preferences.items()])
        convo = database.get_current_conversation(message.user)
        if convo is not None and convo.summary is not None:
            pref_string += "\nWe were having the following conversation: " + convo.summary
        if len(pref_string) == 0:
            pref_string = None
        classifications, tool_calls = await chatgpt.get_structured_classification(message.text, dto.MessageClassification, constraints, pref_string, tools=tools) # type: ignore
        if tool_calls is not None:
            return None, tool_calls, classifications
        if classifications is None:
            raise Exception("No intent could be classified")
        message.classifications = classifications
        results = OrderedSet()
        for result in classifications:
            if result.intent is not None and result.intent in descriptions:
                results.add(descriptions[result.intent])
        if len(results) > 0:
            return list(results), tool_calls, classifications
        second_classification, tool_calls = await chatgpt.classify_intent(list(descriptions.keys()), message.text,  "This is a full breakdown of the message:\n```json\n" + json.dumps(classifications, indent=1, default=lambda x: x.__dict__) + "\n```\n", tools=tools)
        if second_classification is not None:
            for result in second_classification:
                if result in descriptions:
                    results.add(descriptions[result])
        return list(results), tool_calls

import chatgpt
from dto import Message
