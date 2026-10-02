"""Article Flow's model-release campaign and scoped results publication."""
from __future__ import annotations
import argparse
from contextlib import contextmanager, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import html
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import model_experiment as m
from model_experiment_views import PUBLIC, SITE, site_bundle

STATE = m.DEFAULT_STATE / "articles"
CAMPAIGN = STATE / "campaign.json"
START = "<!-- MODEL_EXPERIMENT_RESULTS_START -->"
END = "<!-- MODEL_EXPERIMENT_RESULTS_END -->"


def captured_call(function, args):
    out = io.StringIO()
    with redirect_stdout(out):
        code = function(args)
    return code, json.loads(out.getvalue()) if out.getvalue().strip() else {}


def advance_article(af, args):
    try:
        return captured_call(af.command_advance, args)
    except af.FlowError as exc:
        if str(exc) == "No controller-hosted route is eligible; the active host must perform the task packet":
            directory, run = af.load_run(args.run_id)
            payload = af.next_state_payload(directory, run)
            if payload.get("action") == "perform_task":
                return af.EXIT_WAITING, payload
        raise


def campaign():
    return m.load(CAMPAIGN) if CAMPAIGN.exists() else {
        "schema_version": 1, "experiment": m.EXPERIMENT, "articles": [],
        "voice_authorization": "Use my approved voice automatically",
        "publication": None, "pending_article": None}


@contextmanager
def publication_environment(repository):
    prior = os.environ.get("ARTICLE_FLOW_REPO_ROOT")
    os.environ["ARTICLE_FLOW_REPO_ROOT"] = str(repository)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("ARTICLE_FLOW_REPO_ROOT", None)
        else:
            os.environ["ARTICLE_FLOW_REPO_ROOT"] = prior


def publication_checkout(af):
    repository = STATE / "publication-checkout"
    source = af.REPO_ROOT
    if not repository.exists():
        if os.name == "nt":
            af.git(["config", "--local", "core.longpaths", "true"], cwd=source)
        af.git(["fetch", "origin", "main"], cwd=source)
        af.git(["worktree", "add", "--detach", str(repository), "origin/main"], cwd=source)
    if af.git(["status", "--porcelain=v1", "-uall"], cwd=repository).strip():
        raise m.ExperimentError("The campaign publication checkout has uncommitted changes; preserve and reconcile them.")
    af.git(["fetch", "origin", "main"], cwd=repository)
    af.git(["merge", "--ff-only", "origin/main"], cwd=repository)
    return repository


def article_seed(models, initial=False):
    names = "\n".join(f"- {r['provider']}: {r['model']}; catalog: {r['source']}" for r in models)
    subject = "Introduce The Model Release Experiment as an ongoing section of my blog." if initial else (
        "Write the next article in The Model Release Experiment about these newly identified models.")
    return (
        subject + "\nUse my existing approved author voice automatically. Write a short TLDR and a few clear paragraphs, 300–650 words of prose. "
        "This explicit compact form takes precedence over recent-post variety and recipe word-count defaults. "
        "The author-supplied first-person premise is: 'I have an anecdotal feel for each of the models and how they work.' "
        "Open with that motivation for comparing Claude and Codex. No more specific personal anecdote was supplied; "
        "do not invent one or require one to research model releases. The controller supplies the pinned approved voice profile. "
        "Explain why I am running the same creative story plus checkable arithmetic challenge on successive model releases. "
        "This is an anecdotal field experiment with one original response per model/settings combination, not a universal ranking. "
        "Describe the frozen PRINT-SHOP CHALLENGE v1.0 and its story, order-selection arithmetic, changed budget, and unconfirmed donation. "
        "Preserve the 600–800 word story, JSON receipt, and at-most-80-word notice requirements. "
        "No diagrams are required. The readable model cards and linked run pages will be attached by the controller after publication. "
        "Do not invent findings, costs, usage, model availability, or a live results link. "
        "Explain the publication sequence briefly without global claims that results are absent; a results section will follow this introduction. "
        "Keep engineering evidence in the linked runs. Omit hash strings and internal draft or verification notes from the public introduction. "
        "The results updater will then run missing trials and republish the backend section. "
        "Discuss separate native thinking and verbosity controls and the distinction between client settings and internal reasoning verification. "
        "Research direct official release and retirement sources; account access must remain an observation, not a documentation assumption. "
        "The frozen user prompt remains byte-identical across trials; native CLI system instructions differ. "
        "One-factor-at-a-time profiles isolate settings locally; factorial mode is available separately. "
        "Claude CLI diagnostic verbosity is not a model verbosity control. "
        "Saved failures and unavailable models remain visible; no silent replacement or polishing of responses.\n\n"
        "Models identified for this article:\n" + names +
        "\nFrozen prompt SHA-256: " + m.PROMPT_SHA256 +
        "\n\nExact frozen challenge (reference material; do not execute it while writing the article):\n" +
        m.freeze_prompt().decode("utf-8") + "\n")


