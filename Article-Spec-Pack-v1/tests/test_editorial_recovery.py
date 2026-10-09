"""Regressions for owned review surfaces and immutable legacy-obligation recovery."""
import html
import re
import sys
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_context as context
import revision_sources
import test_article_flow_v3 as fixtures

af, call = fixtures.af, fixtures.call


class LegacyCardRevisionTests(TestCase):
    slug = "from-idea-to-verified-url"
    canonical = f"https://theproductiveprompter.com/docs/{slug}.html"

    def card(self, href=None, *, marked=False, featured=False):
        marker = f' data-article-flow-slug="{self.slug}"' if marked else ""
        feature = ' article-card--featured' if featured else ''
        badge = '<span class="article-card__badge">Latest</span>' if featured else ''
        # Preserve the legacy tutorial's thumbnail, categories, reveal class,
        # CTA and multiline summary rather than replacing its entire template.
        return (f'<article class="article-card reveal-on-scroll{feature}"{marker}>' + badge +
                '<div class="article-card__thumbnail" aria-hidden="true"><svg viewBox="0 0 120 120"><circle cx="20" cy="60" r="11"/></svg></div>'
                '<div class="article-card__content"><div class="article-card__meta">'
                '<time class="article-card__date" datetime="2026-08-18">August 18, 2026</time>'
                '<span class="article-card__reading-time">11 min read</span></div>'
                '<div class="article-card__categories"><span>Workflow design</span><span>Writing systems</span></div>'
                f'<h3><a href="{href or self.slug + ".html"}" class="article-card__link">Original tutorial</a></h3>'
                '<p class="article-card__summary">\nOriginal summary.\n</p>'
                f'<a href="{href or self.slug + ".html"}" class="article-card__cta">Read the article →</a></div></article>')

    def replacement(self):
        return (f'<article class="article-card article-card--featured" data-article-flow-slug="{self.slug}">'
                '<span class="article-card__badge">Latest</span>'
                '<time class="article-card__date" datetime="2026-08-18">August 18, 2026</time>'
                '<span class="article-card__reading-time">13 min read</span>'
                f'<h3><a href="{self.slug}.html" class="article-card__link">Revised tutorial</a></h3>'
                '<p class="article-card__summary">A clearer &amp; bounded explanation.</p></article>')

    def test_legacy_and_repeated_revisions_preserve_layout_details_and_position(self):
        for home in (False, True):
            for featured in (False, True):
                with self.subTest(home=home, featured=featured):
                    href = ("docs/" if home else "") + self.slug + ".html"
                    old = self.card(href, featured=featured)
                    replacement = self.replacement().replace(f'href="{self.slug}.html"', f'href="{href}"')
                    before = '<!-- unchanged before -->\r\n<article class="article-card"><a href="other.html">Other</a></article>\r\n'
                    after = '\r\n<!-- unchanged after -->'
                    base = "https://theproductiveprompter.com/" if home else "https://theproductiveprompter.com/docs/blog.html"
                    updated = af.replace_existing_article_card(before + old + after, self.slug, replacement, canonical=self.canonical, base_url=base)
                    expected = old.replace('class="article-card reveal-on-scroll' + (' article-card--featured' if featured else '') + '">',
                                           'class="article-card reveal-on-scroll' + (' article-card--featured' if featured else '') + f'" data-article-flow-slug="{self.slug}">')
                    expected = expected.replace('11 min read', '13 min read').replace('Original tutorial', 'Revised tutorial')
                    expected = expected.replace('\nOriginal summary.\n', 'A clearer &amp; bounded explanation.')
                    self.assertEqual(updated, before + expected + after)
                    self.assertEqual(af.replace_existing_article_card(updated, self.slug, replacement, canonical=self.canonical, base_url=base), updated)

    def test_comments_single_quotes_and_normalized_urls_use_real_card_spans(self):
        old = self.card('/docs/%66rom-idea-to-verified-url.html?old=1#part').replace('"', "'")
        lookalike = '<!-- ' + old + ' -->'
        updated = af.replace_existing_article_card(lookalike + old, self.slug, self.replacement())
        self.assertTrue(updated.startswith(lookalike))
        self.assertEqual(updated.count('Revised tutorial'), 1)
        self.assertEqual(updated.count(f'data-article-flow-slug="{self.slug}"'), 1)

    def test_duplicate_url_and_conflicting_identifiers_fail_closed(self):
        for content in (self.card() * 2, self.card(marked=True) + self.card(),
                        self.card(marked=True).replace(f'data-article-flow-slug="{self.slug}"', 'data-article-flow-slug="other"'),
                        self.card('https://unrelated.example/docs/' + self.slug + '.html', marked=True)):
            with self.subTest(content=content), self.assertRaises(af.FlowError):
                af.replace_existing_article_card(content, self.slug, self.replacement())

    def test_incidental_links_foreign_bases_and_ambiguous_fields_fail_closed(self):
        old = self.card()
        invalid = (old.replace('class="article-card__link"', 'class="citation"'),
                   '<base href="https://unrelated.example/">' + old,
                   '<base href="https://unrelated.example/">' + self.card(self.canonical),
                   '<base href="/other/">' + self.card(self.canonical),
                   old.replace('class="article-card__link"', 'class="article-card__link" href="other.html"'),
                   old.replace('<p class="article-card__summary">', '<p class="article-card__summary" class="other">'),
                   old.replace('</article>', '<p class="article-card__summary">Duplicate</p></article>'),
                   old.replace('Original tutorial', '<em>Original tutorial</em>'),
                   old.replace('article-card__date', 'unknown-date'), old.replace('</article>', ''))
        for content in invalid:
            with self.subTest(content=content), self.assertRaises(af.FlowError):
                af.replace_existing_article_card(content, self.slug, self.replacement())

    def test_populated_marked_cards_cannot_use_bare_placeholder_fallback(self):
        old = self.card(marked=True)
        invalid = (old.replace('article-card__link', 'changed-title-class'),
                   re.sub(r'<a[^>]*class="article-card__link"[^>]*>.*?</a>', '', old),
                   old.replace('article-card__summary', 'changed-summary-class'),
                   old.replace('11 min read', '<em>11 min read</em>'))
        for content in invalid:
            with self.subTest(content=content), self.assertRaises(af.FlowError):
                af.replace_existing_article_card(content, self.slug, self.replacement())

    def test_self_closing_managed_fields_cannot_diverge_from_browser_ownership(self):
        for role, tag in af.ArticleCardHTMLParser.managed_fields.items():
            old = self.card()
            content, count = re.subn(r'<' + tag + r'([^>]*class="' + role + r'"[^>]*)>.*?</' + tag + '>',
                                    lambda match: '<' + tag + match[1] + '/>', old, flags=re.DOTALL)
            self.assertEqual(count, 1)
            with self.subTest(role=role):
                with self.assertRaises(af.FlowError):
                    af.replace_existing_article_card(content, self.slug, self.replacement())
                with self.assertRaises(af.FlowError):
                    af.discovery_entry(content.encode(), 'blog', self.canonical, 'https://theproductiveprompter.com/docs/blog.html')

    def test_inert_cards_and_bases_cannot_authorize_mutation_or_discovery(self):
        real = self.card()
        base = 'https://theproductiveprompter.com/docs/blog.html'
        for tag in ('template', 'textarea', 'noscript', 'script', 'style', 'title', 'xmp', 'iframe', 'noembed'):
            inert = f'<{tag}><base href="https://unrelated.example/">' + real + f'</{tag}>'
            with self.subTest(tag=tag):
                with self.assertRaises(af.FlowError):
                    af.replace_existing_article_card(inert, self.slug, self.replacement())
                with self.assertRaises(af.FlowError):
                    af.discovery_entry(inert.encode(), 'blog', self.canonical, base)
                updated = af.replace_existing_article_card(inert + real, self.slug, self.replacement())
                self.assertTrue(updated.startswith(inert))
                self.assertEqual(updated.count('Revised tutorial'), 1)
                self.assertEqual(af.discovery_entry((inert + real).encode(), 'blog', self.canonical, base), (0, real))
        nested = '<template><textarea></template>' + real + '</textarea></template>'
        self.assertEqual(af.discovery_entry((nested + real).encode(), 'blog', self.canonical, base), (0, real))
        for content in ('<plaintext>' + real + '</plaintext>' + real, '<template/>' + real):
            with self.assertRaises(af.FlowError):
                af.replace_existing_article_card(content, self.slug, self.replacement())
        # The ownership parser and field parser must agree: an inert summary
        # inside a real card cannot stand in for a reader-facing summary.
        content = real.replace('<p class="article-card__summary">\nOriginal summary.\n</p>',
                               '<template><p class="article-card__summary">Hidden summary</p></template>')
        with self.assertRaises(af.FlowError):
            af.replace_existing_article_card(content, self.slug, self.replacement())

    def test_title_authority_requires_canonical_origin_with_default_port_equivalence(self):
        for origin in ('https://theproductiveprompter.com:8443', 'https://theproductiveprompter.com:80', 'https://theproductiveprompter.com:0',
                       'http://theproductiveprompter.com:80', 'https://theproductiveprompter.com:invalid'):
            with self.subTest(origin=origin), self.assertRaises(af.FlowError):
                af.replace_existing_article_card(self.card(origin + '/docs/' + self.slug + '.html'), self.slug, self.replacement())
        explicit_default = self.card('https://theproductiveprompter.com:443/docs/' + self.slug + '.html')
        self.assertIn('Revised tutorial', af.replace_existing_article_card(explicit_default, self.slug, self.replacement()))


