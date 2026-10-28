# Home sharing through Google Drive

This backend-free implementation keeps each device's local database. Drive carries versioned change journals, **never a live SQLite database**. It uses the narrow `drive.file` scope; selecting a folder is not assumed to authorize all child files.

## Household setup

1. Connect Google Drive in Home → Share Home. Each person uses their own Google account.
2. In Drive, create a dedicated Home folder and share it with the other person as an editor. Tether does not change sharing permissions.
3. Each browser/device chooses this folder through Google Picker and creates its own sync file. Confirm that existing Home task data will be shared.
4. Each person selects the other device's actual sync file through Picker. This authorizes precisely those files. Adding another device requires selecting its new file too.
5. Keep the app open. It checks about every 30 seconds. Tokens expire; reconnect when asked. Offline edits remain local.

The publisher configures Google once; ordinary household members should not need their own developer project. `tend/drive-config.json` supplies the public OAuth client ID, project number, and restricted browser Picker key for shipped builds. Empty defaults show App setup fields as a development fallback. Never put a client secret, service-account key, access token, or refresh token in that file.

Desktop Google authorization happens in the **system browser**, not the embedded desktop webview. Open the sharing browser page from the app and leave it open to sync the same local Home database. Browser edition keeps sync in the shell when navigating between its screens. Closed apps do not continuously sync.

## Privacy and shared data

Only Home tasks, categories, dates, statuses, task items, and action notes sync. Existing Home data requires explicit confirmation. Joining merges shared records into existing Home instead of replacing the database. Work, conversations, provider settings, API keys, AI instructions, notification claims, and activity records are excluded.

Anyone with Drive read access to the shared files can read their JSON task data. Home/Work organization is not encryption or protection against somebody with device access. Disconnect preserves local data and Drive files; revoke a person's access in Google Drive separately.

Access tokens stay in memory. They are not stored in localStorage, SQLite, backups, or journals. Public app configuration and the device's writer binding are stored in that browser. The writer binding is never taken from a shared file, portable backup, or restored SQLite database. A new browser/device creates a new writer file; selecting a peer file does not make it writable by that device.

## Safe journal updates

Each device writes only its own journal. A journal contains immutable operations with unique IDs and causal field versions. It also replicates operations learned from peers so history remains complete. Devices merge different-field edits; simultaneous edits to one field retain both values for the user to resolve. Deletion history prevents old offline copies from silently resurrecting removed tasks. Editing a child item also protects against concurrent deletion of its parent.

Local snapshots and sync metadata use one compare-and-swap transaction. If tasks change during a network request, sync retries instead of replacing those edits. Local changes are journaled before network access. Duplicate deliveries and uncertain-upload retries are idempotent. Conflicts, missing history, corruption and oversized payloads pause sync without discarding local changes.

Replacing a journal requires a fresh strong ETag and `If-Match`. Before any task data is uploaded, Tether probes a newly created **empty** journal using an intentionally wrong ETag and requires HTTP 412. If Google does not expose the ETag through CORS or does not enforce the precondition, uploads stay disabled. The probe does not run against an existing populated journal. This check must be verified against real Google accounts before production readiness is claimed.

History is retained, not compacted automatically. Individual journals have an 8 MiB safety cap and bounded operation count. Hitting a limit pauses sync with local edits preserved; future compaction requires explicit acknowledgement rules across devices. No arbitrary last-writer-wins data loss is used.

## Publisher Google setup

Use one dedicated Google Cloud project:

1. Enable **Google Drive API** and **Google Picker API**.
2. Configure OAuth consent and the non-sensitive `https://www.googleapis.com/auth/drive.file` scope. While in testing, add intended test accounts explicitly.
3. Create an OAuth **Web application** client. Add exact authorized JavaScript origins, such as `https://briday1.github.io` and `http://localhost:8765`. A desktop server running on another port needs that exact origin configured too. This token model uses no client secret or token-exchange backend.
4. Obtain the Cloud **project number** for Picker `setAppId`.
5. Create a browser API key restricted to the necessary APIs and website referrers. Google's Picker documentation requires the application referrers plus `https://docs.google.com/*`; use Google Picker API and Drive API restrictions as appropriate.
6. Put only the public client ID/project number/restricted browser key into the public config through an authorized configuration step. Never paste secrets into chat or commit secret credentials.

No project, grant, key, or folder is provisioned by the code changes themselves.

## Verification status

Automated tests cover journal validation, merging, conflict resolution, deletion, local races, restart, revoked/expired access responses, uncertain writes, writer ownership, conditional updates, privacy, and explicit-file discovery. A hosted mock-Google/Picker UI test exercises connection, selection, consent, sync, navigation, reload, and disconnect without contacting Google.

Real two-account sign-in, Picker grants to spouse-owned files, CORS/ETag access, conditional media PATCH, revoked access and actual device behavior still require verification with configured OAuth. Do not describe mock tests as successful real Google integration.

Primary documentation:
- https://developers.google.com/workspace/drive/picker/guides/web-picker
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://developers.google.com/workspace/drive/api/guides/handle-errors
- https://developers.google.com/identity/oauth2/web/guides/use-token-model
- https://developers.google.com/identity/protocols/oauth2/native-app
