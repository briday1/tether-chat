# tether-chat — detailed documentation

A local-first personal assistant for unfinished thoughts. Talk naturally: “Remember that I need to look into this,” “What am I tracking?”, “That thing is blocked,” or “I finished it.” tether-chat keeps its state in SQLite, **not** browser storage.

## Install and start

Python 3.11 or newer.

```bash
git clone https://github.com/briday1/tether-chat.git
cd tether-chat
python -m pip install -e .
tether
```

The **single `tether-chat` command** waits for the web server to respond successfully before opening a browser tab, and starts the browser web server on http://127.0.0.1:8765 and local MCP streamable-HTTP on http://127.0.0.1:8766/mcp. Press Ctrl+C to stop both. Set `TETHER_NO_BROWSER=1` if you don't want your browser to open.

Open **Settings** in the GUI, enter your HTTPS API base URL, model name and your own API key. The model **must support OpenAI-compatible chat-completions tool calling**. The key is stored in the operating system credential vault (Windows Credential Manager, macOS Keychain, or a supported Linux Secret Service/KWallet backend), NOT in `provider.json`. Only the nonsecret provider URL and model are saved in `~/.tend/provider.json`. The GUI never receives a stored key or exposes a show-key control; changing or clearing browser data does not remove it. If no secure vault is available, key saving fails closed; you can alternatively supply `TETHER_AI_API_KEY` as a process environment variable. Existing plaintext keys from early tether-chat builds are migrated on next settings load when a secure vault is available. Because older versions previously wrote the key unencrypted, consider rotating that key. For hosted AI, note that thread context is sent to the configured provider.

## Local storage and MCP

- SQLite: `~/.tend/tend.sqlite3` (override via `TETHER_DB`)
- Browser: http://127.0.0.1:8765
- MCP HTTP: http://127.0.0.1:8766/mcp
- MCP stdio alternative: `python -m tether.mcp_server`
- Local backup: **Settings → Download SQLite backup**
- Tests: `python -m pip install -e '.[dev]'` then `pytest`

MCP and the browser use **the same database**. MCP tools can read and update stored information. Both servers listen on loopback only; there is no authentication. Do not expose ports to other machines or untrusted clients. Clients must be trusted, and an accessible MCP port is not a protected security boundary.

## What it does

Conversation and a separate categorized Board with shared top navigation, five local color themes (Sage, Ocean, Clay, Violet, Graphite), searchable category columns, AI-assisted automatic grouping, manual card editing (title, category, details, status and revisit date), accumulated notes, completion/waiting status changes, searchable history, local SQL storage, BYOK settings, and optional MCP access. On the Board, choose **Ask AI to organize** to draft an instruction in Conversation, review it, and send it. The AI can also choose categories while capturing new thoughts. Both views operate on the same underlying SQLite records.

Current limits: reminders are surfaced when browsing (no OS push notifications); natural-language dates depend on the model; no scheduled background agent, automatic backup schedule, multi-device sync, or fully semantic long-term retrieval. The assistant uses a bounded tool-calling loop; providers without tool calling won't support the full experience.

## Key security

The API key input uses a password field, autocomplete disabled, and is cleared after saving. The GET settings endpoint returns only `has_key`, model, and URL. Saved credentials stay in the operating system vault. No credential ever belongs in the SQLite database, a browser cache, or the Git repository. Avoid running tether-chat behind a public reverse proxy, or using an untrusted model provider. A previously saved key from versions before the vault migration may exist in filesystem backups, disk history, or snapshots; rotate it if exposure is a concern.

The selected color theme is a display preference kept in browser local storage, separate from SQLite content; clearing browser data resets only the theme, not thoughts or conversations.

## Daily brief and commands

The Conversation view includes a **/ Commands** reference button (or type `/` in an empty message). Commands work locally without an AI request:

- `/brief` — due, active and waiting overview
- `/due` — reminders ready to revisit
- `/waiting` — blocked or waiting items
- `/recent` — recently changed topics
- `/board` — board navigation hint
- `/help` — command reference

