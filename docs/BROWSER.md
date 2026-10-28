# Browser edition

Open <https://briday1.github.io/tether-chat/>. No Python, desktop process, or tether backend is required. GitHub Pages serves static files; task operations run on your device, and AI requests go directly to the provider you configure.

![Browser task view with synthetic example data](screenshots/browser.jpg)

## Phone installation

On iPhone, open the app in Safari and use **Share → Add to Home Screen**. Other supported browsers offer **Install app** in their browser menu. The app caches its interface after the first online visit, so tasks, notes, activity, deterministic slash commands, and calendars remain available offline. AI chat requires internet.

## App updates

Use **Settings → Update app** to load the latest browser release. It checks for an active chat before switching versions and preserves local tasks, notes, conversations, drafts, and saved credentials. The app checks for new releases when you return to it and shows an available update in Settings.

If an older release stays cached, open [Update tether](https://briday1.github.io/tether-chat/update.html) in the same browser where you use tether. This independent update page works while other tether tabs remain open. It waits for an active chat to finish, downloads the latest interface, and opens the updated app. Keep using the same browser and origin to retain your existing local data.

## AI connection

Use an HTTPS OpenAI-compatible chat-completions endpoint with tool calling. The provider must permit the app's origin through CORS, including the Authorization and Content-Type headers. A provider that works with the desktop Python client may reject browser requests. Test the connection in Settings. The browser edition includes no proxy, and never sends your key to GitHub or a tether backend.

Enter the provider API base URL and API key. Available model IDs load automatically from that connection's `/models` endpoint; choose a suggestion in **Model**, or enter an ID manually if the provider does not list models. The selected model must support chat completions and tool calling. Model discovery does not save credentials or generate a chat response.

**Save connection** applies the connection immediately. **Test connection** saves the entered fields first, so a separate Save click is optional. Chat waits for an in-progress save, including key encryption; a reload is not needed. Changing the URL requires entering a key for the new endpoint; a blank key leaves your previous connection intact and asks you to re-enter it. Model-only edits retain the current key and its encrypted backup. If chat needs a missing or locked key, Settings opens and your unsent message stays in the draft.

Provider errors distinguish temporary rate limits from exhausted API credits or account/project limits. Billing and quota errors are not automatically retried. Temporary limits honor `Retry-After`; longer waits are shown so you can retry later. For OpenAI, use `https://api.openai.com/v1` and check API billing separately from your ChatGPT subscription if an error reports insufficient quota or an empty credit balance.

By default a key stays in session storage for this browser session. Optionally save it encrypted with a passphrase of at least eight characters. Persistent storage contains only a PBKDF2-derived AES-GCM ciphertext, salt, and nonce. The unlock passphrase is not saved. Locking removes the session key. Forgetting removes both saved and session keys. Changing the provider URL clears the unlocked key unless you explicitly supply a key for the new URL. Like any web app, scripts running in the app's origin can access an unlocked session; the browser is not an operating-system credential vault.

AI requests use a short recent conversation window and retrieve task context through tools. The tool declarations and system prompt are extracted from the desktop source during the build. Identical tool calls are not executed twice. Task operations commit to IndexedDB before the model is told they succeeded.

## Voice input

Click the borderless microphone once to start and again to stop. Its color changes while listening, and recognized words appear in the draft as you speak. × discards this dictation and restores the text that was already there. Manually editing the draft stops dictation and preserves your edits. Voice never sends a chat automatically.

Both editions default to **On-device speech · English** using open-source Vosk in a WebAssembly worker. No Python speech package, tether backend, provider transcription endpoint, or API key is needed. Microphone audio stays on this device. First use downloads a pinned Vosk runtime from jsDelivr and the small English model from the Vosk browser project's GitHub Pages (about 45 MB total). The runtime is integrity-checked and cached; Vosk stores its model in IndexedDB. Later use works offline unless the browser has cleared those files. Speech files are separate from task backups.

Wait for **Listening** before speaking, especially during first setup. HTTPS or localhost and microphone permission are required. Stopping, cancellation, errors, switching screens, or hiding the app releases the microphone and worker. Audio is not saved to tasks or backups.

**Settings → Voice input** also offers Browser dictation and its language setting. This mode may use the browser's speech service. Existing Automatic and Provider transcription preferences migrate to on-device speech; the app no longer sends microphone audio to your AI provider.

## Local data and backups

Tasks, entries, action notes, activity, relations, chat history, and jobs use a database scoped to the app's deployment path. IndexedDB transactions prevent simultaneous tab edits from overwriting unrelated changes. **Protect local storage** asks the browser to retain the database; browser settings and clearing website data can still remove it.

Use **Settings → Download backup** regularly. Portable JSON backups include all task data and conversations, but no provider settings, API keys, or queued jobs. **Import backup** validates the full file and merges new records in one transaction. Identical IDs are accepted once; conflicting versions or broken references reject the entire import and retain current data. To preserve two conflicting versions, import the other backup into a separate empty browser profile. The import UI accepts files up to 20 MB.

Attention refreshes after task and action edits, notes, and chat updates, including changes saved before a chat failure. Other open tabs receive change notifications; a three-second refresh also catches time-based reminders and outside changes. Completed, archived, or rescheduled items reflect their current state. An AI suggestion is discarded when its source task changes; scheduled reminders still appear when due. Automatic refresh uses saved data. The reconsider button requests a new AI selection.

To copy existing desktop data into the browser, update the desktop package and run:

```sh
tether-chat export --output tether-portable-backup.json
```

The command creates a new file and refuses to overwrite an existing file. Import it using the browser's Settings. A running desktop server also provides a portable download at `/api/portable`; its normal SQLite backup at `/api/backup` remains available. Browser JSON files are browser-importable backups, not replacements for desktop SQLite databases. Automatic desktop/phone sync is not included.

## Requests and reminders

One persistent parent page owns the AI queue while Conversation and Tasks use the shared desktop screens. Switching screens does not cancel requests. Requests have durable IDs and are serialized across tabs using Web Locks. Closing or reloading the entire app interrupts a running request; tether marks it interrupted and never automatically repeats potentially mutating tool calls. Queued requests can resume. Review any saved changes before explicitly retrying.

Due items appear in Attention. Clicking an item asks a read-only question about that task or selected action. **Reconsider what deserves attention** explicitly asks the model to curate additional task choices; routine background refreshes never spend AI tokens. Optional notifications work while the app remains open. Closed-app push reminders and always-running background AI require a separate service and are not part of this release. The local MCP server, desktop tray, and database folder controls remain desktop features.

## Releases

The existing `publish-pypi.yml` continues producing the desktop wheel and source archive, including Windows/macOS/Linux validation. `web-pages.yml` is a second, independent workflow: it tests the browser engine, runs real browser checks with a synthetic provider, builds static files, uploads the artifact, and deploys Pages. Both use the version in `pyproject.toml`.

For initial repository setup, GitHub Pages must use **GitHub Actions** as its publishing source. The workflow attempts to enable Pages automatically. If the repository token lacks permission to enable Pages, set **Settings → Pages → Source → GitHub Actions**, then rerun **Browser app and GitHub Pages**. No API keys belong in the workflow or static output.

Service-worker caches contain only bundled public application assets. Provider requests, API keys, and task data are never cached as HTTP responses. A new release waits until older app sessions close before activating, keeping active sessions on a consistent set of files. Close all tether browser windows and reopen to pick up an installed update.

## Build and check

```sh
python -m pip install Pillow pytest
python scripts/build_web.py --base-path /tether-chat/
node --test tests/web/*.test.mjs
python -m pytest -q tests/test_browser_build.py
```

The generated `web-dist/` is the Pages artifact; it is not the desktop package or a second copy of the source screens. Local root hosting can use `--base-path /`. Serve the output over HTTPS or localhost; Web Crypto, Web Locks, service workers, and installation require a secure browser context.

On a normal development machine or hosted CI runner, install Playwright and Chromium and run `python scripts/check_web_ui.py`. This checks the real static build at a repository subpath, IndexedDB, desktop imports, scoped action notes, encrypted keys, navigation during AI calls, exports, mobile layout, and fresh offline loads with a synthetic provider. No real API key or user task database is used.
