import os
import re
import asyncio
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


class GameSession:
    """Manages the state, hints, and multiplayer scoreboard for a single game channel."""
    def __init__(self, title: str, full_data: str):
        self.title = title
        self.full_data = full_data
        self.hint_count = 0
        # {user_id: {"name": str, "points": int, "questions": int}}
        self.scores = {}

    def record_question(self, user_id: int, user_name: str):
        if user_id not in self.scores:
            self.scores[user_id] = {"name": user_name, "points": 0, "questions": 0}
        self.scores[user_id]["questions"] += 1
        self.scores[user_id]["name"] = user_name

    def add_points(self, user_id: int, user_name: str, points: int):
        if user_id not in self.scores:
            self.scores[user_id] = {"name": user_name, "points": 0, "questions": 0}
        self.scores[user_id]["points"] += points
        self.scores[user_id]["name"] = user_name

    def format_leaderboard(self) -> str:
        if not self.scores:
            return "📊 **Leaderboard:** No questions asked or points scored yet!"

        sorted_players = sorted(
            self.scores.values(),
            key=lambda x: (x["points"], -x["questions"]),
            reverse=True
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = [f"🏆 **Standings for '{self.title}':**"]
        for idx, player in enumerate(sorted_players):
            badge = medals[idx] if idx < 3 else f"`#{idx+1}`"
            lines.append(
                f"{badge} **{player['name']}** — **{player['points']} pts** "
                f"({player['questions']} questions)"
            )
        return "\n".join(lines)


# Active games mapped per channel: {channel_id: GameSession}
active_games: dict[int, GameSession] = {}


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
            game = active_games.pop(channel_id)
            await message.reply(f"Current game session '{game.title}' ended. / 当前汤局已结束。")
        else:
            await message.reply("No active game in this channel. / 当前频道没有进行中的汤。")
        return

    # Command: !score
    if content == "!score":
        if channel_id in active_games:
            game = active_games[channel_id]
            await message.reply(game.format_leaderboard())
        else:
            await message.reply("No active game running in this channel. / 当前频道没有进行中的汤。")
        return

    # Command: !hint
    if content == "!hint":
        if channel_id not in active_games:
            await message.reply("No active game in this channel to give a hint for. / 当前没有进行中的汤。")
            return

        game = active_games[channel_id]
        game.hint_count += 1

        async with message.channel.typing():
            hint_prompt = f"""
            You are the Game Master for Haiguitang (海龟汤).
            Here is the puzzle data including the secret truth:
            {game.full_data}

            Instructions:
            1. Provide a clever, mysterious hint (Hint #{game.hint_count}) pointing players toward a major breakthrough or clearing a misconception.
            2. NEVER explicitly reveal or spoil the secret truth (汤底).
            3. FORMAT: Output in BOTH Chinese and English.
            """
            try:
                res = ai_client.models.generate_content(
                    model=GAME_MODEL,
                    contents=hint_prompt
                )
                await message.reply(f"💡 **Hint #{game.hint_count} / 线索 #{game.hint_count}:**\n{res.text}")
            except Exception as err:
                print(f"[HINT ERROR] {err}")
                await message.reply("Failed to generate hint.")
        return

    # Command: !giveup
    if content == "!giveup":
        if channel_id not in active_games:
            await message.reply("No active game to give up on. / 当前没有进行中的汤。")
            return

        game = active_games.pop(channel_id)
        async with message.channel.typing():
            reveal_prompt = f"""
            You are the Game Master for Haiguitang (海龟汤).
            The players have given up on the puzzle.
            Here is the puzzle data:
            {game.full_data}

            Provide a full, dramatic reveal and explanation of the secret truth (汤底) in BOTH Chinese and English.
            """
            try:
                res = ai_client.models.generate_content(
                    model=GAME_MODEL,
                    contents=reveal_prompt
                )
                standings = game.format_leaderboard()
                await message.reply(
                    f"🏳️ **Game Over! The room gave up on '{game.title}'. / 游戏结束，大家选择放弃了。**\n\n"
                    f"**🍲 Full Truth (汤底):**\n{res.text}\n\n{standings}"
                )
            except Exception as err:
                print(f"[GIVEUP ERROR] {err}")
                await message.reply("Failed to reveal the story.")
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

            active_games[channel_id] = GameSession(title=puzzle_name, full_data=puzzle_text)

            text_prompt = f"""
            You are the Game Master for Haiguitang (海龟汤).
            Here is the puzzle data:
            {puzzle_text}

            Instructions:
            1. Announce the puzzle title and the 汤面 (surface premise) clearly.
            2. NEVER reveal the 汤底 (truth) or critical clues.
            3. Invite players to begin asking Yes/No questions.
            4. Remind them of commands: `!hint`, `!score`, `!giveup`.
            5. FORMAT: Provide everything in BOTH Chinese and English. Show the Chinese section first, followed immediately by an accurate English translation.
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
        game = active_games[channel_id]
        author = message.author
        game.record_question(author.id, author.display_name)

        async with message.channel.typing():
            user_query = f"【Player: {author.display_name}】 asks: {content}"

            eval_prompt = f"""
            You are the strict Game Master for Haiguitang (海龟汤).
            Full puzzle details and secret truth:
            {game.full_data}

            Player query: {user_query}

            Rules:
            1. Evaluate strictly against the secret truth. Players may ask questions in either Chinese or English.
            2. Standard responses:
               - 是 (Yes)
               - 不是 (No)
               - 是也不是 (Yes and No / Partially)
               - 没有关系 (Irrelevant / Unrelated)
            3. FORMAT REQUIREMENT: Always respond in BOTH Chinese and English.
               Example: 是 (Yes) / 不是 (No)
            4. Scoring & Verdict Directives (Append EXACTLY one of these tags at the very end of your response):
               - If the question deduces the full core truth (盘出完整汤底):
                 Tag: `[VERDICT: SOLVED] <POINTS: 5>`
               - If the question discovers a crucial breakthrough clue or exposes a key hidden assumption:
                 Tag: `<POINTS: 1>`
               - If standard, unrevealing, or irrelevant:
                 Tag: `<POINTS: 0>`
            """
            try:
                res = ai_client.models.generate_content(
                    model=GAME_MODEL,
                    contents=eval_prompt
                )
                raw_response = res.text

                # Extract points: <POINTS: X>
                points = 0
                points_match = re.search(r"<POINTS:\s*(\d+)>", raw_response)
                if points_match:
                    points = int(points_match.group(1))

                if points > 0:
                    game.add_points(author.id, author.display_name, points)

                # Check if solved
                is_solved = "[VERDICT: SOLVED]" in raw_response

                # Clean control tags from the visible chat output
                clean_reply = re.sub(r"\[VERDICT:\s*SOLVED\]|<POINTS:\s*\d+>", "", raw_response).strip()

                if is_solved:
                    # Remove from active games and trigger victory screen
                    active_games.pop(channel_id, None)
                    standings = game.format_leaderboard()
                    await message.reply(
                        f"🎉 **{author.display_name} cracked the soup! / 破解了汤底！ (+5 pts)**\n\n"
                        f"{clean_reply}\n\n"
                        f"{standings}"
                    )
                else:
                    score_badge = f" *(+{points} pt)*" if points == 1 else ""
                    await message.reply(f"{clean_reply}{score_badge}")

            except Exception as err:
                print(f"[QA ERROR] Error evaluating question: {err}")
                await message.reply("Encountered an error evaluating question.")


bot.run(DISCORD_TOKEN)
