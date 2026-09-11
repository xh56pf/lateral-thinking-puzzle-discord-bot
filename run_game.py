import os
import discord
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MCP_SERVER_DIR = os.path.abspath("./haiguitangmcp/haiguitang_mcp")
GAME_MODEL = "gemini-3.5-flash-lite"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

ai_client = genai.Client(api_key=GEMINI_API_KEY)
active_games = {}

@bot.event
async def on_ready():
    print(f"DM is online as {bot.user}! Ready for Haiguitang.")
    print(f"Using model: {GAME_MODEL}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    channel_id = message.channel.id
    content = message.content.strip()

    server_params = StdioServerParameters(
        command="uv",
        args=["--directory", MCP_SERVER_DIR, "run", "server.py"]
    )

    # Command: !list
    if content == "!list":
        async with message.channel.typing():
            try:
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        list_result = await session.call_tool("list_puzzles_tool", arguments={})

                raw_list = list_result.content[0].text
                list_prompt = f"""
                Here is a list of Haiguitang puzzle titles and summaries:
                {raw_list}

                Please output this list formatted nicely for Discord with both Chinese and English translations for each title/description.
                End with: 'Type `!start <title>` to begin a game! / 输入 `!start <题目>` 开始游戏！'
                """
                res = ai_client.models.generate_content(
                    model=GAME_MODEL,
                    contents=list_prompt
                )
                await message.reply(res.text)
            except Exception as err:
                print(f"[LIST ERROR] {err}")
                await message.reply("Failed to retrieve puzzle catalog from MCP server.")
        return

    # Command: !stop
    if content == "!stop":
        if channel_id in active_games:
            del active_games[channel_id]
            await message.reply("Current game session ended. / 当前汤局已结束。")
        else:
            await message.reply("No active game in this channel. / 当前频道没有进行中的汤。")
        return

    # Command: !start <puzzle_name>
    if content.startswith("!start"):
        async with message.channel.typing():
            parts = content.split(maxsplit=1)
            puzzle_name = parts[1] if len(parts) > 1 else "忠诚的狗"

            try:
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        puzzle_result = await session.call_tool(
                            "get_puzzle", arguments={"puzzle_title": puzzle_name}
                        )
                puzzle_text = puzzle_result.content[0].text
            except Exception as err:
                print(f"[MCP ERROR] Failed to fetch puzzle '{puzzle_name}': {err}")
                await message.reply(f"Could not find puzzle '{puzzle_name}' in MCP database.")
                return

            active_games[channel_id] = {
                "title": puzzle_name,
                "full_data": puzzle_text
            }

            # Generate text story & bilingual premise
            text_prompt = f"""
            You are the Game Master for Haiguitang (海龟汤).
            Here is the puzzle data:
            {puzzle_text}

            Instructions:
            1. Announce the puzzle title and the 汤面 (surface premise) clearly.
            2. NEVER reveal the 汤底 (truth) or critical clues.
            3. Invite players to begin asking Yes/No questions.
            4. FORMAT: Provide everything in BOTH Chinese and English. Show the Chinese section first, followed immediately by an accurate English translation.
            """
            try:
                text_res = ai_client.models.generate_content(
                    model=GAME_MODEL,
                    contents=text_prompt
                )
                await message.reply(text_res.text)
            except Exception as err:
                print(f"[GEN ERROR] Failed generating premise: {err}")
                await message.reply("Failed to generate premise. Please check server logs.")
        return

    # In-game questioning
    if channel_id in active_games and not content.startswith("!"):
        async with message.channel.typing():
            puzzle_context = active_games[channel_id]["full_data"]
            user_query = f"【Player: {message.author.display_name}】 asks: {content}"

            eval_prompt = f"""
            You are the strict Game Master for Haiguitang (海龟汤).
            Full puzzle details and secret truth:
            {puzzle_context}

            Player query: {user_query}

            Rules:
            1. Evaluate strictly against the secret truth. Players may ask questions in either Chinese or English.
            2. Standard responses:
               - 是 (Yes)
               - 不是 (No)
               - 是也不是 (Yes and No / Partially)
               - 没有关系 (Irrelevant / Unrelated)
            3. FORMAT REQUIREMENT: Always respond in BOTH Chinese and English.
               Example:
               是 (Yes)
               或者: 不是 (No)
            4. If a player describes the full solution (盘汤底) and hits the core plot points:
               - Declare them the winner in both Chinese and English!
               - Reveal the full story (汤底) in both Chinese and English.
            """
            try:
                res = ai_client.models.generate_content(
                    model=GAME_MODEL,
                    contents=eval_prompt
                )
                await message.reply(res.text)
            except Exception as err:
                print(f"[QA ERROR] Error evaluating question: {err}")
                await message.reply("Encountered an error evaluating question.")

bot.run(DISCORD_TOKEN)