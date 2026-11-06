"""Real ZIP -> source validation -> owner -> rendering, including local captures."""
import json
import struct
import zipfile
import zlib
from unittest import mock

from test_external_revision_import import ExternalRevisionFixture, af, call, imported
import revision_bundle as bundle
import revision_images as captures


def png(color=b"\x00\x80\xff"):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 100, 100, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\x00' + color * 100) * 100)) + chunk(b'IEND', b''))


class RevisionBundleTests(ExternalRevisionFixture):
    def files(self, *, fallback=False, image=False):
        manifest = {'article_flow_bundle_version': '1.0.0', 'slug': self.slug,
                    'candidate_file': 'draft.revised.md', 'author_feedback_file': 'author-feedback.txt',
                    'source_file': None if fallback else 'source.json'}
        candidate = self.candidate.read_bytes()
        files = {'source.json': self.envelope.read_bytes(), 'author-feedback.txt': self.feedback.read_bytes(),
                 'README.txt': b'Private review notes, never article prose.'}
        if image:
            alt = 'A clean local capture illustrates the article with a visible example.'
            caption = 'An illustrative capture, separate from the original anecdote.'
            files['capture.png'] = png()
            manifest['images'] = [{'file': 'capture.png', 'alt_text': alt, 'caption': caption}]
            candidate += f'\n![{alt}](/assets/articles/{self.slug}/capture.png)\n\n{caption}\n'.encode()
        files['draft.revised.md'] = candidate
        files['revision-bundle.json'] = af.canonical_json(manifest)
        return files

    def archive(self, files, compression=zipfile.ZIP_DEFLATED):
        path = self.root / 'returned.zip'
        with zipfile.ZipFile(path, 'w', compression=compression) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return path

    def import_zip(self, files, **kw):
        return self.revise(bundle_file=str(self.archive(files)), source_file=None,
                           candidate_file=None, request_file=None, **kw)

    def test_zip_preserves_files_and_exact_retry_has_one_owner_despite_compression(self):
        files = self.files()
        code, one = self.import_zip(files)
        self.assertEqual(code, af.EXIT_OK, one)
        path = self.archive(files, zipfile.ZIP_STORED)
        _, two = self.revise(bundle_file=str(path), source_file=None, candidate_file=None, request_file=None)
        self.assertEqual(one['run_id'], two['run_id'])
        directory, run = af.load_run(one['run_id'])
        self.assertEqual(af.artifact_path(directory, run, 'external-revision-candidate').read_bytes(), files['draft.revised.md'])
        self.assertEqual(af.artifact_path(directory, run, 'revision-request').read_bytes(), self.feedback.read_bytes())

    def test_fallback_source_is_verified_once_and_retry_never_refreshes_identity(self):
        files = self.files(fallback=True)
        code, one = self.import_zip(files)
        self.assertEqual(code, af.EXIT_OK, one)
        with mock.patch.object(af.revision_sources, 'checked_snapshot', side_effect=AssertionError('retry fetched a new source')):
            _, two = self.import_zip(files)
        self.assertEqual(one['run_id'], two['run_id'])

    def test_zip_source_slug_mismatch_and_unauthorized_import_create_no_run(self):
        files = self.files()
        manifest = json.loads(files['revision-bundle.json']); manifest['slug'] = 'other-article'
        files['revision-bundle.json'] = af.canonical_json(manifest)
        with self.assertRaises(af.FlowError):
            self.import_zip(files)
        with self.assertRaises(af.FlowError):
            self.import_zip(self.files(), unattended_editorial=False, authorization=None)
        self.assertEqual(list(af.runs_root().glob('AF-*')), [])

    def test_capture_survives_actual_renderer_and_enters_package_and_live_asset_scope(self):
        files = self.files(image=True)
        code, result = self.import_zip(files)
        self.assertEqual(code, af.EXIT_OK, result)
        directory, run = af.load_run(result['run_id'])
        self.carry(directory, run, 'DRAFT'); self.carry(directory, run, 'VISUAL_PLAN')
        code, result = call(af.command_visual_render, run_id=run['run_id'], refresh=False)
        self.assertEqual(code, af.EXIT_OK, result)
        directory, run = af.load_run(run['run_id']); self.carry(directory, run, 'EDIT')
        self.record_json(directory, run, 'brief', {'title':'Original title', 'slug':self.slug, 'date':'2026-09-15', 'description':'A useful explanation', 'tags':[]})
        package = directory / 'package'
        outputs = af.render_publication_files(directory, run, package, af.package_metadata(directory, run))
        image = package / f'site/assets/articles/{self.slug}/capture.png'
        self.assertIn(image, outputs)
        self.assertEqual(image.read_bytes(), png())
        self.assertEqual(imported.assets(af, directory, run)[0]['sha256'], af.sha256_bytes(png()))
        article = (package / f'site/docs/{self.slug}.html').read_text(encoding='utf-8')
        self.assertIn(f'src="/assets/articles/{self.slug}/capture.png"', article)
        self.assertNotIn('Private review notes', article)
        af.atomic_write(package / 'public/article.md', af.artifact_path(directory, run, 'article').read_bytes())
        af.write_json(package / 'public/metadata.json', af.package_metadata(directory, run))
        af.write_json(package / 'public/assets.json', {'assets': []})
        af.write_json(package / 'package.json', {'package_revision': 'f' * 64,
            'public_files': [{'path':p.relative_to(package).as_posix(), 'sha256':af.sha256_path(p)} for p in outputs]})
        for output in outputs:
            self.pages['https://theproductiveprompter.com/' + output.relative_to(package / 'site').as_posix()] = output.read_bytes()
        self.pages['https://theproductiveprompter.com/'] = (package / 'site/index.html').read_bytes()
        expected = {key:(package / 'site' / rel).read_bytes() for key, rel in
                    {'blog':'docs/blog.html','homepage':'index.html','feed':'feed.xml','sitemap':'sitemap.xml'}.items()}
        self.pages[f'https://theproductiveprompter.com/assets/articles/{self.slug}/capture.png'] = b'Wrong live image'
        self.move(directory, run, 'LIVE_VERIFICATION')
        with mock.patch.object(af, 'live_discovery_scope', return_value=(expected, None)):
            code, result = call(af.command_verify_live, run_id=run['run_id'])
        self.assertEqual(code, af.EXIT_FAILED)
        self.assertEqual([check['name'] for check in result['checks'] if not check['ok']], ['visual_asset'])
        self.assertNotEqual(af.load_run(run['run_id'])[1].get('publication', {}).get('status'), 'VERIFIED')
        imported.assert_current_assets(af, run)
        target = self.repo / f'assets/articles/{self.slug}/capture.png'
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b'different bytes')
        with self.assertRaises(af.FlowError):
            imported.assert_current_assets(af, run)
        target.unlink()
        (directory / imported.assets(af, directory, run)[0]['source_path']).write_bytes(b'changed')
        with self.assertRaises(af.FlowError):
            imported.assets(af, directory, run)

    def test_invalid_or_undeclared_capture_is_rejected(self):
        files = self.files(image=True)
        files['capture.png'] = b'not an image'
        with self.assertRaises(af.FlowError):
            self.import_zip(files)
        files = self.files(image=True)
        manifest = json.loads(files['revision-bundle.json']); del manifest['images']
        files['revision-bundle.json'] = af.canonical_json(manifest)
        with self.assertRaises(af.FlowError):
            self.import_zip(files)
        self.assertEqual(list(af.runs_root().glob('AF-*')), [])

    def test_zip_rejects_traversal_duplicate_case_links_and_excessive_expansion(self):
        for name in ('../draft.md', '/draft.md', 'C:evil.md', 'a\\draft.md', 'CON.txt', 'nested/draft.md'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.read(self.archive({name:b'x'}).read_bytes())
        with self.assertRaises(ValueError):
            bundle.read(self.archive({'Draft.md':b'x','draft.md':b'x'}).read_bytes())
        path = self.root / 'link.zip'
        with zipfile.ZipFile(path,'w') as archive:
            info=zipfile.ZipInfo('link.md');info.external_attr=0o120777 << 16
            archive.writestr(info,b'elsewhere')
        with self.assertRaises(ValueError): bundle.read(path.read_bytes())
        with self.assertRaises(ValueError):
            bundle.read(self.archive({'huge.md':b'x' * (2 * 1024 * 1024 + 1)}).read_bytes())

    def test_capture_rejects_corrupt_png_private_metadata_and_overwrite(self):
        with self.assertRaises(ValueError):
            captures.dimensions(png()[:-12], '.png')
        # Correct CRC does not permit hidden textual metadata.
        payload = b'private note'; kind = b'tEXt'
        chunk = struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
        with self.assertRaises(ValueError):
            captures.dimensions(png()[:-12] + chunk + png()[-12:], '.png')
        files = self.files(image=True)
        target = self.repo / f'assets/articles/{self.slug}/capture.png'
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(png())
        with self.assertRaises(af.FlowError):
            self.import_zip(files)
        self.assertEqual(list(af.runs_root().glob('AF-*')), [])

    def test_capture_bytes_are_part_of_owner_identity(self):
        files = self.files(image=True)
        _, first = self.import_zip(files)
        files['capture.png'] = png(b'\xff\x80\x00')
        _, second = self.import_zip(files)
        self.assertNotEqual(first['run_id'], second['run_id'])
        _, retry = self.import_zip(files)
        self.assertEqual(second['run_id'], retry['run_id'])
