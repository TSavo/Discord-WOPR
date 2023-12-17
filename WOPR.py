import asyncio
import datetime
from typing import Optional
import discord
from discord import app_commands, SelectOption
import openai
import os
import json
from action import ConversationCompletionAction
from chatgpt import extract_datasource
from db import Database, UserUnion
from discord_handler import DiscordHandler, DiscordSendable
from dto import Conversation, Message
from sendable import Sendable
from db import Database
import asyncio
from timezones import timezones
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

db = Database("db.json")

intents = discord.Intents(messages=True, guilds=True, message_content=True, members=True, guild_reactions=True, dm_reactions=True, presences=True, reactions=True, typing=True, voice_states=True, webhooks=True)
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

commands = json.load(open("commands.json", "r"))

handler = DiscordHandler()

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


@tree.command(name="summary", description="Get a summary of your conversations")
async def summary_command(interaction):
    await interaction.response.send_message(f"Summary: FIX ME") #conversation_manager.get_conversation_summary(interaction.user.id)}")

def channel_responder(channel, chunk_size=60):
    content = ""
    send = None
    sent = 0
    async def pipe(message):
        nonlocal content
        nonlocal send
        nonlocal sent
        content += message
        if send is None and len(content) > sent + chunk_size:
            sent = len(content)
            send = await channel.send(content)
        elif len(content) > sent + chunk_size:
            sent = len(content)
            await send.edit(content=content)
    async def done():
        nonlocal content
        if content == "":
            return
        nonlocal send
        nonlocal sent
        if send is None and len(content) > 0:
            await channel.send(content)
        else:
            if send is not None:
                await send.edit(content=content)
    return pipe, done

@client.event
async def on_ready():
    logging.info('Logged in as {0.user}'.format(client))
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