Ask the assistant for a daily brief conversationally to get an AI-interpreted answer from the same stored information.

## Desktop notifications and Attention

Running `tether-chat` now starts three local components: the browser web server, MCP HTTP server, and desktop notification worker. The worker polls for due reminders every 20 seconds and attempts OS desktop notifications. Notifications require an active desktop session and OS notification support; they do not run while tether-chat is stopped or the computer is off. To avoid storms of stale popups, the worker only notifies reminders due within the previous 24 hours, at most three per polling cycle; older items remain visible in tether-chat. Due reminders are marked as attempted at most once per schedule, including across restarts. Operating-system permissions and platform support may affect whether a popup is actually shown.

The right-side **Attention** panel is selected by the configured AI model rather than displaying every open thread. It shows at most five items, can show none, and caches choices for ten minutes or until recorded threads change. The refresh control asks the AI to reconsider. With no AI connection or a failed AI response, the panel falls back to explicit due reminders only.

Conversation and Board share the same top navigation geometry.

## Appearance

tether-chat uses the same named theme color definitions as WriteShape: Light, Dark, Solarized Light, Solarized Dark, Sepia, Sage, Rose, Dusk, and Ocean (sourced from `fountain-publisher/beta/src/branding/writeShapeThemes.ts`). Board categories use stable colored outlines around each card; there are no category dots, drop shadows, or glow effects.

## Dates, activity history, and database location

Each thought may have an optional **Due date** (an actual deadline) and separately **Bring to attention** (when tether-chat should nudge you). Only the attention date directly schedules a desktop notification. A due date does not imply one.

The board includes an activity timeline. Log progress, feedback, blockers or decisions with the time they happened (default: now). The AI and MCP tools also support backdated events and period reports for weeks, months, quarters and years. Reports use the recorded occurrence time, not entry time.

In **Settings → Database location**, choose either **Move current database** to a new unused SQLite filename or **Use an existing tether-chat database**. Both are staged until you stop and restart `tether-chat`. A move uses SQLite backup and integrity verification and keeps the original. Using an existing database validates its schema and integrity without overwriting it. Choose a local disk or a backup-managed folder, **not a cloud-sync folder that modifies the live SQLite file while tether-chat is running**. The browser cannot provide a reliable native system file path through ordinary web file pickers, so paste a full path (e.g. `D:\\Backups\\tether-chat\\tend.sqlite3`). External `TETHER_DB` environment overrides take precedence and disable Settings relocation.

## Moving the database from Settings

Open **Settings → Database location → Move current database → Browse…**. tether-chat opens a native folder picker on the computer running the local server. Choose an existing folder, then click **Move database**. The single `tether-chat` launcher stops the web, MCP, and notification processes, copies and verifies the live SQLite database, switches the active database path, and restarts the services automatically. The original database stays at its previous location as a safety backup. The browser may briefly lose the connection during this operation. Do not terminate tether-chat during the move.

The other option, **Use an existing tether-chat database**, accepts an existing full database filename and validates it before switching. Database relocation is available when launched through the `tether-chat` command; starting only `uvicorn` bypasses the supervisor that handles automatic restarts. A desktop folder chooser requires an active GUI session on the local host. Backing up the live database should be done via tether-chat's SQLite backup feature rather than direct file synchronization.

## Install tether-chat as a Windows desktop app (recommended)

Requires Windows 10/11, Python 3.11+, Git, and Microsoft Edge or Google Chrome. These instructions install tether-chat locally; no hosted service or cloud database is required.

Open **PowerShell** and run:

```powershell
git clone https://github.com/briday1/tether-chat.git
cd tether-chat
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
powershell -ExecutionPolicy Bypass -File .\install-desktop.ps1
```