class SharedSurfaceVerificationTests(fixtures.TemporaryRuntime):
    live_verification_fixture = fixtures.WorkflowV31RegressionTests.live_verification_fixture

    def committed_collection(self):
        run_id, directory, target, surfaces = self.live_verification_fixture()
        slug = "bounded-live-verification"
        canonical = target["canonical_url"].format(slug=slug)
        card = f'<article class="article-card" data-article-flow-slug="{slug}"><time>2026-08-18</time><a href="{slug}.html">Title</a><p>Summary</p></article>'
        for name in ("blog", "homepage"):
            actual_card = card.replace(f'href="{slug}.html"', f'href="docs/{slug}.html"') if name == "homepage" else card
            surfaces[name].write_text("<html>" + actual_card + "<!-- other article: old --></html>", encoding="utf-8")
        surfaces["feed"].write_text(f'<rss><channel><item><title>Title</title><link>{canonical}</link><description>Summary</description><pubDate>Tue, 18 Aug 2026 12:00:00 -0500</pubDate></item><!-- other article: old --></channel></rss>', encoding="utf-8")
        surfaces["sitemap"].write_text(f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{canonical}</loc><lastmod>2026-10-09</lastmod></url><!-- other article: old --></urlset>', encoding="utf-8")
        site = directory / "package/site"
        (site / "styles.css").write_bytes(b"body { color: black; }\n")
        asset = site / "assets/owned.svg"
        asset.parent.mkdir()
        asset.write_bytes(b"<svg>original</svg>\n")
        repo = self.root / run_id
        repo.mkdir()
        for path in site.rglob("*"):
            if path.is_file():
                dest = repo / path.relative_to(site)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(path.read_bytes())
        af.git(["init", "-b", "main"], cwd=repo)
        for key, value in (("user.email", "test@example.com"), ("user.name", "Test"), ("core.autocrlf", "false")):
            af.git(["config", key, value], cwd=repo)
        af.git(["add", "."], cwd=repo)
        af.git(["commit", "-m", "Original article"], cwd=repo)
        published = str(af.git(["rev-parse", "HEAD"], cwd=repo)).strip()
        remote = self.root / (run_id + "-remote.git")
        af.git(["init", "--bare", str(remote)], cwd=repo)
        af.git(["remote", "add", "origin", str(remote)], cwd=repo)
        _, run = af.load_run(run_id)
        package = af.load_json(directory / "package/package.json")
        package["public_files"] = [{"path": path.relative_to(directory / "package").as_posix(), "sha256": af.sha256_path(path)} for path in (directory / "package").rglob("*") if path.is_file() and path.name != "package.json"]
        af.write_json(directory / "package/package.json", package)
        af.record_artifact(directory, run, directory / "package/package.json", "package", {"actor": "test"})
        publication = self.record_json(directory, run, "publication", {"commit": published, "package_revision": package["package_revision"]})
        for name in ("blog", "homepage", "feed", "sitemap"):
            path = repo / surfaces[name].relative_to(site)
            path.write_bytes(path.read_bytes().replace(b"other article: old", b"other article: revised"))
        af.git(["add", "."], cwd=repo)
        af.git(["commit", "-m", "Next article changes discovery surfaces"], cwd=repo)
        af.git(["push", "origin", "main"], cwd=repo)
        return run_id, directory, target, repo, published, publication

    def fetched(self, target, repo):
        mapping = {target["canonical_url"].format(slug="bounded-live-verification"): repo / "docs/bounded-live-verification.html",
                   **{target[name + "_url"]: repo / target[name + "_file"] for name in ("blog", "homepage", "feed", "sitemap")},
                   target["homepage_url"] + "styles.css": repo / "styles.css"}
        return lambda url, timeout=30: (200, mapping[url].read_bytes(), {})

    def test_later_collection_commit_verifies_without_rewriting_original_publication(self):
        run_id, directory, target, repo, published, publication = self.committed_collection()
        original_receipt = publication.read_bytes()
        original_package = (directory / "package/package.json").read_bytes()
        head = str(af.git(["rev-parse", "HEAD"], cwd=repo)).strip()
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=self.fetched(target, repo)):
            code, result = call(af.command_verify_live, run_id=run_id)
        self.assertEqual(code, af.EXIT_OK, result)
        receipt = af.load_json(directory / "receipts/live-verification-01.json")
        self.assertEqual((receipt["commit"], receipt["shared_surface_commit"]), (published, head))
        self.assertEqual(publication.read_bytes(), original_receipt)
        self.assertEqual((directory / "package/package.json").read_bytes(), original_package)
        self.assertEqual(af.load_run(run_id)[1]["state"], "COMPLETE")
        self.assertTrue(all(item["ok"] for item in receipt["checks"]))

    def test_later_discovery_scope_rejects_unbound_or_changed_evidence(self):
        cases = ("dirty", "remote_moved", "unrelated", "article", "asset", "style", "missing_card", "duplicate_card", "summary", "card_position", "feed_date", "sitemap_date", "package", "publication")
        for case in cases:
            with self.subTest(case=case):
                run_id, directory, target, repo, _, publication = self.committed_collection()
                if case in {"package", "publication"}:
                    path = directory / "package/public/metadata.json" if case == "package" else publication
                    path.write_bytes(path.read_bytes() + b" ")
                elif case == "unrelated":
                    af.git(["checkout", "--orphan", "unrelated"], cwd=repo)
                    af.git(["commit", "-m", "Unrelated root"], cwd=repo)
                    af.git(["push", "--force", "origin", "HEAD:main"], cwd=repo)
                elif case == "remote_moved":
                    (repo / "next.txt").write_bytes(b"not pushed")
                    af.git(["add", "."], cwd=repo)
                    af.git(["commit", "-m", "Not published"], cwd=repo)
                else:
                    path = repo / ({"article": "docs/bounded-live-verification.html", "asset": "assets/owned.svg", "style": "styles.css", "feed_date": "feed.xml", "sitemap_date": "sitemap.xml"}.get(case, "index.html"))
                    body = path.read_bytes()
                    card = re.search(rb'<article\b.*?</article>', body, re.DOTALL)
                    if case == "missing_card":
                        body = body.replace(card.group(0), b"")
                    elif case == "duplicate_card":
                        body = body.replace(card.group(0), card.group(0) * 2)
                    elif case == "summary":
                        body = body.replace(b"Summary", b"Different meaning")
                    elif case == "card_position":
                        body = body.replace(card.group(0), b'<article class="article-card"><a href="other.html">Other</a></article>' + card.group(0))
                    elif case == "feed_date":
                        body = body.replace(b"18 Aug", b"19 Aug")
                    elif case == "sitemap_date":
                        body = body.replace(b"2026-10-09", b"2026-10-10")
                    else:
                        body += b" changed"
                    path.write_bytes(body)
                    if case != "dirty":
                        af.git(["add", "."], cwd=repo)
                        af.git(["commit", "-m", "Changed binding"], cwd=repo)
                        af.git(["push", "origin", "main"], cwd=repo)
                _, run = af.load_run(run_id)
                with mock.patch.object(af, "publication_repo_root", return_value=repo), self.assertRaises(af.FlowError):
                    af.live_discovery_scope(directory, run, af.load_json(directory / "package/package.json"), af.load_json(directory / "package/public/metadata.json"), target)
                self.assertEqual(af.load_run(run_id)[1]["state"], "LIVE_VERIFICATION")

    def test_later_scope_still_rejects_stale_http_and_failed_tls(self):
        for failed in ("feed", "styles.css"):
            with self.subTest(surface=failed):
                run_id, directory, target, repo, _, _ = self.committed_collection()
                fetch = self.fetched(target, repo)
                def stale(url, timeout=30):
                    if url == (target["feed_url"] if failed == "feed" else target["homepage_url"] + "styles.css"):
                        return (200, b"stale", {}) if failed == "feed" else (0, b"", {})
                    return fetch(url, timeout)
                with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=stale):
                    code, result = call(af.command_verify_live, run_id=run_id)
                self.assertEqual(code, af.EXIT_FAILED, result)
                self.assertNotEqual(af.load_run(run_id)[1]["state"], "COMPLETE")

    def test_actual_verifier_rejects_a_duplicate_card_with_root_relative_url(self):
        run_id, directory, target, repo, _, _ = self.committed_collection()
        path = repo / "index.html"
        path.write_bytes(path.read_bytes().replace(b"</html>", b'<article class="article-card"><a href="/docs/bounded-live-verification.html">RETIRED TITLE</a><p>RETIRED SUMMARY</p></article></html>'))
        af.git(["add", "."], cwd=repo)
        af.git(["commit", "-m", "Duplicate retired card"], cwd=repo)
        af.git(["push", "origin", "main"], cwd=repo)
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=self.fetched(target, repo)), self.assertRaises(af.FlowError):
            call(af.command_verify_live, run_id=run_id)
        self.assertEqual(af.load_run(run_id)[1]["state"], "LIVE_VERIFICATION")

    def test_discovery_ownership_counts_equivalent_urls_in_html_and_xml(self):
        canonical = "https://theproductiveprompter.com/docs/example.html"
        variants = (canonical, "/docs/example.html", "docs/example.html", "//theproductiveprompter.com/docs/example.html",
                    "/docs/../docs/example.html", "/docs/%65xample.html", canonical + "?source=old", canonical + "#old", r"\docs\example.html")
        for surface in ("homepage", "blog", "feed", "sitemap"):
            base = "https://theproductiveprompter.com/docs/blog.html" if surface == "blog" else "https://theproductiveprompter.com/"
            for link in variants:
                if surface == "blog" and link == "docs/example.html":
                    link = "example.html"
                with self.subTest(surface=surface, link=link):
                    if surface in {"homepage", "blog"}:
                        original = '<article class="article-card"><a href="' + canonical + '">Approved</a></article>'
                        duplicate = "<article class='article-card'><a href='" + html.escape(link, quote=True) + "'>Retired</a></article>"
                        content = original + duplicate
                    else:
                        owner, key = ("item", "link") if surface == "feed" else ("url", "loc")
                        entry = lambda value: f"<{owner}><{key}>{html.escape(value)}</{key}></{owner}>"
                        content = "<root>" + entry(canonical) + entry(link) + "</root>"
                    with self.assertRaisesRegex(af.FlowError, "found 2"):
                        af.discovery_entry(content.encode(), surface, canonical, base)

    def test_discovery_selection_respects_document_base_and_rejects_ambiguous_attributes(self):
        canonical = "https://theproductiveprompter.com/docs/example.html"
        original = '<article class="article-card"><a href="docs/example.html">Approved</a></article>'
        base = "https://theproductiveprompter.com/"
        self.assertEqual(af.discovery_entry(original.encode(), "homepage", canonical, base)[0], 0)
        for extra in ('<base href="https://unrelated.example/">', '<base href="/other/">'):
            with self.subTest(base=extra), self.assertRaises(af.FlowError):
                af.discovery_entry((original + extra).encode(), "homepage", canonical, base)
        duplicate = '<article class="article-card"><a href="/docs/example.html" href="https://unrelated.example/">Retired</a></article>'
        with self.assertRaisesRegex(af.FlowError, "duplicate HTML attributes"):
            af.discovery_entry((original + duplicate).encode(), "homepage", canonical, base)


