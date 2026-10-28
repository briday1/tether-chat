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

## Optional household AI connection (browser)

Settings starts with one Household section: name it and save a provider/model/key
for solo use. Drive is optional. Expand **Share household** to connect Google,
create or join the selected Sheet, and grant the other member Editor access.
To share AI as well, explicitly confirm **Encrypt and share AI connection** with
a long, separate household passphrase. Copy the household invitation and give
the passphrase separately. The invitation contains only a Sheet ID and name;
it grants neither Google access nor access to a key.

The recipient opens the invitation, connects their own Google account, selects
the invited Sheet, and confirms merging Home tasks. They enter the passphrase,
review the full provider address/model, and explicitly choose **Use for this
session**. Their personal connection is preserved. The decrypted household key
is not written to browser storage or backups; reopen/reload requires unlocking
again. Lock household AI to return to the personal connection. Google access
expires separately and needs reconnecting for sync.

Use a dedicated spending-limited provider key and check that its provider permits
sharing and direct browser requests (CORS). Every recipient can extract the key.
A passphrase holder can also publish a different provider configuration: verify
any change out of band before approving it. Tether does not automatically accept
shared AI updates or send a key to an unapproved changed endpoint.

The optional encrypted bundle is stored in a separate **Household AI** tab, not
in task records, AI prompts, task sync, or portable backups. Versions are
append-only; concurrent changes require an explicit new publication instead of
silently picking a winner. Old encrypted versions and downloaded copies may
remain. To revoke a key, revoke or rotate it at the provider: changing a
passphrase or Sheet permission does not revoke copies. A failed/inconclusive
upload may have completed; inspect/reload before publishing another version.

### Security and interoperability notes

The bundled maintained `jose` library implements compact JWE:
PBES2-HS512+A256KW wrapping and A256GCM authenticated encryption. Version 1 fixes
PBKDF2 at 220,000 iterations, uses a random 16-byte salt and a library-generated
unique nonce, and authenticates the household and revision IDs. Malformed or
unsupported algorithms/parameters and oversized payloads are rejected before
key derivation. Passphrases are not saved; there is no remember-device option
for shared keys. This protects stored ciphertext, not a compromised browser,
malicious extension, weak passphrase, or authorized member. A browser cannot
prove that a public DNS name resolves only to public hosts. HTTPS, explicit
endpoint confirmation, no URL credentials, and redirect rejection are enforced.

Tests use synthetic Google responses and synthetic keys only. Real Google
consent, provider CORS, mobile performance, and account-specific permissions still
need user verification; no test authorizes credential publication to real Drive.
