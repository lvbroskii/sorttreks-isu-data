# Public capture security - v0.4.1

An automatic approval review blocked the initial GitHub tree upload because the
captured official ISU HTML contains an embedded access-token field. The tree was
not committed to the repository branch. The repository was initialized with its
README only before this block.

The public project now removes token/authorization values from source bodies
before writing files or invoking the raw archive sink. This handles ordinary JSON
and escaped Next Flight JSON. Schedule IDs, event identity, race timestamps and
athlete records are preserved. The immutable archive refuses unsanitized legacy
bodies rather than publishing them.

For changed responses, `sha256` identifies the public stored body;
`originalResponseSha256` records the original response hash, and
`credentialsRedacted` is true. Historical HTML fixture hashes and archive paths
were migrated, retaining original-response hashes in metadata. Schedule/heat JSON
captures without credential fields remain byte-identical.

Public HTML captures are therefore source captures with explicit security
redactions, not a claim to preserve secret-bearing responses byte for byte.
The previous ZIP should not be uploaded publicly; use v0.4.1 or later.
No token was used to authenticate a request, and monitoring was not activated.
