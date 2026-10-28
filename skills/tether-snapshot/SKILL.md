---
name: tether-snapshot
description: Create factual, attractive Tether calendar snapshots and task activity reports for natural-language time ranges using Tether's local MCP tools.
---
# Tether /snapshot

Use when a user types `/snapshot` with or without parameters, or asks for a visual task report such as "show how last week went", "give me a colorful view of November", "what is coming up over the next two weeks", or "show WriteShape's activity from the 3rd through the 18th."

## Natural-language interpretation
- Parse relative dates using the **user's local current date and timezone**, not the model's training date or UTC. Interpret "today", "yesterday", "tomorrow", "this/last/next week", "this/last/next month", "the past N days", "next N weeks", quarters, explicit dates, and "from X through Y". Inclusive `YYYY-MM-DD` endpoints.
- Weeks start Monday unless an explicit user preference is available. For "past N days", include today; for "next N days", include today unless the user says "starting tomorrow". If user says "last week", use the preceding full Monday–Sunday week, not a rolling seven days.
- If the period is omitted, default to current week. Only ask when a genuinely unresolved ambiguity would materially change the report. For ranges longer than the server's 366-day limit, explain the limit and offer adjacent reports; never silently truncate.
- Extract any specific category only if intended as a category filter; do not mistake task names for categories. Use the `categories` MCP tool when uncertain; no fabricated category names.
- Follow explicit filters and details such as "completed", "due", "activity", "overdue" when supported; say clearly when the source data cannot support the requested historical metric. Do not hallucinate completed work based on current task statuses.
- Choose day/week/month/custom view appropriate to the range. Keep the result a compact, read-only calendar inside the requested chat response: dates, tasks, category labels, task inspection, and downloads. Size each view to its own content; do not add editing controls, a separate application workspace, summary blocks, or introductory fanfare. Show Monday–Friday for multi-day calendars; include weekend columns only when tasks or recorded activity occur on them. Never substitute a generative AI image for deterministic Tether output.

## Retrieve and display
1. Invoke Tether MCP `get_snapshot(start, end, category="")` using exact inclusive ISO dates. Treat returned `days`, `insights`, and `notice` as the authoritative task data. For individual task details call `explore_thread(thread_id)`; obtain stable clickable references with `task_link(thread_id)`.
2. Preserve every task's `categories` list. Treat the legacy `category` field as the first membership only. Count overall tasks by unique `id`; category totals overlap and need not sum to the task count. A category filter matches any membership, including secondary ones. Never duplicate tasks into separate records to represent categories. Use `set_task_categories` with `mode="add"` to add a membership, `remove` to remove named memberships, or `replace` to intentionally set the complete list.
3. Present the returned `view_url` as a Markdown link in Tether chat; Tether embeds it as an interactive calendar automatically and removes the redundant link text. Do not preface it with numeric summaries unless the user asks for analysis. Calendar task buttons open read-only details. In other MCP clients, use a supported rich view or ordinary local links without promising that the host can embed Tether. Task references use `/board#task/<id>` on the local Tether origin. Cite only returned titles and dates; never invent activity, effort, productivity scores, status histories, or due dates.
4. Use returned `downloads.png` or `downloads.svg` URLs, preserving start, end, and any category filter. PNG accepts `theme` and `scale` (1, 2, 4); SVG accepts `theme`. Both exports size to their own content and include every task and membership. Never report a file exported unless it was actually created or returned by the integration.
5. Default to current Tether theme when rendering in the app. When a remote MCP client cannot obtain the user's theme, do not pretend it did; use a disclosed default or ask when materially important.
6. For empty periods, show the empty calendar without fabricated example tasks or count blocks. Distinguish recorded activity from current due dates using Tether's `notice` when discussing the data.

## Example prompts
- `/snapshot`
- `/snapshot yesterday`
- `/snapshot how did last week go?`
- `/snapshot show October and highlight activity from WriteShape`
- `/snapshot next two weeks, show what is coming due`
- `/snapshot between September 15 and October 20, in Ocean theme`
- `/snapshot last month as PNG at 4x`
- `/snapshot what changed this quarter for Cork?`
