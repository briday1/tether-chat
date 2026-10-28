# Household sharing through Google Drive and Sheets

**tether-home** is the Home-only browser application. **tether-chat** is the installed Work-only application and includes no Drive integration. Both belong to **tether**. The hosted URL stays unchanged for existing installations and OAuth.

Each browser keeps its own local database. One explicitly selected Google Sheet in Drive carries an append-only journal of immutable changes, **not a live SQL database or Google Calendar events**. The app uses only `drive.file`, not permission to browse your whole Drive.

## Set up a household

1. Open **Share Home → Connect Google Drive** using your own Google account. No separate tether account is needed.
2. Confirm sharing your existing Home tasks and notes, then choose **Create shared household** and give it a name. A clearly named Sheet is created with a dedicated Journal tab.
3. Choose **Share household in Google Drive**. In the Sheet, click **Share**, enter your partner’s email as an **Editor**, and send Google’s invitation. Copy household link is optional; a link alone does not grant access.
4. Your partner connects their own Google account, chooses **Join shared household**, and selects that same Sheet in Google Picker. Existing local Home records are merged, not silently replaced. Each additional device joins the same way.
5. Edits sync while the app is open. The screen shows last successful sync and any conflicts. “Connected” describes this device, not proof another person has connected. Expired Google authorization requires reconnecting; offline edits remain local.

Do not manually edit, sort or delete Journal rows. They contain change history rather than a readable task table. Drive Editors can alter the Sheet outside tether; this is not cryptographic tamper protection. Invalid or inconsistent data pauses sync instead of overwriting local work.

Setup progress is retained locally without tokens or task contents. **Resume setup** continues confirmed steps. An uncertain creation is never automatically repeated; check Drive before forgetting pending setup. Forgetting setup does not delete existing Sheets. Pause prevents further requests but cannot cancel a request already received by Google.

## Data boundaries

Only Home tasks, categories, dates, statuses, task items and action notes sync. Work, conversations, provider settings, API keys, AI instructions, notification claims and activity records are excluded. Earlier browser Work data remains available through explicit Settings recovery/export; it is never silently moved into Home. Importing a Work or unlabelled backup into Home requires separate informed confirmation.

Anyone with access to the Sheet can read its journal, including earlier task contents. Disconnect keeps local data and the Sheet; revoke another person’s access in Google separately. Deletion is a journal tombstone, not permanent erasure of all historical copies. Home/Work product separation does not prevent someone with device access from reading local data.

Google access tokens remain only in memory. They are not stored in localStorage, databases, backups or the journal. Public app configuration, device identity and pending setup references are stored locally. Provider credentials never enter shared records.

## Append safety and limits

Each operation has a unique ID and causal per-field versions. Different-field edits merge; concurrent edits to one field retain both values for explicit resolution. Tombstones prevent old offline copies from silently resurrecting deleted tasks. Local snapshots and sync metadata commit atomically with compare-and-swap, preserving local edits made during a request.

Google Sheets `values.append`, with `RAW` and `INSERT_ROWS`, appends complete operations without computing row positions or replacing existing cells. Requests are atomic. Lost-response retries may create duplicate rows; exact duplicates are deduplicated by operation ID and chunk content. Conflicting duplicates, missing chunks, invalid records or missing causal history stop sync. The app never sorts, clears or updates existing journal rows.

JSON operations are split into cells of at most 30,000 characters and bounded append requests. The app caps an individual operation at 1 MiB, journal responses at 8 MiB and grid size at 50,000 rows. It reads bounded pages, adapts polling to journal size, and backs off on quota responses. Limits pause sync while local edits remain safe; automatic history compaction is not implemented.

The old mutable JSON-file/ETag transport is not used. No Google conditional media-update behavior is assumed.

## Publisher Google setup

Configure one dedicated project for all household users:

1. Enable **Google Drive API**, **Google Picker API**, and **Google Sheets API**.
2. Configure OAuth consent with the non-sensitive `https://www.googleapis.com/auth/drive.file` scope. External apps in Testing need explicit test users and Drive authorizations expire after seven days; handle production status and any required verification appropriately.
3. Create an OAuth **Web application** client for exact JavaScript origins, including `https://briday1.github.io`. For local browser development, configure `http://localhost` and the exact development port. No client secret or token-exchange backend is used.
4. Configure the public client ID and project number in `web/drive-config.json`.
5. Create a website-restricted Picker browser API key with the required app referrers and Google’s documented `https://docs.google.com/*` referrer. Restrict its API use to Picker. Sheets requests use the user’s OAuth bearer token, not this key.
6. Save that key once as repository Actions secret **TETHER_GOOGLE_PICKER_API_KEY** (the existing **TETHER_GOOGLE_API_KEY** name is also accepted). The Pages publication workflow injects it immediately before building. The resulting browser key is necessarily public, so publication requires approval and appropriate restrictions. The desktop package never receives it. Never put client secrets or tokens in frontend configuration.

PR tests never receive the publisher key. Missing configuration stops browser publication. Household members use the configured app and do not create Cloud projects or type keys; App setup is a development fallback.

## Verification

Automated tests cover immutable merge/conflicts/tombstones, offline and duplicate replay, chunk corruption, quota limits, Home-only privacy, interrupted setup, and a two-context mocked Google/Picker UI flow. **Mocks are not real Google verification.** Real two-account sign-in, Picker access, Sheets creation/append, revocation and concurrent devices still require a mediated test with configured Google accounts.

Official documentation:
- https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append
- https://developers.google.com/workspace/sheets/api/limits
- https://developers.google.com/workspace/sheets/api/quickstart/js
- https://developers.google.com/workspace/drive/picker/guides/web-picker
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://developers.google.com/identity/oauth2/web/guides/use-token-model
