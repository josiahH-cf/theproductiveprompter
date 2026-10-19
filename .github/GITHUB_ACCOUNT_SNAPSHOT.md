# GitHub activity sources and refresh

## Public calendar and pinned repositories

The existing public collector and daily 06:17 UTC schedule remain independent.
Its graph uses GitHub's signed-out rolling date window, three same-window public
summaries, explicit UTC bounds and a dated snapshot. Only public pins are accepted.

## Verified signed-in aggregate

The combined contribution total comes from the owner's visible signed-in GitHub
profile, not a private-repository/event query. Read only the calendar heading,
the exact data-from/data-to bounds (including offsets), and signed-in owner.
GitHub's explicit year-filter URL can show a calendar year rather than the requested
rolling year: always verify the rendered bounds. Do not toggle profile privacy
settings, export cookies/tokens, or capture private repository names/details.
The public-sharing checkbox alone is not an owner-view inclusion indicator. If
the source has no explicit inclusion signal, obtain the owner's count-only
confirmation before marking the reference as private-inclusive or publishing it.

Keep the count-only reference outside this repository until validated. Its exact
fields are schema_version (1), source (github-signed-in-profile), source_url,
owner, from_bound, to_bound, checked_at, total_contributions, and
includes_private_activity (true, explicitly verified by the operator). No extra
fields are accepted. New references must be checked within 24 hours; re-rendering
never substitutes the current time for the actual check time. Existing snapshots
remain explicitly dated rather than silently becoming current.

```powershell
python -B .github/scripts/refresh_github_profile_snapshot.py --reference C:/path/outside-the-repo/verified-profile-reference.json
python -B .github/scripts/refresh_github_profile_snapshot.py --check
python -B .github/scripts/refresh_github_profile_snapshot.py --check-live
python -B -m unittest discover -s tests -p "test_github_*.py" -v
```

The source is a combined public/private total, not a private-only count. Never
subtract the UTC public calendar or a differently scoped API result from a
profile-local snapshot. Only the verified anonymous total and provenance are
rendered; there are no private repository names or private activity records.

For an on-demand refresh through the existing workflow, explicitly confirm
profile_snapshot_verified and supply profile_snapshot_total,
profile_snapshot_from, profile_snapshot_to, and profile_snapshot_checked_at.
Inputs enter Python through environment values, never shell interpolation. The
same Article Flow, stale-main, single-page staging, concurrency and exact-SHA
Pages verification guards protect publication. With no confirmed reference,
scheduled/manual public-only runs leave this third marker region untouched.

GitHub can cancel a legacy Pages build while a replacement Pages workflow for
the same commit succeeds. The legacy build record may remain errored. Publication
therefore also checks the newest `dynamic/pages/pages-build-deployment` run on
`main` for the exact commit; only completed success counts. Cancellation waits
within the existing 25-minute deadline, and an actual failed replacement fails.
The probe uses the existing token for read-only public run metadata, with a
30-second request timeout and no added permissions or new build requests.

No unattended account credential has been added. The private-inclusive snapshot
is refreshed on demand and says so visibly. The public calendar continues daily.

## Aggregate-only CLI diagnostic

refresh_github_account_snapshot.py remains an internal-only diagnostic. It uses
existing gh authentication, bounded noninteractive requests and only identity,
exact bounds and numeric calendar aggregates. It writes no site or credential
file. Its successful HTTP response is not proof of private visibility; neither
equal totals, scope metadata nor restrictedContributionsCount establishes a
private total of zero. Diagnostic records remain publication-ineligible and
must stay outside this public repo. No auth refresh/switch or permission
expansion is performed by either helper.
