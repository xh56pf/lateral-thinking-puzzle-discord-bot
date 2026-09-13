# Lateral Thinking (aka Haiguitang) Discord Bot

An asynchronous, multiplayer lateral thinking puzzle bot powered by the Google GenAI SDK (Gemini 3.5 Flash-Lite) and Anthropic's Model Context Protocol (MCP). The bot acts as an automated Game Master, serving bilingual mystery premises, moderating Yes/No question loops, evaluating win-conditions without leaking spoilers, and tracking multi-player scoring in real time.

## Architecture Overview
The system decouples knowledge access from game coordination using standard protocols and containerized isolation:

DiscordUser["Discord Players"] <-->|"Gateway Events (discord.py)"| BotEngine["Bot Engine (run_game.py)"]
    BotEngine <-->|"Stdio Subprocess (uv)"| MCPServer["MCP Server (server.py)"]
    MCPServer <-->|"File I/O"| PuzzleData["Puzzles Catalog (.md)"]
    BotEngine <-->|"REST / GenAI SDK"| GeminiAPI["Gemini 3.5 Flash-Lite"]

- Event-Driven Interface: Built with discord.py to handle concurrent channel sessions, input throttling, and dynamic command dispatch.

- Context Decoupling via MCP: Puzzle retrieval is isolated in a separate Model Context Protocol server spawned over stdio via uv, keeping underlying mystery solutions inaccessible to direct user prompts.

- Prompt & Response Parsing: Uses strict structural formatting directives to output bilingual responses (Chinese (English)) while tagging internal scoring signals parsed in Python.



## Tech Stack

- Language: Python 3.11+

- LLM Engine: Google Gemini 3.5 Flash-Lite (google-genai SDK)

- Tool & Context Standard: Model Context Protocol (MCP via mcp SDK & uv)

- Bot Framework: discord.py (Async / Gateway)

- Environment & Packaging: Docker, Docker Compose


## Features
- Bilingual Lateral Thinking Gameplay: Automatically serves mystery setups (汤面) and answers player inquiries in dual Chinese/English formatting.

- Automated Clue Moderation: Evaluates queries strictly as 是 (Yes), 不是 (No), 是也不是 (Partially), or 没有关系 (Irrelevant) without spoiling the underlying truth (汤底).

- Cost & Latency Optimized: Runs against gemini-3.5-flash-lite to ensure near-zero latency in chat channels while maximizing API rate limits and token economics.


## Command Reference
!list : Queries the MCP server for all cataloged puzzle titles and summaries  

!start <title> : Initializes a new game session with bilingual surface setup  

!stop : Ends the active session, prints final standings, and clears channel state  