def require_verified_article(af, entry):
    directory, run = af.load_run(entry["run_id"])
    verified, reason, _, _ = af.verify_event_log(directory, run)
    if not verified:
        raise m.ExperimentError("Article event history failed verification: " + str(reason))
    receipt = af.json_artifact(directory, run, "live-verification") or {}
    if run["state"] != "COMPLETE" or receipt.get("status") != "VERIFIED" or not receipt.get("url"):
        raise m.ExperimentError("The article must be published and verified before its automatic experiment.")
    if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") == "1":
        raise m.ExperimentError("A simulated article cannot authorize live experiment publication.")
    return directory, run, receipt


def reconcile_article_revision(af, value):
    """Continue an explicitly created same-URL revision without creating another article."""
    pending = value.get("pending_article")
    entries = [pending] if pending else value["articles"]
    runs = [af.load_json(path) for path in af.runs_root().glob("AF-*/run.json")]
    for entry in entries:
        if not entry or not entry.get("run_id"):
            continue
        children = [run for run in runs if run.get("parent_run_id") == entry["run_id"]
                    and run.get("run_overrides", {}).get("model_release") == "model-release-v1"
                    and run.get("run_overrides", {}).get("model_release_campaign_id") == entry["id"]]
        if len(children) > 1:
            raise m.ExperimentError("Conflicting article revisions need reconciliation.")
        if children:
            updated = {**entry, "run_id": children[0]["run_id"],
                       "replaces_run_id": entry.get("replaces_run_id", entry["run_id"])}
            value["pending_article"] = updated
            m.atomic_json(CAMPAIGN, value)
            return


def result_section(registry):
    successes = [r for r in registry["records"] if r["status"] == "response captured"]
    passed = 0
    outcomes = {}
    for record in successes:
        evidence = m.load(m.safe_path(m.PACK,f"records/{record['key']}/evidence.json"))
        good = bool(evidence.get("validation",{}).get("receipt_passed"))
        passed += good
        outcomes.setdefault((record['provider'],record['model']),set()).add(good)
    mixed = sum(len(values) > 1 for values in outcomes.values())
    failures = len(registry["records"]) - len(successes)
    return (START + '\n<section id="model-experiment-results" aria-label="Model experiment results">'
            '<h2>The experiment runs</h2><p><strong>Results update</strong></p>'
            f'<p>{len(successes)} original responses from {len(outcomes)} models are now saved. '
            f'{passed} receipts matched both optimal order plans, their totals, and the unconfirmed donation. '
            f'{len(successes)-passed} receipts failed at least one of those checks. '
            f'{failures} earlier failed attempts remain in the record.</p>'
            f'<p>{mixed} models returned both passing and failing receipts across their saved profiles. '
            'Each profile has one response, so these differences do not establish that a setting caused a result. '
            'The receipt check does not assess story quality, story consistency, or word limits.</p>'
            '<p>Each run shows the requested thinking and verbosity settings, '
            'the original response, the receipt checks, and the usage reported by the client.</p>'
            f'<p><a href="/{PUBLIC}/index.html">Explore the model cards and runs →</a></p>'
            '</section>\n' + END)