A **tether-chat** shortcut appears on your Windows desktop. Double-click **that shortcut** to launch tether-chat. It checks whether tether-chat is already running, starts the Python web server, MCP server, and reminder worker if necessary, waits until the web server is ready, and opens a standalone Edge/Chrome app window. You do **not** need to start `tether-chat.exe` manually each time.

For an existing installation, update it with:

```powershell
cd tether-chat
git pull
.\.venv\Scripts\python.exe -m pip install -e .
powershell -ExecutionPolicy Bypass -File .\install-desktop.ps1
```

**Important: Windows launcher vs browser-installed PWA.** Chrome/Edge's **Install app** option produces a browser-only shortcut that opens `http://127.0.0.1:8765`; it **cannot launch Python**. If the tether-chat server is stopped, that shortcut will show a connection error. Use the desktop shortcut created by `install-desktop.ps1` for automatic startup. Unpin or uninstall the browser-only shortcut if you have both and cannot tell them apart.

tether-chat uses local-only loopback connections. The server continues running after you close the app window so scheduled desktop notifications can work. To stop it, end the tether-chat processes or restart Windows; a tray stop control has not been implemented yet.

### Troubleshooting

If the desktop shortcut doesn't open tether-chat, first try running `.\.venv\Scripts\python.exe -m tether.desktop` from PowerShell to see the error. Check `%USERPROFILE%\.tend\server.log` and `%USERPROFILE%\.tend\desktop-launch.log` for startup details. If Python is missing, install Python 3.11+ and recreate the virtual environment before rerunning the installer.

## Notification planning without background AI usage

While you're chatting with tether-chat, the assistant can decide that a future **Bring to attention** notification is useful and save the trigger in SQLite. The notification worker checks those saved times locally every 20 seconds and delivers desktop notifications **without AI requests or token usage**. It never asks the model whether to send something. No autonomous token-consuming polling occurs between conversations.

AI-powered Attention-panel curation is separate: opening or refreshing the interface may call the configured model during that active browser session. Explicit scheduled notifications never need another model call.

## If an installed tether-chat app says "site not found"

A browser-installed PWA icon only opens the localhost URL; Chrome and Edge cannot start Python services from it. Use the **Windows desktop shortcut** created by `install-desktop.ps1` instead. It checks the local health endpoint, starts the tether-chat server if needed, waits for readiness, and then opens an app window.

If you previously installed tether-chat through Chrome or Edge, unpin or uninstall that browser-only app so you do not confuse it with the launcher. Re-run `powershell -ExecutionPolicy Bypass -File .\install-desktop.ps1` from the repository after updating. If the launcher fails, check `%USERPROFILE%\.tend\server.log` and `%USERPROFILE%\.tend\desktop-launch.log`.

### Windows command window stays open or closing it stops tether-chat

Update the repository and reinstall the editable package, then **stop any tether-chat server previously started in PowerShell** before using the desktop shortcut. If a console-launched server is already running, the shortcut will correctly reuse that server; closing its PowerShell window will still stop it. Start a fresh instance through the desktop shortcut so the parent process is detached. The launcher now also starts its child web, MCP and notification Python processes with Windows no-console flags and sends their output to `%USERPROFILE%\.tend\services.log`. Server-supervisor logs are at `%USERPROFILE%\.tend\server.log`. Recreate the shortcut with `powershell -ExecutionPolicy Bypass -File .\install-desktop.ps1` if needed.

### Fully windowless startup

The Windows shortcut starts `pythonw.exe -m tether.desktop`; the desktop launcher now uses `pythonw.exe` for its detached service supervisor as well. All service output is redirected to `%USERPROFILE%\.tend\server.log` and `services.log`. The tether-chat app window is the only window that should appear. If you still see a command window, close any tether-chat process started earlier from PowerShell and recreate the shortcut with `install-desktop.ps1`. Do not launch `.venv\Scripts\tether-chat.exe` to get background operation, because that is the terminal-oriented command.

## AI connection diagnostics

