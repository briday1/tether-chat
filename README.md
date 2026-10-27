# tether.

[![PyPI version](https://img.shields.io/pypi/v/tether-chat)](https://pypi.org/project/tether-chat/)

A local-first assistant for tasks, action items, and things worth remembering. Talk naturally; your work and conversation stay in a local SQLite database.

![tether-chat conversation](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/conversation.png)

## Browser app

[Open tether in your browser](https://briday1.github.io/tether-chat/) — including on your phone. On iPhone, open it in Safari and choose **Share → Add to Home Screen**.

The browser edition runs on your device, with no tether server or Python installation. Enter your own API endpoint, model, and key in Settings. Your provider must allow browser requests (CORS). Tasks, action notes, conversations, and calendars stay in this browser; saved tasks work offline after the app has loaded once. AI requests still need internet.

Keys can stay in your browser session or be saved encrypted with an unlock passphrase. Download portable backups from Settings: clearing website data removes browser tasks. Desktop and browser data are independent; they do not sync automatically. Closed-app reminders, the local MCP server, and database folder selection belong to the desktop edition.

Both editions are released from this repository. [Browser setup, backups, and development](docs/BROWSER.md).

## Install

Requires Python 3.11 or newer. No PyInstaller build or separate Windows `.exe` installer is required.

Install the desktop app from [PyPI](https://pypi.org/project/tether-chat/):

```sh
uv tool install --reinstall "tether-chat[desktop]"
tether-chat-desktop
```

The install exposes only **`tether-chat`** and **`tether-chat-desktop`**. On Windows, `tether-chat-desktop` opens a native WebView2 window and remains in the tray after the window closes. Choose **Open tether** to return or **Exit tether** to stop it. The Microsoft Edge WebView2 Runtime is required. macOS and Linux open the browser UI and use a tray/menu-bar entry where supported by the desktop environment.

**Browser/server mode:**

```sh
pip install tether-chat
tether-chat serve --port 9000 --mcp-port 9001
```

Without custom ports, the browser UI is at `http://127.0.0.1:8765` and the local MCP server is at `http://127.0.0.1:8766/mcp`. Use `--no-browser` to start without opening a window. Both services are local-only; Ctrl+C stops a terminal-launched server.

**Optional desktop shortcut:**

```sh
tether-chat desktop install
tether-chat desktop install --destination "/path/to/shortcuts"
```

The default destination is your operating system's Desktop folder. Windows gets an icon-branded `.lnk`, macOS a `.command` launcher, and Linux a `.desktop` entry. Keep the Python/uv environment that the shortcut references. Linux may require marking the launcher trusted. Add `tether-chat-desktop` to your OS login/startup applications to launch at sign-in; installing it does not enable startup automatically.

For desktop installation with pip, use `pip install "tether-chat[desktop]"`.

## Set up and use

Open **Settings → AI connection**, enter your provider's HTTPS API base URL, model, and API key, then save and test. The provider must support OpenAI-compatible chat-completions tool calling. Desktop keys use the operating system's credential vault; they are not stored in your task database.

**Conversation:** Describe work to track, ask for an update, or record feedback. You can switch to Tasks while a reply is running. Requests are queued on the local server, and returning to Conversation restores their progress or completed replies. A full server shutdown interrupts in-flight requests rather than automatically repeating potentially mutating operations.

**Voice input:** Click the microphone beside Send, speak, then stop and review the text before sending. Both desktop and browser editions support browser dictation and a recorded-audio fallback. In **Settings → Voice input**, choose the mode, dictation language, and provider transcription model. Recorded transcription uses your existing key and requires your provider to support `audio/transcriptions`; it does not change your chat model. Cancel discards a recording and releases the microphone.

**Tasks:** Browse **Categories → Tasks → Action items**. Each task may have several categories and several action items. Individual action items have their own due date and **Bring to attention** time. Click an action row to open its details drawer, including its own notes. Add, edit, or remove a note there; notes stay attached to that action and are included in its check-in context.

**Attention:** Click an item or focus it and press Enter. This sends a contextual check-in to Conversation and asks for your update; it does not silently mark anything complete or change dates. Action-item attention stays scoped to that action, rather than its siblings or category.

**Calendars:** Ask “give me my next week snapshot” or use `/snapshot last month`. The calendar appears inside chat, with transparent day cells and category-colored task blocks. Monday–Friday remain visible; weekends appear when they contain work. PNG and SVG buttons export the calendar.

**Archive:** Put finished or inactive tasks away without deleting them; restore them from **View archive**.

## Update

Choose **Exit tether** in the tray before replacing a running installation:

```sh
uv tool upgrade tether-chat
```

Run `tether-chat desktop install` again to refresh an existing shortcut. Existing data and provider settings remain in `~/.tend`; this does not install a legacy `tend` command.

## Releases

Main releases use **YYYY.sequence**: `2026.1`, `2026.2`, and so on, restarting at `2027.1` in the next year. `python scripts/bump_version.py` updates both package and runtime versions. Commit that version bump with the main update; a separate manual publish is not required.

The main release workflow validates the version, runs Windows/macOS/Linux tests and isolated installations, checks browser interactions, builds the wheel and source archive, creates the versioned GitHub release, and attempts PyPI publication using `PYPI_API_KEY`. It confirms the uploaded version before reporting PyPI success.

A separate **Browser app and GitHub Pages** workflow builds and tests the standalone browser edition and publishes it to Pages. It uses the same version, interface, AI prompt, and tool declarations as desktop. Browser publication is independent of the PyPI upload.

## More screenshots

These desktop screenshots use synthetic example data, never your personal tasks.

**Categories and tasks**

![Category buttons and task list](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/tasks.png)

**Action items in the third column**

![Categories, tasks, and clickable action items](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/task-action-columns.png)

**Details in a chat drawer**

![Action details in a themed chat drawer](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/chat-action-drawer.png)

**Week and month calendars**

![Week calendar inside chat](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/snapshot-week.png)

![Month calendar inside chat](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/snapshot-month.png)

**Task details and archive**

![Task details](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/task-details.png)

![Archived tasks](https://raw.githubusercontent.com/briday1/tether-chat/main/docs/screenshots/archive.png)

## More information

See [development and troubleshooting](https://github.com/briday1/tether-chat/blob/main/docs/DEVELOPMENT.md) for database backups, MCP configuration, and server setup. The repository also includes a [snapshot skill](https://github.com/briday1/tether-chat/blob/main/skills/tend-snapshot/SKILL.md) for compatible AI clients. Screenshots are regenerated by the screenshot workflow.