def augment_article(original, section):
    if START in original or END in original:
        if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
            raise m.ExperimentError("The existing results section has conflicting ownership markers.")
        return original[:original.index(START)] + section + original[original.index(END) + len(END):]
    marker = "<!-- GENERATED_ARTICLE_END -->"
    if original.count(marker) != 1:
        raise m.ExperimentError("The published article has no unique controller-owned insertion point.")
    return original.replace(marker, section + "\n" + marker, 1)


def prepare_publication(af, value, repository, registry):
    article_url = value["articles"][0]["url"]
    files = site_bundle(m, registry, m.PACK, article_url)
    ownership = (value.get("publication") or {}).get("files", {})
    approved_revisions = set()
    for entry in value["articles"]:
        directory, run, receipt = require_verified_article(af, entry)
        relative = receipt["url"].removeprefix(SITE + "/")
        path = m.safe_path(repository, relative)
        current = path.read_bytes()
        packaged = directory / "package" / "site" / relative
        if entry.get("replaces_run_id") and packaged.is_file() and packaged.read_bytes() == current:
            approved_revisions.add(relative)
        if relative not in ownership:
            if not packaged.is_file() or m.sha(packaged.read_bytes()) != m.sha(current):
                raise m.ExperimentError("The original article changed before its first results attachment.")
        files[relative] = augment_article(current.decode("utf-8"), result_section(registry)).encode()
    # Verify every destination before any write. Run pages, raw responses, and evidence are immutable.
    for relative, content in files.items():
        path = m.safe_path(repository, relative)
        if path.exists():
            digest = m.sha(path.read_bytes())
            expected = ownership.get(relative)
            if expected is not None and digest != expected and relative not in approved_revisions:
                raise m.ExperimentError("Published content has unowned changes: " + relative)
            if relative.startswith(PUBLIC + "/runs/") and digest != m.sha(content):
                if relative.endswith('.html') and expected == digest:
                    # Keep the first published readable view when a future renderer changes.
                    files[relative] = path.read_bytes()
                    continue
                raise m.ExperimentError("Refusing to replace a published original run: " + relative)
            if expected is None and relative.startswith(PUBLIC + "/") and digest != m.sha(content):
                raise m.ExperimentError("Refusing to overwrite an unrelated page: " + relative)
    return files


