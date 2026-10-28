# Sharing options (design exploration)

Tether currently stores each Work/Home workspace locally. It does not provide a
shared database, account invitations, cross-device synchronization, or permissions.
Choosing Home is an organizational choice, not a security boundary.

For genuine simultaneous editing, the recommended design is an optional service
that owns its database and exposes an authenticated API. Clients would share an
explicitly selected workspace, with invitations and roles, stable record IDs,
revision checks, conflict handling, deletion records, and backups. Existing local
workspaces should remain local until their owner explicitly chooses to share.
Provider credentials must not be included in shared task data.

Do not put the live SQLite database in a Google Drive synchronized folder for
multi-user editing. File copying does not provide database locking or transaction
coordination between computers, and competing copies can lose changes or corrupt
the database. See [SQLite guidance on remote database files](https://www.sqlite.org/useovernet.html).

Cloud storage could instead hold deliberate portable exports or a purpose-built
sync format with version checks and conflict resolution. That would be a separate
feature, not safe automatic sharing of the existing SQLite file. Today's portable
export contains task and conversation data from the selected workspace, so review
it before sending it to another person. It excludes provider credentials.

No server, cloud storage grant, data upload, or sharing permission was created by
this change. Before implementation, choose the recipients, workspace, read/edit
permissions, hosting, and conflict behavior.
