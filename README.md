# Do not clone this repo and use code currently it's in testing mode
# code-mode-mcp

A minimal **FastMCP** server that exposes [FakerAPI.it](https://fakerapi.it) endpoints as typed MCP tools,
with a **Code Mode** execution layer inspired by Anthropic's [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
and Cloudflare's [Codemode](https://developers.cloudflare.com/agents/api-reference/codemode/) pattern.

Built for learning — designed to run in VS Code as a GitHub Copilot MCP server.

## Project structure

```
code-mode-mcp/
├── server.py        ← FastMCP server, tool registration
├── code_mode.py     ← Code Mode execution layer
├── requirements.txt
└── .vscode/
    └── mcp.json     ← VS Code / Copilot auto-discovery config
```

## Tools

### Data tools (standard)

| Tool | FakerAPI endpoint | What it returns |
|---|---|---|
| `get_persons` | `/persons` | Person profiles with address, email, phone |
| `get_companies` | `/companies` | Company records with contact & VAT |
| `get_products` | `/products` | Product listings with price & categories |
| `get_books` | `/books` | Book records with author, ISBN, publisher |
| `get_addresses` | `/addresses` | Address objects with lat/lng |

Every data tool accepts:
- `quantity` (int, 1–1000, default 5)
- `locale` (str, e.g. `"en_US"`, `"fr_FR"`, default `"en_US"`)
- `seed` (int | None — for reproducible results)

Some tools have extra params (e.g. `gender` for persons, `country_code` for addresses).

### Code Mode tool

| Tool | What it does |
|---|---|
| `execute_code` | LLM writes Python that orchestrates any combination of the above tools, runs it, and returns only what's needed |

## Two execution modes explained

### Standard tool calling (what most MCP servers do)

Copilot calls `get_books(quantity=3)` directly. The full JSON payload — every field across all 3 records — is returned and loaded into Copilot's context window. If you ask for books and companies together, that's two round trips, two full payloads.

### Code Mode (what this server adds)

Instead of calling tools directly, Copilot writes a small Python script and passes it to `execute_code`. The script runs, calls the faker functions internally, filters and shapes the result, and only the clean output comes back. For example, asking for "3 books with just title and author" produces code like:

```python
def run():
    books = get_books(quantity=3)
    return [{"title": b["title"], "author": b["author"]} for b in books]
```

The full book payload never enters Copilot's context — only the two fields you asked for do.

## Why this matters: token bursts

Every piece of data that flows through the LLM costs tokens. In standard tool calling, the full API response lands in the context window on every call. This creates **token bursts** — sudden spikes in context consumption that:

- **Increase latency** — the model processes more tokens before generating a response.
- **Increase cost** — you pay per token, including intermediate tool results.
- **Hit context limits** — a few large responses can fill the context window, breaking multi-step workflows.
- **Reduce accuracy** — the more irrelevant data the model sees, the more likely it is to get distracted or make mistakes copying data between tool calls.

Code Mode addresses all of these by keeping intermediate data in the execution environment. The LLM only sees what the code explicitly returns. A request that previously caused a burst of 5,000 tokens from raw API payloads might return 50 tokens of filtered output instead.

This matters even more as you add tools. If your server exposes 20 tools and the user's request touches 5 of them, standard calling means 5 full payloads in context. Code Mode means one filtered result. The token savings compound with scale.

The tools themselves are still hardcoded by the developer — Code Mode doesn't change that. What it changes is how the LLM interacts with them: writing code that orchestrates multiple tools in one pass, rather than calling them one by one through the agent loop.

## Setup

```bash
# 1. Install dependencies (using uv)
uv sync

# 2. Run manually
uv run server.py
```

## VS Code / GitHub Copilot

The `.vscode/mcp.json` is pre-configured. VS Code picks it up automatically.

1. Open this folder in VS Code.
2. Make sure the GitHub Copilot extension is installed and signed in.
3. VS Code starts `uv run server.py` when Copilot needs the tools.

## Example Copilot prompts

These work best with Code Mode active (Copilot will use `execute_code`):

```
Give me 3 books with just the title and author
Fetch 2 companies and 3 persons in French and combine them into one list
Get 5 products sorted by price, return only name and price
Fetch persons with seed 42 so I get the same results every time
```

These simpler ones may use the direct tools:

```
Fetch 3 fake persons
Get addresses in Germany
```

## References

- [Code Execution with MCP — Anthropic](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Codemode — Cloudflare](https://developers.cloudflare.com/agents/api-reference/codemode/)
- [FakerAPI.it](https://fakerapi.it)
- [FastMCP](https://github.com/jlowin/fastmcp)