Conversation displays live, non-sensitive status lines while the assistant contacts its API provider and performs tools (for example, `Connecting to AI provider…` and `Tool: overview — completed`). These are streamed during the response, rather than leaving a static `Thinking…` indicator. Tool arguments, note contents, and API credentials are never included in these status messages. A failed request displays an error with Retry. Each provider request has a 22-second network timeout, and a multi-tool conversation can involve several sequential requests.

To troubleshoot your API key, model name, or custom GenAI.mil endpoint, open **Settings → AI connection → Test connection**. The test sends a small prompt to the configured provider; it uses API tokens, but it does not modify stored thoughts. A successful basic connection test does not guarantee that the model supports tool calling.

### Windows desktop icon

The shortcut installer now generates a multi-resolution `tether.ico` in the repository and assigns it to the Windows `.lnk` file, instead of borrowing the Microsoft Edge icon. Re-run `powershell -ExecutionPolicy Bypass -File .\install-desktop.ps1` to refresh an existing shortcut. Windows may cache old shortcut icons temporarily. The standalone browser window's title-bar/taskbar icon can still depend on Edge/Chrome app-window behavior; the shortcut itself uses tether-chat's ICO.

## Compact category list

The Board now starts with a compact list of categories and item counts. Select any category to see its tasks in the list immediately below, or select **All categories** to see everything. Searching narrows both the category list and task list. Tasks are prioritized for display when deadlines or attention dates are due, but remain editable in their detail panel. This avoids rendering an ever-expanding grid of every task at once.

If chat reports HTTP 404 for `/api/chat/stream`, an old server may still be bound to port 8765. Shut down the old tether-chat processes and relaunch the updated desktop shortcut; tether-chat now detects incompatible server capabilities at startup and displays a clearer error.

### Error: tether-chat port is already in use