class SettledDeploymentRecoveryTests(fixtures.TemporaryRuntime):
    live_verification_fixture = fixtures.WorkflowV31RegressionTests.live_verification_fixture
    committed_collection = SharedSurfaceVerificationTests.committed_collection

    def prepared(self, *, same_head=False):
        run_id, directory, target, repo, published, _ = self.committed_collection()
        if same_head:
            af.git(["checkout", "-B", "main", published], cwd=repo)
            af.git(["push", "--force", "origin", "main"], cwd=repo)
        _, run = af.load_run(run_id)
        package_path = directory / "package/package.json"
        package = af.load_json(package_path)
        package["run_id"] = run_id
        af.write_json(directory / "package/public/assets.json", {"assets": [{"visual_id": "owned", "public_path": "assets/owned.svg", "sha256": af.sha256_path(repo / "assets/owned.svg")}]})
        package["public_files"] = [{"path": path.relative_to(directory / "package").as_posix(), "sha256": af.sha256_path(path)} for path in (directory / "package").rglob("*") if path.is_file() and path != package_path]
        af.write_json(package_path, package)
        af.record_artifact(directory, run, package_path, "package", {"actor": "test"})
        authority = {"run_id": run_id, "target": target["target_id"], "package_revision": package["package_revision"], "approval_id": "AP-original"}
        self.record_json(directory, run, "publish-approval", {**authority, "status": "APPROVED"})
        self.record_json(directory, run, "publication", {**authority, "status": "PUSHED", "commit": published})
        def fetched(url, timeout=30):
            rel = url.removeprefix(target["homepage_url"]) or "index.html"
            return 200, (repo / rel).read_bytes(), {}
        def stale(url, timeout=30):
            return (200, b"previous deployment", {}) if url == target["feed_url"] else fetched(url, timeout)
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=stale):
            for _ in range(4):
                code, result = call(af.command_verify_live, run_id=run_id)
                self.assertEqual(code, af.EXIT_FAILED, result)
                self.assertEqual(result["classification"], "deployment_propagation")
        return run_id, directory, target, repo, fetched

    def recover(self, run_id):
        return call(af.command_repair, run_id=run_id, gate_id="G-LIVE-REVISION", finding="The author authorized one additional verification after the deployment settled.")

    def test_settled_bytes_open_one_check_and_preserve_original_authority(self):
        for same_head in (True, False):
            with self.subTest(same_head=same_head):
                run_id, directory, _, repo, fetched = self.prepared(same_head=same_head)
                _, run = af.load_run(run_id)
                paths = [af.artifact_path(directory, run, kind) for kind in ("package", "publication", "publish-approval")]
                paths += list((directory / "receipts").glob("live-verification-*.json"))
                before = {path: path.read_bytes() for path in paths}
                with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=fetched):
                    code, result = self.recover(run_id)
                    self.assertEqual((code, result["state"], result["maximum_attempts"]), (af.EXIT_OK, "LIVE_VERIFICATION", 1))
                    code, result = call(af.command_verify_live, run_id=run_id)
                self.assertEqual(code, af.EXIT_OK, result)
                self.assertEqual(result["state"], "COMPLETE")
                receipt = af.load_json(directory / "receipts/live-verification-05.json")
                self.assertEqual((receipt["attempt"], receipt["maximum_attempts"]), (5, 1))
                self.assertEqual({path: path.read_bytes() for path in paths}, before)
                self.assertFalse((directory / "receipts/live-verification-06.json").exists())

    def test_failed_extra_check_cannot_be_repeated_by_verify_advance_or_repair(self):
        run_id, directory, target, repo, fetched = self.prepared()
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=fetched):
            self.recover(run_id)
        def stale(url, timeout=30):
            return (200, b"stale again", {}) if url == target["feed_url"] else fetched(url, timeout)
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=stale):
            code, result = call(af.command_verify_live, run_id=run_id)
            self.assertEqual((code, result["retryable"], result["maximum_attempts"]), (af.EXIT_FAILED, False, 1))
            with self.assertRaisesRegex(af.FlowError, "exhausted"):
                call(af.command_verify_live, run_id=run_id)
            code, result = call(af.command_advance, run_id=run_id)
            self.assertEqual(code, af.EXIT_WAITING, result)
            with self.assertRaisesRegex(af.FlowError, "already recorded"):
                self.recover(run_id)
        self.assertEqual(af.load_run(run_id)[1]["status"], "BLOCKED")
        self.assertFalse((directory / "receipts/live-verification-06.json").exists())

    def test_stale_article_shared_style_and_asset_cannot_reopen_the_stop(self):
        run_id, directory, target, repo, fetched = self.prepared(same_head=True)
        before = (directory / "events.jsonl").read_bytes()
        for rel in ("docs/bounded-live-verification.html", "feed.xml", "styles.css", "assets/owned.svg"):
            def stale(url, timeout=30):
                return (200, b"stale", {}) if url == target["homepage_url"] + rel else fetched(url, timeout)
            with self.subTest(rel=rel), mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=stale):
                with self.assertRaisesRegex(af.FlowError, "has not settled"):
                    self.recover(run_id)
            self.assertEqual((directory / "events.jsonl").read_bytes(), before)
        self.assertFalse(list((directory / "receipts").glob("deployment-propagation-observation-*.json")))

    def test_the_authorized_check_rechecks_style_even_at_the_original_commit(self):
        run_id, directory, target, repo, fetched = self.prepared(same_head=True)
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=fetched):
            self.recover(run_id)
        style_url = target["homepage_url"] + "styles.css"
        def changed(url, timeout=30):
            return (200, b"changed after observation", {}) if url == style_url else fetched(url, timeout)
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=changed):
            code, result = call(af.command_verify_live, run_id=run_id)
        self.assertEqual(code, af.EXIT_FAILED, result)
        self.assertFalse(result["retryable"])
        failed = [item for item in result["checks"] if not item["ok"]]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["url"], style_url)
        self.assertNotEqual(failed[0]["expected_sha256"], failed[0]["actual_sha256"])
        self.assertEqual(af.load_run(run_id)[1]["status"], "BLOCKED")

    def test_tampered_authority_history_and_original_files_cannot_recover(self):
        cases = ("publication", "package", "publish-approval", "live-verification-attempt:1", "live-verification-attempt:4", "events", "packaged_file", "article", "remote", "replaced_package", "replaced_receipt")
        for kind in cases:
            with self.subTest(kind=kind):
                run_id, directory, _, repo, fetched = self.prepared(same_head=True)
                _, run = af.load_run(run_id)
                if kind == "events":
                    path = directory / "events.jsonl"
                    path.write_bytes(path.read_bytes().replace(b'"test"', b'"changed"', 1))
                elif kind == "packaged_file":
                    path = directory / "package/public/article.md"
                    path.write_bytes(path.read_bytes() + b"changed")
                elif kind == "replaced_package":
                    path = af.artifact_path(directory, run, "package")
                    af.record_artifact(directory, run, path, "package", {"actor": "test"})
                elif kind == "replaced_receipt":
                    path = af.artifact_path(directory, run, "live-verification-attempt:4")
                    receipt = af.load_json(path)
                    receipt.update(target="different-target", created_at="2099-01-01T00:00:00Z")
                    af.write_json(path, receipt)
                    af.record_artifact(directory, run, path, "live-verification-attempt:4", {"actor": "test"})
                elif kind in {"article", "remote"}:
                    path = repo / ("docs/bounded-live-verification.html" if kind == "article" else "unpublished.txt")
                    path.write_bytes(path.read_bytes() + b"changed" if path.exists() else b"new")
                    af.git(["add", "."], cwd=repo)
                    af.git(["commit", "-m", "Changed source"], cwd=repo)
                    if kind == "article":
                        af.git(["push", "origin", "main"], cwd=repo)
                else:
                    path = af.artifact_path(directory, run, kind)
                    path.write_bytes(path.read_bytes() + b" ")
                with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=fetched):
                    with self.assertRaises(af.FlowError):
                        self.recover(run_id)
                self.assertFalse(list((directory / "receipts").glob("deployment-propagation-observation-*.json")))

    def test_missing_finding_and_nonpropagation_failure_do_not_authorize_recovery(self):
        run_id, directory, _, repo, fetched = self.prepared()
        _, run = af.load_run(run_id)
        with self.assertRaisesRegex(af.FlowError, "explicit authorized finding"):
            af.repair_settled_deployment(directory, run, fixtures.namespace(run_id=run_id, finding=None))
        # A real permanent failure cannot acquire a propagation allowance.
        path = directory / "receipts/live-verification-04.json"
        receipt = af.load_json(path)
        receipt["classification"] = "permanent_validation_failure"
        receipt["checks"] = [{"name": "canonical", "ok": False}]
        af.write_json(path, receipt)
        af.record_artifact(directory, run, path, "live-verification-attempt:4", {"actor": "test"})
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=fetched):
            with self.assertRaises(af.FlowError):
                af.repair_settled_deployment(directory, run, fixtures.namespace(run_id=run_id, finding="Explicit request"))
        self.assertEqual(af.load_run(run_id)[1]["state"], "LIVE_VERIFICATION")

    def test_observation_is_bound_and_live_checks_are_serialized(self):
        run_id, directory, _, repo, fetched = self.prepared()
        with mock.patch.object(af, "publication_repo_root", return_value=repo), mock.patch.object(af, "fetch_url", side_effect=fetched):
            self.recover(run_id)
            _, run = af.load_run(run_id)
            with af.run_lock(directory, run):
                with self.assertRaisesRegex(af.FlowError, "already locked"):
                    call(af.command_verify_live, run_id=run_id)
            path = af.artifact_path(directory, run, "deployment-propagation-observation:4")
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(af.FlowError, "artifact changed"):
                call(af.command_verify_live, run_id=run_id)
        self.assertFalse((directory / "receipts/live-verification-05.json").exists())


