from __future__ import annotations
import discord
from tinydb import TinyDB, Query
from tinydb.queries import QueryInstance
from typing import List, Optional, Type, Any, Union
import jsonpickle
from tinydb_serialization import Serializer
from tinydb_serialization import SerializationMiddleware
from tinydb.storages import JSONStorage
from dto import Conversation, Knowledge, Tool
from dto import User, UserConversation
from external_datasource import DataSource

UserUnion = Union[User, discord.User]
class JSONSerializer(Serializer):
    OBJ_CLASS : Type[object] = object

    def encode(self, obj):
        return jsonpickle.encode(obj)

    def decode(self, s):
        return jsonpickle.decode(s)
 
from tinydb import TinyDB, Query

def get_user_query(user: UserUnion, query : Query = Query()) -> QueryInstance:
    return query.user_id == str(user.id)

def get_conversation_query(user: UserUnion, conversation_id : str, query = Query()) -> QueryInstance:
    user_query = get_user_query(user, query)
    return user_query and query.conversation_id == conversation_id
    
class Database:
    def __init__(self, db_path="db.json"):
        middleware = SerializationMiddleware(JSONStorage)
        middleware.register_serializer(JSONSerializer(), "jsonpickle")
        self.db = TinyDB(db_path, indent=4, separators=(',', ': '), ensure_ascii=False, storage=middleware) 
        self.knowledge = self.db.table("knowledge")
        self.conversations = self.db.table("conversations")
        self.current_conversation = self.db.table("current_conversation")
        self.knowledge = self.db.table("knowledge")
        self.datasources = self.db.table("datasources")
        self.tools = self.db.table("tools")

    def get_knowledge_base(self, user : UserUnion) -> dict[str, Knowledge]:
        if not self.knowledge.contains(get_user_query(user)):
            return {}
        else:
            return self.knowledge.search(get_user_query(user))[0].get("knowledge", {})
        
    def get_knowledge(self, user: UserUnion, knowledge_key, default=None) -> Optional[Knowledge]:
        return self.get_knowledge(user.id).get(knowledge_key, default)
    
    def set_knowledge(self, user : UserUnion, knowledge_key: str, knowledge_value: Knowledge):
        if not self.knowledge.contains(get_user_query(user)):
            self.knowledge.insert({"user_id": str(user.id), "knowledge": {knowledge_key: knowledge_value}})
        else:
            knowledge = self.knowledge.search(get_user_query(user))[0].get("knowledge", {})
            knowledge[knowledge_key] = knowledge_value
            self.knowledge.upsert({"knowledge": knowledge}, get_user_query(user))

    def delete_knowledge(self, user : UserUnion, knowledge_key: str):
        if not self.knowledge.contains(get_user_query(user)):
            return
        else:
            knowledge = self.knowledge.search(get_user_query(user))[0].get("knowledge", {})
            del knowledge[knowledge_key]
            self.knowledge.upsert({"knowledge": knowledge}, get_user_query(user))


    def get_conversations(self, user : UserUnion) -> List[Conversation]:
        result = self.conversations.search(get_user_query(user))
        return [r.get("conversation", None) for r in result]
    
    def get_conversation(self, user : UserUnion, conversation_id : str) -> Optional[Conversation]:
        result = self.conversations.get(get_conversation_query(user, conversation_id))
        if result is None:
            return None
        return result.get("conversation", None)    
    def set_conversation(self, user: UserUnion, conversation : Conversation):
        self.conversations.upsert(UserConversation(user_id=str(user.id), conversation=conversation, conversation_id=conversation.id).__dict__, get_conversation_query(user, conversation.id))

    def delete_conversation(self, user: UserUnion, conversation_id : str):
        return self.conversations.remove(get_conversation_query(user, conversation_id))

    def set_current_conversation(self, user: UserUnion, conversation : Conversation):
        self.current_conversation.upsert({"user_id":str(user.id), "conversation_id": conversation.id}, get_user_query(user))

    def get_current_conversation(self, user : UserUnion) -> Optional[Conversation]:
        if not self.current_conversation.contains(get_user_query(user)):
            return None
        conversation_id = self.current_conversation.search(get_user_query(user))[0].get("conversation_id", None)
        if conversation_id is None:
            return None
        return self.get_conversation(user, conversation_id)
        
    def add_tool(self, user : UserUnion, tool : Tool):
        if not self.tools.contains(get_user_query(user)):
            self.tools.insert({"user_id":str(user.id), "tools": []})
        tools = self.tools.search(get_user_query(user))[0].get("tools", [])
        tools.append(tool)
        self.tools.update({"tools": tools}, get_user_query(user))
    
    def remove_tool(self, user : UserUnion, tool : str):
        if not self.tools.contains(get_user_query(user)):
            return
        tools = self.tools.search(get_user_query(user))[0].get("tools", [])
        tools.remove(tool)
        self.tools.update({"tools": tools}, get_user_query(user))
    
    def get_tools(self, user : UserUnion) -> List[str]:
        if not self.tools.contains(get_user_query(user)):
            return []
        return self.tools.search(get_user_query(user))[0].get("tools", [])