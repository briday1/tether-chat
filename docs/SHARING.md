# Household sharing

The Home-only **tether-home** browser application offers optional experimental
Google Drive collaboration without a tether backend. The installed **tether-chat**
application is Work-only and does not include this integration.

See [Drive sharing setup, safety checks and limitations](DRIVE_SYNC.md). Each
device keeps local data and writes its own selected journal; the app merges
immutable changes and preserves conflicts. Google sharing permissions remain
under your control. No Google Calendar integration is included.

Never place a live SQLite database in a Drive-synchronized folder for concurrent
editing. Drive journals are a separate sync protocol, not database-file sharing.
Portable backups can contain private conversation data; do not use them as shared
household journals. Provider credentials are excluded from portable task backups
and Drive task journals.