class EditorialRecoveryTests(fixtures.TemporaryRuntime):
    anchor = fixtures.UsefulVisualPolicyTests.anchor
    fixture = fixtures.UsefulVisualPolicyTests.fixture

    tutorial_code = ("EDITORIAL LOOP\n\n                Seed\n                  ↓\n                Confirmed intent\n"
                     "                  ↓\n                Research + brief\n                  ↓\n                Draft\n"
                     "                  ↺  repair failed\n                     evidence or voice checks\n"
                     "                Editorially ready article\n                  ↓\n                PUBLICATION LOOP\n\n"
                     "                Package\n                  ↓\n                Validate\n                  ↓\n"
                     "                Deploy\n                  ↓\n                Inspect the live result\n"
                     "                  ↓\n                Verified URL\n                ")

    def source_code_fixture(self, include=False):
        directory, run, _, _ = self.fixture(current=True, include=include)
        source = self.record_text(directory, run, "revision-source", "<pre><code>" + html.escape(self.tutorial_code) + "</code></pre>", "bound-source.html")
        run["revision"] = {"slug": "competing-effects", "source_html_sha256": af.sha256_path(source)}
        draft = "# Competing effects\n\n```text\n" + self.tutorial_code + "\n```\n\n" + self.anchor + "\n\nThe net effect remains uncertain.\n"
        self.record_text(directory, run, "draft", draft, "exact-source-draft.md")
        return directory, run, draft

    def test_exact_tutorial_code_survives_visuals_and_new_locks(self):
        self.assertEqual(revision_sources.digest(self.tutorial_code), "71ab5d3ad4bd6bf15650b66095070f22b713f4b892d9be53df024f300d938abd")
        for include in (False, True):
            with self.subTest(actual_visual=include):
                directory, run, draft = self.source_code_fixture(include)
                self.assertEqual(revision_sources.preservation_findings(af, draft, run), [])
                af.transition(directory, run, "VISUAL_RENDER", "test", "Preserve source code through actual visual rendering")
                call(af.command_visual_render, run_id=run["run_id"])
                directory, run = af.load_run(run["run_id"])
                actual = af.artifact_path(directory, run, "draft").read_text(encoding="utf-8")
                self.assertEqual(revision_sources.preservation_findings(af, actual, run), [])
                self.assertEqual(af.find_locked_tokens(actual)["code_blocks"], af.find_locked_tokens(draft)["code_blocks"])
                self.assertEqual(af.materialize_manifest_visuals_markdown(actual, af.json_artifact(directory, run, "visual-manifest")), actual)
                ledger = self.record_json(directory, run, "verified-claim-ledger", {"claims": []})
                af.lock_verified_fields(directory, run, ledger)
                self.assertEqual(af.json_artifact(directory, run, "locked-fields")["tokens"]["code_blocks"], af.find_locked_tokens(draft)["code_blocks"])

    def test_visual_cleanup_preserves_code_images_blank_lines_and_literal_markers(self):
        literal = "```text\n## Owned heading\n\n\n![Example](/assets/example.svg)\n\n*Example caption*\n \t \n```\n"
        raw = '<pre><code>one\n\n\n two\n \t </code></pre>'
        text = "@@AF_VISUAL_LITERAL_0@@\n\n" + literal + "\n" + raw + "\n\n## Owned heading\n\n![Old](/assets/example.svg)\n\n*Example caption*\n"
        manifest = {"assets": [{"public_path": "/assets/example.svg", "caption": "Example caption", "alt_text": "Current", "placement": {"after_heading": "Owned heading"}}]}
        actual = af.materialize_manifest_visuals_markdown(text, manifest)
        self.assertIn(literal, actual)
        self.assertIn(raw, actual)
        self.assertIn("@@AF_VISUAL_LITERAL_0@@", actual)
        self.assertNotIn("![Old]", actual)
        self.assertEqual(actual.count("![Current]"), 1)

    def test_visual_materialization_preserves_longer_and_unclosed_rendered_code(self):
        for fence, close in (("````", "````"), ("```", "")):
            with self.subTest(fence=fence, close=close):
                text = "# Example\n\n" + fence + "text\nalpha\n \t \nbeta\n" + close + "\n"
                actual = af.materialize_manifest_visuals_markdown(text, {"assets": []})
                self.assertEqual(af.markdown_to_html(actual), af.markdown_to_html(text))

    def test_literal_tokens_do_not_rewrite_generated_captions_or_alt_text(self):
        literal = "```text\nPRESERVE THIS EXACT CODE\n```\n"
        text = "# Article\n\n" + literal + "\n## Owned heading\n\nBody.\n"
        caption = "Reference @@AF_VISUAL_LITERAL_0@@ stays literal."
        alt = "Alt @@AF_VISUAL_LITERAL_X0@@ stays literal."
        manifest = {"assets": [{"public_path": "/assets/example.svg", "caption": caption, "alt_text": alt, "placement": {"after_heading": "Owned heading"}}]}
        actual = af.materialize_manifest_visuals_markdown(text, manifest)
        self.assertEqual(actual.count(literal), 1)
        self.assertIn("*" + caption + "*", actual)
        self.assertIn("![" + alt + "]", actual)

    def test_lock_creation_and_visual_acceptance_reject_altered_source_code(self):
        directory, run, draft = self.source_code_fixture()
        altered = draft.replace("Verified URL\n                \n", "Verified URL\n\n")
        self.record_text(directory, run, "draft", altered, "altered-source-draft.md")
        ledger = self.record_json(directory, run, "verified-claim-ledger", {"claims": []})
        with self.assertRaisesRegex(af.FlowError, "Cannot lock altered"):
            af.lock_verified_fields(directory, run, ledger)
        self.assertIsNone(af.artifact(run, "locked-fields"))
        af.transition(directory, run, "VISUAL_RENDER", "test", "Fail before accepting altered evidence")
        with self.assertRaisesRegex(af.FlowError, "altered source-bound evidence"):
            call(af.command_visual_render, run_id=run["run_id"])
        self.assertEqual(af.load_run(run["run_id"])[1]["state"], "VISUAL_RENDER")

    def test_blocked_edit_reopens_only_proven_intact_source_lock_conflict(self):
        directory, run, draft = self.source_code_fixture()
        altered = draft.replace("Verified URL\n                \n", "Verified URL\n\n")
        bad_draft = self.record_text(directory, run, "draft", altered, "historical-bad-draft.md")
        locked = self.record_json(directory, run, "locked-fields", {"source_sha256": af.sha256_path(bad_draft), "tokens": af.find_locked_tokens(altered)}, "historical-bad-lock.json")
        self.record_text(directory, run, "article", draft, "restored-source-article.md")
        old_bytes = locked.read_bytes()
        af.transition(directory, run, "EDIT", "test", "An older release locked altered evidence")
        run["status"] = "BLOCKED"
        af.save_run(directory, run)
        self.assertTrue(af.locked_revision_source_conflict(directory, run))
        call(af.command_amend, run_id=run["run_id"], reopen_development=True, reason="Explicitly restore original source evidence before fresh locks and renew every downstream check.")
        directory, run = af.load_run(run["run_id"])
        self.assertEqual(run["state"], "DRAFT")
        self.assertEqual(locked.read_bytes(), old_bytes)
        self.assertEqual(af.artifact_path(directory, run, "article").read_text(encoding="utf-8"), draft)
        self.assertEqual(af.json_artifact(directory, run, "development-amendment")["source_state"], "EDIT")

    def test_blocked_edit_recovery_rejects_good_lock_active_edit_or_changed_evidence(self):
        for case in ("good_lock", "active", "changed_lock", "changed_draft", "changed_source"):
            with self.subTest(case=case):
                directory, run, draft = self.source_code_fixture()
                source = draft if case == "good_lock" else draft.replace("Verified URL\n                \n", "Verified URL\n\n")
                draft_path = self.record_text(directory, run, "draft", source, "recovery-source.md")
                lock = self.record_json(directory, run, "locked-fields", {"source_sha256": af.sha256_path(draft_path), "tokens": af.find_locked_tokens(source)})
                self.record_text(directory, run, "article", draft)
                af.transition(directory, run, "EDIT", "test", "Reject unsupported recovery")
                run["status"] = "ACTIVE" if case == "active" else "BLOCKED"
                af.save_run(directory, run)
                target = {"changed_lock": lock, "changed_draft": draft_path, "changed_source": af.artifact_path(directory, run, "revision-source")}.get(case)
                if target:
                    target.write_bytes(target.read_bytes() + b" ")
                with self.assertRaises(af.FlowError):
                    call(af.command_amend, run_id=run["run_id"], reopen_development=True, reason="A targeted recovery must retain intact source evidence and its historical lock.")
                self.assertEqual(af.load_run(run["run_id"])[1]["state"], "EDIT")
                self.assertIsNone(af.artifact(af.load_run(run["run_id"])[1], "development-amendment"))

    def test_edit_and_publication_reject_reintroduced_omitted_diagram(self):
        directory, run, _, _ = self.prepared()
        path = "/assets/articles/competing-effects/retired-graph.svg"
        text = af.artifact_path(directory, run, "article").read_text(encoding="utf-8") + f"\n![Retired graph]({path})\n\n*Old caption.*\n"
        candidate = directory / "artifacts" / "reintroduced.md"
        candidate.write_bytes(text.encode())
        outcome, findings = af.automatic_gate(directory, run, "EDIT", candidate)
        self.assertEqual(outcome, "REPAIR")
        self.assertTrue(any(f["criterion"] == "unplanned_visual_reference" and path in f["finding"] for f in findings))
        for index, url in enumerate((path, "../assets/articles/competing-effects/retired-graph.svg", "/assets/other/../articles/competing-effects/retired-graph.svg", "https://theproductiveprompter.com:443" + path)):
            self.record_text(directory, run, "article", text.replace(path, url), f"reintroduced-article-{index}.md")
            with self.subTest(url=url), self.assertRaisesRegex(af.FlowError, "outside the current manifest"):
                af.render_publication_files(directory, run, directory / "package", {})

    def test_visual_reference_check_distinguishes_current_images_from_source_examples(self):
        directory, run, _, _ = self.prepared()
        accepted = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["public_path"]
        old = "/assets/articles/competing-effects/retired-graph.svg"
        safe = f"![Current]({accepted})\n\n```markdown\n![Example]({old})\n```\n\n<img src=\"{old}\">\n"
        self.assertEqual(af.unplanned_visual_reference_findings(directory, run, safe, "candidate"), [])
        self.assertEqual(af.unplanned_visual_reference_findings(directory, run, f"![External](https://example.com{old})\n", "candidate"), [])
        for url in (old, "https://theproductiveprompter.com" + old, "https://theproductiveprompter.com:443" + old, old.replace("retired", "%72etired"),
                    "../assets/articles/competing-effects/retired-graph.svg", "/assets/other/../articles/competing-effects/retired-graph.svg",
                    "/assets/other/%2e%2e/articles/competing-effects/retired-graph.svg"):
            with self.subTest(url=url):
                self.assertTrue(af.unplanned_visual_reference_findings(directory, run, f"![Old]({url})\n", "candidate"))
        self.record_json(directory, run, "visual-manifest", {"assets": [], "omission_reason": "No diagram is useful."}, "empty-manifest.json")
        self.assertTrue(af.unplanned_visual_reference_findings(directory, run, f"![Previously accepted]({accepted})\n", "candidate"))

    def test_qa_cannot_pass_an_omitted_image_in_the_current_article(self):
        directory, run, _, _ = self.prepared()
        text = af.artifact_path(directory, run, "article").read_text(encoding="utf-8")
        text += "\n![Old](/assets/articles/competing-effects/retired-graph.svg)\n"
        self.record_text(directory, run, "article", text, "qa-omitted-image.md")
        review = {key: {"status": "PASS", "excerpt": self.anchor, "reason": "This exact retained passage explains the two competing mechanisms."} for key in ("language", "rhetoric", "structure", "preservation")}
        assessment = {"editorial_assessment_schema_version": "1.0.0", "run_id": run["run_id"], "outcome": "PASS",
                      "dimensions": {key: {"status": "PASS"} for key in ("intent_fidelity", "clarity_utility", "voice_fit", "naturalness", "public_surface_voice", "structural_interest", "proportional_length")},
                      "findings": [], "naturalization_review": review, "calibration_status": "uncalibrated-advisory"}
        path = self.record_json(directory, run, "editorial-qa", assessment, "qa-omitted-image.json")
        outcome, findings = af.automatic_gate(directory, run, "EDITORIAL_QA", path)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("unplanned_visual_reference", {f["criterion"] for f in findings})

    def test_renderer_does_not_repeat_a_caption_title_already_in_the_bound_caption(self):
        directory, run, _, _ = self.prepared()
        plan = af.json_artifact(directory, run, "visual-plan")
        visual = plan["visuals"][0]
        original_caption = visual["caption"]
        visual["caption"] = visual["title"] + ". " + original_caption
        self.record_json(directory, run, "visual-plan", plan, "caption-title-plan.json")
        af.transition(directory, run, "VISUAL_RENDER", "test", "Render the title-prefixed caption")
        call(af.command_visual_render, run_id=run["run_id"])
        directory, run = af.load_run(run["run_id"])
        body = af.inject_manifest_visuals(directory, run, af.markdown_to_html("## Two competing effects\n\n" + self.anchor))
        expected = f'<figcaption><strong>{visual["title"]}.</strong> {original_caption}</figcaption>'
        self.assertIn(expected, body)
        self.assertNotIn(f'</strong> {visual["title"]}.', body)
        self.assertEqual(af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"], visual["caption"])

    def test_revision_edit_packet_keeps_current_prose_and_manifest_authoritative(self):
        directory, run, _, _ = self.prepared()
        run["revision"] = {"source_run_id": "original", "source_html_sha256": "0" * 64}
        source = self.record_text(directory, run, "revision-source", "<article><p>Historical prose.</p></article>", "revision-source.html")
        run["revision"]["source_html_sha256"] = af.sha256_path(source)
        self.record_json(directory, run, "revision-evidence", {"evidence": []})
        self.record_text(directory, run, "revision-request", "Revise the current article.")
        self.record_text(directory, run, "previous-article", "# Historical article\n\nOld prose.\n")
        self.record_json(directory, run, "locked-fields", {"tokens": {}})
        af.transition(directory, run, "EDIT", "test", "Inspect current repair guidance")
        candidate = {"provider": "active-host", "model": "active-capable-host", "kind": "agent-hosted", "eligible": True}
        route = {"stage": "EDIT", "candidates": [candidate], "chosen": candidate, "fallbacks": [], "reason": "fixture"}
        # Packet text is the contract under test; no model is executed.
        with fixtures.mock.patch.object(af, "route_candidates", return_value=route), fixtures.mock.patch.object(af, "pin_writing_route", side_effect=lambda run, state, route: route), af.run_lock(directory, run):
            _, packet = af.task_packet(directory, run)
        guidance = "\n".join(packet["constraints"])
        self.assertNotIn("Start from previous-article", guidance)
        self.assertIn("current draft owns the first edit", guidance)
        self.assertIn("Never restore diagrams or captions", guidance)

    def test_explicit_development_reopening_preserves_current_prose_and_committed_evidence(self):
        directory, run, old_packet_path, _ = self.prepared()
        old_packet = old_packet_path.read_bytes()
        article = af.artifact_path(directory, run, "article")
        old_article = article.read_bytes()
        locked = self.record_json(directory, run, "locked-fields", {"tokens": {"numbers": ["3.2.1"]}})
        old_locked = locked.read_bytes()
        reason = "The tutorial repeats state inventories and needs a worked development explanation before new claim locks."
        code, payload = call(af.command_amend, run_id=run["run_id"], reopen_development=True, reason=reason)
        self.assertEqual(code, af.EXIT_OK)
        self.assertEqual(payload["state"], "DRAFT")
        directory, run = af.load_run(run["run_id"])
        self.assertEqual(article.read_bytes(), old_article)
        self.assertEqual(locked.read_bytes(), old_locked)
        self.assertEqual(old_packet_path.read_bytes(), old_packet)
        self.assertEqual(af.json_artifact(directory, run, "development-amendment")["article_sha256"], af.sha256_path(article))
        for kind in af.state_definition("DRAFT", run)["required_inputs"]:
            if not af.artifact(run, kind):
                self.record_json(directory, run, kind, {})
        candidate = {"provider": "active-host", "model": "active-capable-host", "kind": "agent-hosted", "eligible": True}
        route = {"stage": "DRAFT", "candidates": [candidate], "chosen": candidate, "fallbacks": [], "reason": "fixture"}
        with fixtures.mock.patch.object(af, "route_candidates", return_value=route), fixtures.mock.patch.object(af, "pin_writing_route", side_effect=lambda run, state, route: route), af.run_lock(directory, run):
            _, packet = af.task_packet(directory, run)
        inputs = {item["id"]: item for item in packet["inputs"]}
        self.assertIn("development-amendment", inputs)
        self.assertEqual(af.load_json(Path(inputs["development-amendment"]["path"]))["reason"], reason)
        self.assertEqual(inputs["current-article"]["sha256"], af.sha256_path(article))
        self.assertIn("before new claim locks", "\n".join(packet["constraints"]))
        self.assertEqual(af.state_definition("DRAFT", run)["next_on_pass"], "DEVELOPMENT_REVIEW")

    def test_development_reopening_rejects_missing_reason_mixed_edits_changed_source_and_published_state(self):
        for case in ("reason", "mixed", "source", "published"):
            with self.subTest(case=case):
                directory, run, _, _ = self.prepared()
                options = {"reopen_development": True, "reason": "A specific missing argument requires development before fresh claims."}
                if case == "reason":
                    options["reason"] = " "
                elif case == "mixed":
                    options["article"] = "other.md"
                elif case == "source":
                    article = af.artifact_path(directory, run, "article")
                    article.write_bytes(article.read_bytes() + b" ")
                else:
                    af.transition(directory, run, "COMPLETE", "test", "Published articles require a new revision")
                with self.assertRaises(af.FlowError):
                    call(af.command_amend, run_id=run["run_id"], **options)
                self.assertIsNone(af.artifact(af.load_run(run["run_id"])[1], "development-amendment"))

    def prepared(self):
        directory, run, _, _ = self.fixture(current=True)
        af.transition(directory, run, "VISUAL_RENDER", "test", "Render reviewed caption")
        call(af.command_visual_render, run_id=run["run_id"])
        directory, run = af.load_run(run["run_id"])
        self.record_text(directory, run, "article", '---\ndescription: "An imprecise old description needs revision."\n---\n\n' + af.artifact_path(directory, run, "draft").read_text(encoding="utf-8"))
        self.record_json(directory, run, "brief", {"slug": "competing-effects", "title": "Two competing effects", "description": "The supported competing effects remain uncertain."}, "review-brief.json")
        for kind in ("verified-claim-ledger", "post-edit-claim-ledger", "voice-learning"):
            self.record_json(directory, run, kind, {})
        af.transition(directory, run, "EDITORIAL_QA", "test", "Original review inputs")
        with af.run_lock(directory, run):
            packet_path, packet = af.task_packet(directory, run)
        return directory, run, packet_path, packet

    def legacy_obligation(self, directory, run, packet_path, packet, excerpt):
        finding = {"criterion": "contextual_naturalness", "artifact": "article", "location": excerpt,
                   "finding": "The assessed language needs a focused correction.",
                   "repair_instruction": "Repair the affected prose while preserving its proposition and locked material.", "repair_state": "EDIT"}
        assessment = {"outcome": "REPAIR", "findings": [], "dimensions": {}}
        self.record_json(directory, run, "editorial-qa", assessment)
        af.write_gate_receipt(directory, run, "G-EDITORIAL-QA", "REPAIR", [finding], {"type": "test"}, "EDIT",
                              task_state="EDITORIAL_QA", task_attempt=packet["attempt"], task_packet_sha256=af.sha256_path(packet_path))
        context.record_assessment(af, directory, run, assessment, [finding], "REPAIR")
        old_path = af.artifact_path(directory, run, "editorial-repair-obligations")
        return finding, old_path, old_path.read_bytes(), af.load_json(old_path)["pending"][0]

    def test_new_naturalization_findings_use_visual_display_and_body_owners(self):
        directory, run, _, _ = self.prepared()
        caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
        for excerpt, expected in ((caption, "VISUAL_PLAN"), ("An imprecise old description needs revision.", "EDIT"), (af.json_artifact(directory, run, "brief")["description"], "DISPLAY_REVISION"), (self.anchor, "EDIT")):
            with self.subTest(expected=expected):
                review = {key: {"status": "PASS", "excerpt": self.anchor, "reason": "The excerpt explains the specific competing mechanisms clearly."} for key in ("language", "rhetoric", "structure", "preservation")}
                review["language"].update(status="REPAIR", excerpt=excerpt)
                findings = af.naturalization_review_findings(directory, run, {"naturalization_review": review}, "qa")
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["repair_state"], expected)
                self.assertNotEqual(findings[0]["location"], excerpt)
        self.assertEqual(context.current_excerpt_owner(af, directory, run, self.anchor)["location"], "paragraph 1")

    def test_legacy_caption_normalization_keeps_identity_and_requires_specific_resolution(self):
        directory, run, packet_path, packet = self.prepared()
        caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
        finding, old_path, old_bytes, old = self.legacy_obligation(directory, run, packet_path, packet, caption)
        recovered = context.normalized_obligations(af, directory, run)["pending"][0]
        self.assertEqual(recovered["id"], old["id"])
        self.assertEqual(recovered["finding"], finding)
        self.assertEqual(recovered["source_sha256"], old["source_sha256"])
        self.assertEqual(recovered["normalization"]["selector"]["location"], "visual:competing-effects:caption")
        self.assertEqual(old_path.read_bytes(), old_bytes)
        reason = "The prose explains both mechanisms; the omitted graph would imply an unsupported relationship."
        plan_path = self.record_json(directory, run, "visual-plan", {"visual_plan_schema_version": "1.0.0", "run_id": run["run_id"], "visuals": [], "omission_reason": reason}, "omitted-plan.json")
        self.record_json(directory, run, "visual-manifest", {"visual_manifest_schema_version": "1.0.0", "run_id": run["run_id"], "visual_plan_sha256": af.sha256_path(plan_path), "assets": [], "omission_reason": reason}, "omitted-manifest.json")
        resolution = {"status": "PASS", "surface": "visual-plan+manifest", "finding_location": finding["location"], "excerpt": self.anchor, "reason": "This unrelated prose is not evidence about the bound caption."}
        assessment = {"outcome": "PASS", "findings": [], "dimensions": {"repair_resolution": {old["id"]: resolution}}}
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        resolution["excerpt"] = reason
        self.assertEqual(context.assessment_findings(af, directory, run, assessment), [])
        context.record_assessment(af, directory, run, assessment, [], "PASS")
        self.assertEqual(af.json_artifact(directory, run, "editorial-repair-obligations")["pending"], [])
        self.assertEqual(old_path.read_bytes(), old_bytes)

    def test_recovery_requires_intact_original_sources_and_display_field(self):
        directory, run, packet_path, packet = self.prepared()
        excerpt = "An imprecise old description needs revision."
        _, _, _, old = self.legacy_obligation(directory, run, packet_path, packet, excerpt)
        recovered = context.normalized_obligations(af, directory, run)["pending"][0]
        self.assertEqual(recovered["normalization"]["selector"], {"artifact": "article", "location": "frontmatter.description", "repair_state": "EDIT"})
        resolution = {"status": "PASS", "surface": "brief.description", "finding_location": excerpt, "excerpt": self.anchor, "reason": "A body passage cannot clear the separately owned description."}
        assessment = {"outcome": "PASS", "findings": [], "dimensions": {"repair_resolution": {old["id"]: resolution}}}
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        resolution["excerpt"] = af.json_artifact(directory, run, "brief")["description"]
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        resolution["surface"] = "article.frontmatter.description"
        self.assertTrue(context.assessment_findings(af, directory, run, assessment))
        article = af.artifact_path(directory, run, "article").read_text(encoding="utf-8").replace(excerpt, resolution["excerpt"])
        self.record_text(directory, run, "article", article, "corrected-frontmatter.md")
        self.assertEqual(context.assessment_findings(af, directory, run, assessment), [])

        other_directory, other_run, source_path, other_packet = self.prepared()
        self.legacy_obligation(other_directory, other_run, source_path, other_packet, excerpt)
        source_path.write_bytes(source_path.read_bytes() + b' ')
        with self.assertRaisesRegex(af.FlowError, "recovery source changed"):
            context.normalized_obligations(af, other_directory, other_run)

    def test_ambiguous_or_unproven_locations_stay_unresolved(self):
        directory, run, packet_path, packet = self.prepared()
        missing = "This was never part of the original reviewed article."
        _, _, _, old = self.legacy_obligation(directory, run, packet_path, packet, missing)
        pending = context.normalized_obligations(af, directory, run)["pending"][0]
        self.assertNotIn("normalization", pending)
        self.assertEqual(pending["id"], old["id"])
        self.assertIsNone(context.excerpt_owner(af, self.anchor + '\n\n' + self.anchor, {}, {}, self.anchor))
        self.assertIsNone(context.excerpt_owner(af, "# Body\n", {"title": missing, "description": missing}, {}, missing))

    def test_recovery_reads_original_sources_after_later_artifacts_replace_the_index(self):
        for replaced in ("article", "brief", "visual-manifest", "gate-receipt", "all"):
            with self.subTest(replaced=replaced):
                directory, run, packet_path, packet = self.prepared()
                caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
                finding, old_path, old_bytes, old = self.legacy_obligation(directory, run, packet_path, packet, caption)
                if replaced in {"article", "all"}:
                    self.record_text(directory, run, "article", "# A corrected article\n\nThe current explanation is different.\n", "later-article.md")
                if replaced in {"brief", "all"}:
                    self.record_json(directory, run, "brief", {"title": "A later title", "description": "A later description."}, "later-brief.json")
                if replaced in {"visual-manifest", "all"}:
                    self.record_json(directory, run, "visual-manifest", {"assets": []}, "later-manifest.json")
                if replaced in {"gate-receipt", "all"}:
                    af.write_gate_receipt(directory, run, "G-EDITORIAL-QA", "REPAIR", [], {"type": "test"}, "EDITORIAL_QA")
                recovered = context.normalized_obligations(af, directory, run)["pending"][0]
                self.assertEqual(recovered["id"], old["id"])
                self.assertEqual(recovered["finding"], finding)
                self.assertEqual(recovered["normalization"]["selector"]["location"], "visual:competing-effects:caption")
                self.assertEqual(old_path.read_bytes(), old_bytes)

    def test_recovery_rejects_tampered_historical_sources_and_event_chain(self):
        for changed in ("article", "brief", "visual-manifest", "gate-receipt:G-EDITORIAL-QA", "events"):
            with self.subTest(changed=changed):
                directory, run, packet_path, packet = self.prepared()
                caption = af.json_artifact(directory, run, "visual-manifest")["assets"][0]["caption"]
                self.legacy_obligation(directory, run, packet_path, packet, caption)
                path = directory / run["event_log"] if changed == "events" else af.artifact_path(directory, run, changed)
                if changed == "events":
                    path.write_bytes(path.read_bytes().replace(b'"test"', b'"changed"', 1))
                else:
                    path.write_bytes(path.read_bytes() + b' ')
                with self.assertRaisesRegex(af.FlowError, "recovery (source|event history) changed"):
                    context.normalized_obligations(af, directory, run)

    def test_late_visual_amendment_cannot_reuse_old_prose_in_a_qa_fallback(self):
        directory, run, packet_path, packet = self.prepared()
        old_bytes = packet_path.read_bytes()
        old_article = next(i for i in packet["inputs"] if i["id"] == "article")
        with af.run_lock(directory, run):
            af.abandon_cached_packet(directory, run, "EDITORIAL_QA", af.latest_task_packet_item(directory, run, "EDITORIAL_QA"), {"reason": "fixture_provider_failure"})
            run.setdefault("route_retry_candidates", {})["EDITORIAL_QA"] = packet["selected_route"]["candidates"]
            af.save_run(directory, run)
        call(af.command_amend, run_id=run["run_id"], diagrams="off", title=None, description=None, article=None,
             reason="A reviewed graph implies an unsupported relationship; omit it and reassess current prose.")
        directory, run = af.load_run(run["run_id"])
        self.assertNotIn("EDITORIAL_QA", run.get("route_retry_candidates", {}))
        self.record_json(directory, run, "visual-plan", {"visual_plan_schema_version": "1.0.0", "run_id": run["run_id"], "visuals": [],
                         "omission_reason": "The prose explains both mechanisms without the misleading graph."}, "late-empty-plan.json")
        af.transition(directory, run, "VISUAL_RENDER", "test", "Render the checked omission")
        call(af.command_visual_render, run_id=run["run_id"])
        directory, run = af.load_run(run["run_id"])
        self.record_json(directory, run, "post-edit-claim-ledger", {"checked_revision": "current"}, "later-claims.json")
        self.record_json(directory, run, "brief", {"title": "Two competing effects", "description": "Current scoped description."}, "later-display.json")
        af.transition(directory, run, "EDITORIAL_QA", "test", "Return after renewed verification")
        self.assertNotEqual(af.artifact(run, "article")["sha256"], old_article["sha256"])
        # Also exercise stale cached authority independently of the epoch reset.
        run.setdefault("route_retry_candidates", {})["EDITORIAL_QA"] = packet["selected_route"]["candidates"]
        with af.run_lock(directory, run):
            _, renewed = af.task_packet(directory, run)
        inputs = {i["id"]: i for i in renewed["inputs"]}
        for kind in ("article", "brief", "post-edit-claim-ledger", "visual-plan", "visual-manifest"):
            self.assertEqual(inputs[kind]["sha256"], af.artifact(run, kind)["sha256"])
        self.assertTrue(af.qa_packet_has_current_visuals(directory, run, renewed))
        self.assertEqual(packet_path.read_bytes(), old_bytes)

    def test_draft_caption_ownership_requires_the_exact_manifest_image_path(self):
        directory, run, _, _ = self.prepared()
        manifest = af.json_artifact(directory, run, "visual-manifest")
        visual = manifest["assets"][0]
        caption = "An old internal production note must be removed."
        image = "![A conceptual relationship](" + visual["public_path"] + ")\n\n*" + caption + "*"
        selector = context.excerpt_owner(af, image, {}, manifest, caption)
        self.assertEqual(selector, {"artifact": "visual-manifest", "location": "visual:competing-effects:caption", "repair_state": "VISUAL_PLAN"})
        other = image.replace(visual["public_path"], "/assets/unrelated.svg")
        self.assertEqual(context.excerpt_owner(af, other, {}, manifest, caption)["repair_state"], "EDIT")
        self.assertIsNone(context.excerpt_owner(af, image + "\n\n" + image, {}, manifest, caption))
