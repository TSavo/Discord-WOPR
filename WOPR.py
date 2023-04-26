import asyncio
import datetime
from typing import Optional
import discord
from discord import app_commands, SelectMenu, SelectOption
import openai
import os
import json
from action import ConversationCompletionAction
from chatgpt import extract_datasource, get_is_request_to_change_topics, get_new_or_existing_conversation, merge_conversations, summarize, summarize_knowledge, find_similar_conversations
from db import Database, UserUnion
from discord_handler import DiscordHandler, DiscordSendable
from dto import Conversation, Message
from sendable import Sendable
from timezones import timezones


openai.api_key = os.environ.get("OpenAIAPI-Token")
model_engine = "gpt-3.5-turbo"

db = Database("db.json")

intents = discord.Intents(messages=True, guilds=True, message_content=True, members=True, guild_reactions=True, dm_reactions=True, presences=True, reactions=True, typing=True, voice_states=True, webhooks=True)
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

commands = json.load(open("commands.json", "r"))

handler = DiscordHandler()

def get_preference(user, preference, default="") -> Optional[str]:
    return db.get_preference(user, preference, default)

def get_preferences(user: UserUnion) -> dict:
    return db.get_preferences(user)

def set_preference(user : UserUnion, preference, value) -> None:
    db.set_preference(user, preference, value)

def remove_preference(user, preference):
    db.delete_preference(user, preference)

def set_datasource(user, datasource):
    db.set_datasource(user, datasource)

def get_datasource(user, name):
    return db.get_datasource(user, name)

def get_datasources(user):
    return db.get_datasources(user)

def delete_datasource(user, name):
    db.delete_datasource(user, name)

def split_into_chunks(text, chunk_size=2000):
    chunks = []
    while len(text) > chunk_size:
        last_space = text[:chunk_size].rfind(" ")
        chunks.append(text[:last_space])
        text = text[last_space+1:]
    chunks.append(text)
    return chunks

async def send(channel, text):
    for chunk in split_into_chunks(text):
        await channel.send(chunk)

async def complete(message:Message, database: Database, sendable: Sendable):
    await ConversationCompletionAction()(message, database, sendable)

for command in commands:
    def command_maker(system, user):
        async def interaction(interaction):
            await interaction.response.defer()
            convo = Conversation.new_conversation()
            convo.set_system("system", system)
            db.set_conversation(interaction.user, convo)
            db.set_current_conversation(interaction.user, convo)
            sendable = DiscordSendable(interaction.followup)
            message = Message.from_message(interaction.message)
            await complete(message, db, sendable)
        return interaction
    tree.add_command(discord.app_commands.Command(name=command["command"], description=command["description"], callback=command_maker(command["system"], command["user"])))



@tree.command(name="adddatasource", description="Add a data source")
async def add_datasource_command(interaction, description: str):
    await interaction.response.defer()
    ds = await extract_datasource(description)
    if ds is None:
        await interaction.followup.send("No data source found")
        return
    await interaction.followup.send(f"Added data source {ds.get('name') or ds.get('url')}")
    set_datasource(interaction.user.id, ds)

@tree.command(name="timezone", description="Sets your timezone for the datetime command")
async def timezone_command(interaction):
    view = discord.ui.View()
    view.add_item(discord.ui.Select(placeholder="Select timezone", options=[SelectOption(label=value, value=key) for key, value in timezones.items()]))
    await interaction.response.defer()
    message = await interaction.followup.send("Please choose your timezone:", view=view)
    async def respond_to_select(user, message, id):
        interaction = await client.wait_for("interaction", check=lambda i: i.user == user and i.data is not None and i.message == message and len(i.data.get("values", [])) > 0)
        if interaction.data is None or interaction.message is None or len(interaction.data.get("values", [])) == 0:
            return
        timezone = interaction.data.get("values", [])[0]
        await interaction.message.edit(content="Your timezone has been set to: " + timezones[timezone], view=None)
        set_preference(user.id, "timezone", str(timezone))
    asyncio.create_task(respond_to_select(interaction.user, message, id))

@tree.command(name = "now", description = "Displays current date and time") #Add the guild ids in which the slash command will appear. If it should be in all, remove the argument, but note that it will take some time (up to an hour) to register the command if it's for all guilds.
async def now_command(interaction):
    now = datetime.datetime.now()
    nowstr = now.strftime('%m-%d-%Y-%H:%M:%S')
    await interaction.response.send_message(nowstr)

@tree.command(name = "new", description = "Clears the current conversation's context") #Add the guild ids in which the slash command will appear. If it should be in all, remove the argument, but note that it will take some time (up to an hour) to register the command if it's for all guilds.
async def new_command(interaction):    
    convo = Conversation.new_conversation()
    db.set_conversation(interaction.user, convo)
    db.set_current_conversation(interaction.user, convo)
    await interaction.response.send_message("New conversation created.")

@tree.command(name='sync', description='Owner only')
async def sync(interaction: discord.Interaction):
    await interaction.response.defer()
    await tree.sync(guild=interaction.guild)
    await tree.sync()
    await interaction.followup.send('Synced.')

@client.event
async def on_ready():
    print('Logged in as {0.user}'.format(client))
    await tree.sync()

@client.event
async def on_message(message): 
    if message.author == client.user or message.author.bot:
        return
    async def handle_message_async(message):
        return await handler.handle_discord_message(message, db, message.channel)
    asyncio.create_task(handle_message_async(message))
    
token = os.environ.get("Discord-Token", None)
if token is None:
    raise ValueError("No Discord token found in the environment variables. Please set the environment variable 'Discord-Token' to your Discord bot token.")
client.run(token)
