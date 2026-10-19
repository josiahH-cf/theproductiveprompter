# Internal account-aggregate prototype

This is an unpublished evidence helper, not a website feature or a replacement
for the signed-out public calendar. It has no website writer or public renderer.
An HTTP 200 response proves a successful aggregate query, not complete private
visibility. Equal totals and an owner's `restrictedContributionsCount` must not
be interpreted as a private total of zero.

Run from the repository with the existing GitHub CLI account sign-in:

```powershell
python -B .github/scripts/refresh_github_account_snapshot.py
python -B .github/scripts/refresh_github_account_snapshot.py --check-snapshot C:/path/outside-the-repo/internal-evidence.json
python -B -m unittest discover -s tests -p test_github_account_snapshot.py -v
```

The capture emits only allowlisted identity/date/numeric aggregate evidence to
stdout. Keep real captured JSON outside this public repository. There is no
credential entry, token export, auth refresh/switch, settings write, or new secret.
The existing daily public pinned-project/calendar workflow remains untouched.

The source query requests only `viewer.login`, `startedAt`, `endedAt`, and
`contributionCalendar.totalContributions`. Requests split into contiguous calendar
years and validate every returned bound. Completed UTC days exclude today's
mutable activity, including commits made while preparing a deployment. The
signed-out calendar is filtered to precisely those same dates; the daily public
calendar itself retains GitHub's entire rolling window.

Every internal snapshot has `private_total: null`,
`private_total_status: not_separately_verified`, and `publication_eligible: false`.
This remains true for zero totals, equal totals, and additional account-visible
counts. These are safety gates, not visitor-facing status messages. No private
repository/event fields or private daily activity are requested. Unknown fields,
duplicate JSON, invalid numeric values, identity/window mismatches and failed
requests are rejected. Errors never echo raw API/CLI responses. Requests are
bounded and noninteractive. Dated checks report an unavailable public-window
comparison as unknown, never as a match.

Publication remains blocked until private inclusion can be substantiated using
an authorized aggregate-only source and an independently established same-window
reference. A scope header by itself is not an API-denial verdict. No permission
expansion or account/profile change is performed by this helper.
