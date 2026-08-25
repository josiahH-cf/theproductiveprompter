# Repository-native scheduled articles

Scheduled Article Flow releases are staged as private draft releases in this
repository. Each draft contains a hashed run bundle and a manifest that pins:

- the earliest UTC publication instant and its display timezone;
- the Article Flow run and package revision;
- the exact publication-plan and article hashes;
- the clean repository commit from which publication is allowed; and
- the controller-scoped authority for that one release.

The checked-in workflow polls for due drafts just before five-minute
boundaries, waits until the exact UTC instant when necessary, and refuses to
publish early. At the boundary it installs the repository's own Article Flow
controller, runs conformance and full readiness, checks the clean pinned
revision, regenerates the exact plan, records a short-lived scoped approval,
commits and pushes only the planned site files, and verifies the live article
and all discovery surfaces.

A successful run uploads `completed.json` plus the controller publication and
live-verification receipts to the still-private draft. A failure uploads a
timestamped `blocked-*.json` and makes no further automatic attempt. Drafts
with either terminal marker are skipped. Article content and private workflow
artifacts are therefore not exposed by the public site before publication.
