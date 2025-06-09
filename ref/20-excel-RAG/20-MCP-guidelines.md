How Cursor decides to invoke your MCP tool (no @ needed)
	1.	Cursor sends the model a “menu” of tools every turn
*When you hit Run in Chat, Cursor serialises the first ≈ 40 tools that are enabled under Settings ▸ MCP ▸ Available Tools (built-ins plus any from your MCP servers).
	•	That list is passed to the underlying LLM in the standard “tools / function-calling” field.
	•	The system prompt already instructs the model to choose whichever tool (or none) best fulfils the user’s request.  ￼
	2.	The LLM chooses a tool when its name + description look like the best match
Function-calling heuristics are pure semantics: the model scans the user’s utterance, looks at every tool’s name, description, and JSON schema, and returns a tool_call block if one of them is clearly helpful. Think of it exactly like normal OpenAI / Anthropic function calling, just wrapped in MCP.  ￼
	3.	Manual approval vs. true “auto-run”
	•	By default you still get the blue Run tool button (“human-in-the-loop” safeguard).
	•	Flip the Yolo / Auto-run switch (either globally in Settings ▸ Chat ▸ Yolo or in a custom mode) and Cursor will execute the tool immediately with no confirmation. The built-in Yolo mode ships with this on.  ￼ ￼

⸻

Making the agent want to call your MCP server

Lever	What to do	Why it helps
Concise, verb-first names	generate_release_notes, query_assumptions	Models match verbs (“generate…”, “query…”) faster than nouns.
Rich, example-heavy descriptions	“Produce an actuarial assumption table (JSON) for the given product code, age, duration…”	Gives the LLM the keywords it will see in user queries.
Minimal, clear argument schema	Keep only the parameters you really need, with descriptive titles.	Less cognitive load ⇒ higher call probability.
Limit the tool buffet	Expose one composite tool instead of five variants when possible.	Cursor only forwards ≈ 40 tools; extra noise dilutes yours.
Project/user rules	Add a rule like:When the user asks for assumption data, always call query_assumptions (MCP).	Hard-bakes the preference into the system prompt.
Custom mode	Create a “Gaspatchio Assistant” mode that enables only your server + core tools, with Auto-run toggled.	Removes competing options entirely.


⸻

Minimal example

fastmcp server

# server.py
from fastmcp import FastMCP

mcp = FastMCP("Gaspatchio tools")

@mcp.tool
def query_assumptions(product_code: str, scenario: str | None = None) -> dict:
    """Return a JSON assumption table for the given product."""
    return lookup_from_pg(product_code, scenario)

if __name__ == "__main__":
    mcp.run()

Global ~/.cursor/mcp.json

{
  "mcpServers": {
    "gaspatchio": {
      "command": "python",
      "args": ["-m", "server"],
      "env": { "PG_DSN": "postgres://…" }
    }
  }
}

Start Cursor → Settings ▸ MCP ↦ enable “gaspatchio / query_assumptions”.

Now, when a user types:

“Give me the mortality assumptions for product AF-LX under the stress scenario”

…Cursor’s agent will see the tool description, emit a tool_call for query_assumptions, and – if Yolo/Auto-run is on – execute it immediately, no @ prefix required.

⸻

Troubleshooting checklist
	1.	Tool doesn’t fire?
Check the chat debug panel – is your tool in the JSON tools array? If not, it’s probably disabled or pushed out because you have >40 tools.
	2.	Still asks for confirmation with Yolo on?
You may be running a Cursor version < 0.46; auto-run for MCP landed there.  ￼
	3.	Model hallucinates parameters?
Validate inputs server-side and send back an error string – Cursor will show it in chat and the model will usually retry with corrected args.

With the naming/description tweaks and Auto-run enabled, your users can simply ask naturally and let the agent route calls to your MCP server behind the scenes.