If the running server has the current streaming chat API, launching `tether-chat.exe` again now reuses it rather than failing. If an **older** tether-chat server still owns port 8765, it must be shut down once to load the updated code. The Windows desktop shortcut now shows a visible error dialog instead of silently doing nothing. To identify the process in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object LocalAddress,OwningProcess
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in (Get-NetTCPConnection -LocalPort 8765 -State Listen).OwningProcess } | Select-Object ProcessId,Name,CommandLine
```

Verify the process command line really belongs to tether-chat before stopping it. Then close its original command window or stop **that specific verified PID** using `Stop-Process -Id <PID>` and relaunch the shortcut. Don't terminate all Python processes indiscriminately; other Python apps may be running. If the old tether-chat supervisor automatically relaunches the web worker, shut down that supervisor too using its known terminal/session before restarting.

### Diagnosing background service exits

The tether-chat supervisor now records the **specific child service** (web, MCP, or notifications) and process exit code when a service stops, and restarts it up to three times in a two-minute window. Repeated failures still stop the supervisor rather than creating an infinite restart loop. Check `%USERPROFILE%\.tend\server.log` for supervisor messages and `%USERPROFILE%\.tend\services.log` for subprocess errors. `KeyboardInterrupt` following Ctrl+C is expected when stopping a terminal-launched process; it does not by itself prove a code defect.

If your tether-chat database lives inside a OneDrive-synchronized folder, avoid concurrent synchronization or simultaneous tether-chat instances against the live SQLite file. A local folder plus regular SQLite backups is safer.

### Fix for a desktop shortcut that silently fails to start tether-chat

Older launcher builds invoked the service supervisor using `pythonw.exe`. The supervisor writes startup information to standard output, which can be missing under `pythonw.exe` on Windows. The desktop launcher now uses **`python.exe` with `CREATE_NO_WINDOW`**, redirecting output to `%USERPROFILE%\.tend\server.log`. The shortcut still uses `pythonw.exe` as its small, windowless launcher. Run `git pull` and reopen the desktop shortcut after closing any outdated tether-chat instances; this fix does not require reinstalling the shortcut. If it still fails, examine `desktop-launch.log`, `server.log`, and `services.log` in `%USERPROFILE%\.tend`.

## One-click Windows desktop launch and system tray

The `install-desktop.ps1` installer creates **tether-chat.lnk** on your Windows desktop. Double-click it to start tether-chat's local web/MCP/reminder services if needed, open tether-chat in a standalone browser app window, and keep a tether-chat icon in the Windows notification area (possibly under the taskbar's hidden-icons arrow). You can close the window and reopen it through the tray icon's **Open tether-chat** action or by clicking the desktop shortcut again. The shortcut is not the Chrome/Edge browser-installed PWA, which cannot start Python services.

The tray menu's **Exit tether-chat** stops the services launched by that tray instance. If tether-chat was already running outside the tray when opened, the menu says **Exit tether-chat tray** and doesn't stop those independently owned services. Startup errors are shown in a Windows dialog and logged at `%USERPROFILE%\\.tend\\desktop-launch.log`.

To install or update the desktop integration after `git pull`, run:

```powershell
.\\.venv\\Scripts\\python.exe -m pip install -e .
powershell -ExecutionPolicy Bypass -File .\\install-desktop.ps1
```

The installation includes the `pystray`, `Pillow`, and `psutil` dependencies needed for the Windows tray. The chat screen now shows **Loading conversation…** while history loads, with an explicit timeout/error message instead of looking stuck on an empty welcome message. The desktop launcher has not been verified on every Windows setup.

### Horizon icon refresh (desktop, tray, and browser)

tether-chat's header, browser favicon, app manifest, and system tray now use Horizon icon artwork from the same PNG renderer as the Windows shortcut's ICO. The installer writes `tether-horizon.ico` (a new filename to avoid stale Windows shortcut icon caches). Run `git pull`, then `powershell -ExecutionPolicy Bypass -File .\\install-desktop.ps1` to refresh the shortcut. **Fully exit the existing tether-chat tray instance before reopening**: an already-running tray process keeps its old icon and code. Hard-refresh the browser app if it shows an old favicon. Chromium's `--app` window may still display the Edge/Chrome taskbar identity instead of the page favicon, depending on the browser and Windows; the favicon cannot fully control native browser chrome.

## Native Windows tether-chat app (not an Edge window)

The recommended Windows installer now builds a proper **`dist\\tether-chat.exe`** using PyInstaller and a small native WebView2 window, then creates/updates the **tether-chat** desktop shortcut to point to that executable. Unlike `msedge.exe --app`, the Windows taskbar sees the native `tether-chat.exe` and can pin it independently of Edge. The native executable also sets the tether-chat app identity and uses the transparent circular Horizon icon for its executable/shortcut; the same image renderer supplies the system tray artwork and browser favicons.

Before installing, **exit any older tether-chat tray instance and stop the old local tether-chat server**. Run from PowerShell in the cloned tether-chat repository:

```powershell
 git pull
 powershell -ExecutionPolicy Bypass -File .\\install-desktop.ps1
