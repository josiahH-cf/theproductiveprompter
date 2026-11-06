"""Bounded review ZIP intake; archive text cannot grant publication authority."""
from __future__ import annotations

import argparse
import io
import json
import re
import stat
import zipfile
from pathlib import Path
from typing import Any


def json_object(data: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field: " + key)
            result[key] = value
        return result
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("JSON must be an object")
    return value


def filename(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("bundle files require plain flat filenames")
    if value.split('.')[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))} or value.endswith('.'):
        raise ValueError("reserved bundle filename")
    return value


def read(data: bytes) -> dict[str, bytes]:
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("ZIP exceeds 20 MiB")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= 24 or sum(item.file_size for item in entries) > 20 * 1024 * 1024:
            raise ValueError("ZIP has too many files or expanded bytes")
        result = {}; seen = set()
        for item in entries:
            name = filename(item.filename)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if name.casefold() in seen or mode not in (0, stat.S_IFREG) or item.flag_bits & 1:
                raise ValueError("duplicate, linked, special or encrypted ZIP member")
            if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError("bundle supports only stored or deflated ZIP members")
            seen.add(name.casefold())
            if not name.lower().endswith(('.json', '.md', '.txt', '.jpg', '.jpeg', '.png')):
                raise ValueError("unsupported ZIP file type")
            limit = 5 * 1024 * 1024 if name.lower().endswith(('.jpg', '.jpeg', '.png')) else 2 * 1024 * 1024
            if item.file_size > limit:
                raise ValueError("bundle member exceeds its size limit")
            result[name] = archive.read(item)  # checks CRC, including for unreferenced notes
        return result


def unpack(af: Any, args: Any) -> Any:
    if any(getattr(args, field, None) for field in ('handoff_file', 'source_file', 'candidate_file', 'request_file',
             'visual_plan_file', 'image_plan_file', 'source_run_id', 'published_slug', 'expected_source_sha256')):
        raise af.FlowError("--bundle-file supplies all inputs; do not combine input variants", af.EXIT_USAGE)
    try:
        with Path(args.bundle_file).expanduser().open('rb') as stream:
            data = stream.read(20 * 1024 * 1024 + 1)
        files = read(data)
        manifest = json_object(files['revision-bundle.json'])
        required = {'article_flow_bundle_version', 'slug', 'candidate_file', 'author_feedback_file', 'source_file'}
        if not required <= set(manifest) or set(manifest) - required - {'visual_plan_file', 'images'}:
            raise ValueError("unexpected or missing revision-bundle.json fields")
        if manifest['article_flow_bundle_version'] != '1.0.0' or not isinstance(manifest['slug'], str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', manifest['slug']):
            raise ValueError("unsupported bundle version or article slug")
        def member(key, suffix):
            name = filename(manifest[key])
            if not name.lower().endswith(suffix):
                raise ValueError("wrong file type for " + key)
            return name, files[name]
        candidate_name, candidate = member('candidate_file', '.md')
        feedback_name, feedback = member('author_feedback_file', ('.txt', '.md'))
        if candidate_name == feedback_name:
            raise ValueError("candidate and feedback require separate files")
        candidate.decode('utf-8'); feedback.decode('utf-8')
        visual_name = None
        visual_data = None
        if 'visual_plan_file' in manifest:
            visual_name, visual_data = member('visual_plan_file', '.json')
        images = manifest.get('images', [])
        if not isinstance(images, list) or len(images) > 4:
            raise ValueError("images must be a list of at most four local captures")
        normalized = []
        for image in images:
            if not isinstance(image, dict) or set(image) != {'file', 'alt_text', 'caption'}:
                raise ValueError("image requires file, alt_text and caption; place its image block in the draft")
            name = filename(image['file'])
            normalized.append({**image, 'sha256': af.sha256_bytes(files[name])})
        # Content, not ZIP timestamps/compression, owns extraction and fallback identity.
        bindings = {name: af.sha256_bytes(data) for name, data in sorted(files.items())}
        root = af.runs_root() / '.revision-bundles' / af.sha256_bytes(af.canonical_json(bindings))
        root.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            path = root / name
            if path.is_symlink():
                raise ValueError("bundle storage is a symbolic link")
            af.immutable_write(path, data)
        if manifest['source_file'] is None:
            # Notes, filenames and ZIP presentation cannot refresh source identity.
            source_key = {'slug': manifest['slug'], 'candidate': af.sha256_bytes(candidate),
                          'feedback': af.sha256_bytes(feedback), 'images': normalized,
                          'visual_plan': af.sha256_bytes(visual_data) if visual_data is not None else None}
            source_root = af.runs_root() / '.revision-bundle-sources' / af.sha256_bytes(af.canonical_json(source_key))
            source_root.mkdir(parents=True, exist_ok=True)
            source_path = source_root / 'source.json'
            # Reserve the fallback once; an exact retry must not refresh a stale source.
            with af.shared_lock(source_root / '.source.lock', wait_seconds=60):
                if not source_path.exists():
                    snapshot = af.revision_sources.checked_snapshot(af, manifest['slug'])
                    markdown, _ = af.external_revision.material(af, snapshot)
                    af.immutable_write(source_path, af.canonical_json(af.external_revision.identity(snapshot, markdown)))
        else:
            source_name, _ = member('source_file', '.json')
            source_path = root / source_name
        source = json_object(source_path.read_bytes())
        identity = source.get('source', source)
        if not isinstance(identity, dict) or identity.get('slug') != manifest['slug']:
            raise ValueError("bundle slug differs from source identity")
        result = argparse.Namespace(**vars(args))
        result.source_file = str(source_path)
        result.candidate_file = str(root / candidate_name)
        result.request_file = str(root / feedback_name)
        if visual_name is not None:
            result.visual_plan_file = str(root / visual_name)
        if images:
            path = root / '.image-plan.json'
            af.immutable_write(path, af.canonical_json({'images': normalized}))
            result.image_plan_file = str(path)
        return result
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise af.FlowError(f"Invalid Article Flow revision ZIP: {exc}", af.EXIT_USAGE) from exc