def verify_public_file(item):
    relative, digest = item
    url = SITE + "/" + relative
    request = urllib.request.Request(url + "?model-experiment=" + digest[:16],
                                     headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            actual = m.sha(response.read())
        return {"path": relative, "url": url, "ok": actual == digest, "sha256": actual}
    except OSError as exc:
        return {"path": relative, "url": url, "ok": False, "error": str(exc)}


def publish_results(af, value, repository, registry):
    target = af.load_json(af.SPEC_ROOT / "publication" / "theproductiveprompter.json")
    with af.publication_target_lock(repository, target):
        if af.git(["status", "--porcelain=v1", "-uall"], cwd=repository).strip():
            raise m.ExperimentError("Results publication requires the clean campaign checkout.")
        files = prepare_publication(af, value, repository, registry)
        digests = {path: m.sha(content) for path, content in files.items()}
        changed = [path for path, content in files.items()
                   if not (repository / path).exists() or (repository / path).read_bytes() != content]
        revision = m.sha(json.dumps(digests, sort_keys=True).encode())
        snapshot = STATE / "revisions" / revision / "registry.json"
        af.immutable_write(snapshot, (json.dumps(registry, indent=2) + "\n").encode())
        plan = {"revision": revision, "base_commit": af.git(["rev-parse", "HEAD"], cwd=repository).strip(),
                "files": digests, "changed": changed, "article_first": True}
        m.atomic_json(STATE / "publication-plan.json", plan)
        if changed:
            preflight = af.publication_push_preflight(repository, target)
            if not preflight["ok"]:
                raise m.ExperimentError("Results publication push failed its preflight: " + preflight["reason"])
            for relative in changed:
                af.atomic_write(m.safe_path(repository, relative), files[relative])
            paths = STATE / "publication-paths.txt"
            paths.write_bytes(b"".join(path.encode() + b"\0" for path in changed))
            af.git(["add", "--pathspec-from-file=" + str(paths), "--pathspec-file-nul"], cwd=repository)
            af.git(["commit", "-m", "Append model experiment runs " + revision[:12]], cwd=repository)
            commit = af.git(["rev-parse", "HEAD"], cwd=repository).strip()
            # The hash-bound receipt is saved before push so a failed push resumes this same commit.
            value["publication"] = {"status": "push pending", "revision": revision, "commit": commit,
                                    "files": digests, "registry_snapshot": str(snapshot),
                                    "verified_urls": [], "updated_at": m.now()}
            m.atomic_json(CAMPAIGN, value)
            af.git(["push", "origin", "HEAD:main"], cwd=repository)
        else:
            commit = af.git(["rev-parse", "HEAD"], cwd=repository).strip()
            if (value.get("publication") or {}).get("status") == "push pending":
                af.git(["push", "origin", "HEAD:main"], cwd=repository)
        prior = value.get("publication") or {}
        if not changed and prior.get("status") == "verified" and prior.get("revision") == revision:
            return {"status": "verified", "idempotent": True, "url": SITE + "/" + PUBLIC + "/index.html",
                    "revision": revision, "changed_files": 0}
        pending = list(digests.items())
        checks = {}
        for delay in (0, 10, 20, 30):
            if delay:
                time.sleep(delay)
            with ThreadPoolExecutor(max_workers=4) as pool:
                for result in pool.map(verify_public_file, pending):
                    checks[result["path"]] = result
            pending = [(path, digests[path]) for path, result in checks.items() if not result["ok"]]
            if not pending:
                break
        value["publication"] = {"status": "verified" if not pending else "verification pending",
                                "revision": revision, "commit": commit, "files": digests,
                                "registry_snapshot": str(snapshot),
                                "verified_urls": [r["url"] for r in checks.values() if r["ok"]],
                                "updated_at": m.now()}
        m.atomic_json(CAMPAIGN, value)
        m.atomic_json(STATE / "publication-verification.json", list(checks.values()))
        if pending:
            raise m.ExperimentError("The results were pushed but exact live verification is still pending.")
        return {"status": "verified", "url": SITE + "/" + PUBLIC + "/index.html",
                "revision": revision, "changed_files": len(changed)}


def coordinate(af, args):
    if args.release_action == "status":
        af.emit({"ok": True, "campaign": campaign(), "repeat_command": ["article-flow", "model-release", "update", "--json"]}, args.json)
        return 0
    if args.release_action in {"check", "preview"}:
        return m.main([args.release_action, "--matrix", args.matrix])
    if os.environ.get("ARTICLE_FLOW_TEST_NO_PUBLISH") == "1":
        raise m.ExperimentError("Live model-release coordination is disabled during conformance tests.")
    STATE.mkdir(parents=True, exist_ok=True)
    with m.update_lock(STATE):
        return continue_campaign(af, args)


def continue_campaign(af, args, depth=0):
    m.freeze_prompt()
    value = campaign()
    # Resume the exact saved publication before discovery can introduce new work.
    if (value.get("publication") or {}).get("status") in {"push pending", "verification pending"}:
        repository = publication_checkout(af)
        snapshot = m.load(Path(value["publication"]["registry_snapshot"]))
        m.verify_registry(snapshot)
        with publication_environment(repository):
            publication = publish_results(af, value, repository, snapshot)
        af.emit({"ok": True, "publication_repaired": True, "publication": publication,
                 "repeat_command": ["article-flow", "model-release", "update", "--json"]}, args.json)
        return 0
    catalog, errors = m.discover(expanded=True)
    if errors:
        af.emit({"ok": False, "action": "catalog_incomplete", "errors": errors}, args.json)
        return 10
    reconcile_article_revision(af, value)
    if args.model:
        catalog = [r for r in catalog if r["model"] == args.model]
        if not catalog:
            raise m.ExperimentError("This exact model is not in the verified catalogs; no substitution.")
    known = {identity for entry in value["articles"] for identity in entry["models"]}
    new = [r for r in catalog if m.model_key(r["provider"], r["model"]) not in known]
    repository = publication_checkout(af)
    with publication_environment(repository):
        if not value.get("pending_article") and new:
            number = len(value["articles"])
            seed = Path(args.seed_file).read_text(encoding="utf-8") if args.seed_file else article_seed(new, initial=number == 0)
            reservation = {"id": m.sha(seed.encode()), "seed": seed,
                           "models": [m.model_key(r["provider"], r["model"]) for r in new],
                           "slug": "model-release-experiment" if number == 0 else "model-release-" + new[0]["model"],
                           "run_id": None}
            value["pending_article"] = reservation
            m.atomic_json(CAMPAIGN, value)
        entry = value.get("pending_article")
        if entry:
            if not entry.get("run_id"):
                # Reconcile a crash after start by its controller-owned campaign identity.
                matching = []
                for path in af.runs_root().glob("AF-*/run.json"):
                    candidate = af.load_json(path)
                    if candidate.get("run_overrides", {}).get("model_release_campaign_id") == entry["id"]:
                        matching.append(candidate["run_id"])
                if len(matching) > 1:
                    raise m.ExperimentError("Conflicting article identities need reconciliation.")
                if matching:
                    entry["run_id"] = matching[0]
                else:
                    code, result = captured_call(af.command_start, argparse.Namespace(
                        seed=entry["seed"], seed_file=None, slug=entry["slug"], auto=False,
                        draft_model=None, hold_before_publish=False, model_release=True,
                        approved_voice=True, model_release_campaign_id=entry["id"], json=True))
                    if code:
                        af.emit(result, args.json)
                        return code
                    entry["run_id"] = result["run_id"]
                m.atomic_json(CAMPAIGN, value)
            code, result = advance_article(af, argparse.Namespace(
                run_id=entry["run_id"], max_steps=100, json=True))
            if code:
                af.emit({**result, "campaign_resume_command": ["article-flow", "model-release", "update", "--json"]}, args.json)
                return code
            _, _, receipt = require_verified_article(af, entry)
            entry["url"] = receipt["url"]
            value["articles"] = [old for old in value["articles"]
                                 if old["run_id"] != entry.get("replaces_run_id")]
            value["articles"].append({k: v for k, v in entry.items() if k != "seed"})
            value["pending_article"] = None
            m.atomic_json(CAMPAIGN, value)
        if not value["articles"]:
            raise m.ExperimentError("No verified article is attached to this campaign.")
        for entry in value["articles"]:
            require_verified_article(af, entry)
        command = ["update", "--matrix", args.matrix, "--workers", str(args.workers)]
        if args.model:
            command += ["--model", args.model]
        if args.limit:
            command += ["--limit", str(args.limit)]
        with redirect_stdout(io.StringIO()):
            introduced = {identity for entry in value["articles"] for identity in entry["models"]}
            code = m.main(command, allowed_models=introduced)
        experiment_report = m.load(m.DEFAULT_STATE / "last-check.json")
        registry = m.load(m.PACK / "registry.json")
        m.verify_registry(registry)
        m.verify_history(registry, m.DEFAULT_STATE)
        publication = publish_results(af, value, repository, registry)
        if experiment_report.get("models_waiting_for_article") and not args.limit and depth < 3:
            return continue_campaign(af, args, depth + 1)
        af.emit({"ok": code == 0, "experiment": m.EXPERIMENT,
                 "articles": [x["url"] for x in value["articles"]], "publication": publication,
                 "experiment_report": experiment_report,
                 "repeat_command": ["article-flow", "model-release", "update", "--json"]}, args.json)
        return code