```

The installer installs build dependencies into `.venv`, builds the executable locally and updates the desktop shortcut. Pin the resulting **tether-chat** application (or `dist\\tether-chat.exe`) to your taskbar, not Microsoft Edge. Future native code changes require rerunning the installer to rebuild the executable; ordinary web/app Python changes take effect on server restart after `git pull`. The `.venv` and repository must remain at their installed paths because `tether-chat.exe` starts the server from that environment. A Microsoft Edge **WebView2 Runtime** must be available on Windows; that is an embedded web runtime and does not make tether-chat an Edge taskbar application. Closing the native window hides it to the system tray; **Exit tether-chat** from the tray stops services started by the native app. An already running external tether-chat server is reused rather than terminated by the tray.

Note: this is a Windows-local build and has not yet been executed/tested in the user's Windows environment.

## Linked recurring actions and reporting

A recurring task can store a **due action** alongside its schedule and category. For example, tell tether-chat: “For my Weekly activity report, when it's due, summarize the last week's logged work in Projects.” tether-chat can store `due_action=activity_report`, `period=week`, and `category=Projects`. The task's reminder uses a deterministic SQLite activity query and includes the number of recorded events and a short sample without requiring a background AI call. The assistant can run the same report on request, and MCP exposes `set_task_due_action` and `run_task_due_action`. Reporting is based only on explicitly logged activities, not fabricated work. Configure a recurrence and the next occurrence time for recurring due notifications; categorizing a task alone does not automatically schedule it or link an action.

## Conversational AI context and tool progress

tether-chat does **not** upload the full SQLite database or entire lifetime conversation on each chat request. It currently sends the latest **10 conversation messages**, each limited to 3,000 characters, plus the current prompt and relevant tool results fetched during that request. Multi-step tool conversations still resend the growing current-turn tool transcript on each successive provider call, so multiple calls consume tokens. The separate Attention curation request supplies up to 80 candidate task summaries, not the whole chat history. Provider calls send this selected context to the configured external model service.

Tool progress is displayed in an expandable activity panel instead of dumping raw technical tool names into the response bubble; the activity remains available after the answer. tether-chat no longer stops after four/twelve reasoning rounds. Instead it skips repeated identical tool calls and requests a final response if looping or excessively many tool operations are detected. This is a safeguard against duplicated writes and runaway model use, not a provider-imposed server-side limit.

### No local action-count ceiling

tether-chat's conversational tool runner no longer imposes a four-, twelve-, or forty-call cutoff or forces an early summary based on a counter. It continues requesting model/tool steps until the provider returns a final response or a real error occurs. Identical repeated tool calls are not executed again within the same chat request, protecting against duplicate writes; the model receives a skipped-call result and can continue. Provider limits, request timeouts, and token costs still apply. If a model loops despite skipped calls, terminate the request or restart tether-chat and inspect its tool statuses.

## Tasks: inspect or modify an action

The former **Board** navigation item is now **Tasks**, with the same themed content background as Conversation. Open any task to edit **Action when due**. The task editor shows an editable **Action description / prompt**, the supported action type (currently a locally generated activity report), reporting period (week/month/quarter/year), category filter, **Bring to attention**, recurrence frequency and next occurrence. These fields are stored on the task's row in the SQLite `threads` table as `action_prompt`, `due_action`, `action_config`, `recurrence`, `next_occurrence`, and `revisit_at`. The action description is informational text: it is not executed as arbitrary AI instructions in the background. The linked activity-report action queries logged activities without consuming AI tokens. Choose **Preview report** after saving the configuration to inspect the available activity data.

## Reliable shutdown from the native tether-chat system tray

**Exit tether-chat** now takes a snapshot of the processes owned by the native launcher (supervisor, web server, MCP server, reminder worker, and any nested Python virtual-environment subprocesses), terminates descendants before parents, waits briefly, then force-stops any remaining owned children. It does **not** indiscriminately kill Python or terminate an independently running tether-chat server that the native app did not start. The Python supervisor uses the same child-tree cleanup when it exits normally or handles Ctrl+C. This prevents the old orphaned-process/port-8765-or-8766 issue on ordinary shutdown.

Because `tether/native.py` changed, **rebuild the native executable** after pulling: close the tray instance, run `git pull`, then `powershell -ExecutionPolicy Bypass -File .\\install-desktop.ps1`. Launch the new `dist\\tether-chat.exe`; right-click its tray icon and select **Exit tether-chat**. Both ports should then be free: `Get-NetTCPConnection -LocalPort 8765,8766 -State Listen -ErrorAction SilentlyContinue` should produce no rows, provided no independent server is running. On unexpected hard crashes or forced process kills Windows may not execute normal cleanup; those situations remain outside guaranteed graceful shutdown.

## Archiving tasks

In **Tasks**, use **Archive task** in a task's detail panel. Archived tasks are retained in SQLite with their notes, activity history, and schedule, but hidden from the normal Tasks list, daily attention, and scheduled reminders. Use **View archive** above the category list to browse and search archived tasks, then **Restore task** to return one to the active list. The assistant can archive or restore tasks upon explicit request or clear indication that an item should be put away; this is not automatic cleanup of recurring work. MCP exposes `archive_task`, `restore_task`, and `list_archived_tasks`. Task headings show their current matching counts inline, like **All Tasks (4)**. Task rows use compact, single-title-first styling.

## Visual UI reference screenshots

The repository includes `scripts/capture_screenshots.py` and a manually triggered GitHub Actions workflow, **Refresh tether-chat UI screenshots**. The script creates an isolated temporary SQLite database containing synthetic task and conversation examples, launches a local tether-chat web server on port 18765, captures Chromium screenshots with Playwright, and shuts the temporary server down. It never uses your personal tether-chat database or AI provider key. Screenshot files are written to `docs/screenshots/`: `conversation.png`, `tasks.png`, `task-details.png`, and `archive.png`.

To generate them locally:

```powershell
.\\.venv\\Scripts\\python.exe -m pip install playwright
.\\.venv\\Scripts\\python.exe -m playwright install chromium
.\\.venv\\Scripts\\python.exe scripts\\capture_screenshots.py
```

Commit those generated PNGs if you want to keep them in GitHub. Alternatively, run **GitHub → Actions → Refresh tether-chat UI screenshots → Run workflow**; the workflow generates and commits updated reference images on the default branch. These screenshots are reproducible examples rather than live captures from your Windows machine. When discussing UI issues in ChatGPT, link the corresponding `docs/screenshots/*.png` file or attach the image so we can inspect the actual layout. Screenshots should be regenerated after relevant UI changes.

## Chat calendars and overlapping categories

Calendar requests now return an embedded, read-only response with task inspection and PNG/SVG downloads. There is no separate Snapshots navigation or date-editing toolbar. The iframe reports its measured content height to its same-origin parent using `tether:snapshot-size`; the parent validates the sender before resizing it. Weeks and months size independently. Phone week views use day rows. Multi-day calendars retain Monday–Friday and add weekend columns only when tasks or recorded activity occur on them. Downloads preserve the requested dates and category filter, use stable category colors, and expand to include all tasks rather than dropping overflow.

The `thread_categories` table stores ordered memberships. Startup migrates existing `threads.category` values without dropping data and does not overwrite established memberships on later starts. Every task response includes `categories`; the legacy `category` field mirrors the first membership. Updating legacy `category` intentionally replaces all memberships with that one category. Updating `categories` replaces the list; an empty list returns the task to Unsorted. The MCP `set_task_categories` and chat `set_categories` tools also support additive and removal edits under a write transaction. Category groups can overlap; All Tasks deduplicates by task ID. Category filters for snapshots and linked activity reports match any membership. Archived tasks keep their memberships and activity history, but their current deadlines do not appear as active calendar obligations.

Refresh screenshots with `python scripts/capture_screenshots.py`. The script uses isolated synthetic data, exercises a task with multiple memberships, verifies unique task counts, checks frame sizing on desktop and mobile, opens read-only details, and downloads both formats. Calendar-only images are captured at the content bounds, independently of the browser viewport.

## Source-package rename

The Python implementation is now `tether/`; imports and module launches use
`tether`, and the distribution remains `tether-chat`. The snapshot skill is
`skills/tether-snapshot/`. New environment settings use `TETHER_*`; existing
`TEND_*` settings are still accepted, with `TETHER_*` taking precedence.

Existing data is intentionally not moved: `~/.tend`, `tend.sqlite3`, the OS
credential-vault service name, and saved browser theme keys keep their historical
identifiers. This avoids losing tasks, API settings, or themes on upgrade.
A small `tend.py` compatibility loader keeps older `python -m tend.native`
shortcuts working until they are recreated; no `tend` executable is installed.
