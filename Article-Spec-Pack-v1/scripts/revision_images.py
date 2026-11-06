"""Explicit local raster imports, hashed separately from the source's assets."""
from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path
from typing import Any

import revision_bundle


def dimensions(data: bytes, suffix: str) -> tuple[int, int]:
    if suffix == '.png':
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError("PNG signature mismatch")
        pos = 8; size = None
        while pos < len(data):
            length = struct.unpack('>I', data[pos:pos + 4])[0]
            kind = data[pos + 4:pos + 8]; chunk = data[pos + 8:pos + 8 + length]
            crc = struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])[0]
            if len(chunk) != length or zlib.crc32(kind + chunk) & 0xffffffff != crc:
                raise ValueError("invalid PNG chunk")
            if size is None:
                if kind != b'IHDR' or length != 13:
                    raise ValueError("PNG requires IHDR")
                size = struct.unpack('>II', chunk[:8])
            if kind not in {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS', b'sRGB', b'gAMA', b'cHRM', b'pHYs', b'iCCP'}:
                raise ValueError("PNG contains unsupported metadata; export a clean capture")
            pos += 12 + length
            if kind == b'IEND':
                if pos != len(data) or length:
                    raise ValueError("PNG has trailing data")
                return size
        raise ValueError("PNG is incomplete")
    if suffix not in {'.jpg', '.jpeg'} or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError("only complete PNG/JPEG captures are supported")
    pos = 2; size = None
    while pos < len(data) - 2:
        if data[pos] != 255:
            raise ValueError("invalid JPEG marker")
        while data[pos] == 255:
            pos += 1
        marker = data[pos]; pos += 1
        length = struct.unpack('>H', data[pos:pos + 2])[0]
        if length < 2 or pos + length > len(data):
            raise ValueError("invalid JPEG segment")
        payload = data[pos + 2:pos + length]
        color_profile = marker == 0xe2 and payload.startswith(b'ICC_PROFILE\x00') and len(payload) >= 14 and 1 <= payload[12] <= payload[13]
        if marker == 0xfe or (0xe1 <= marker <= 0xef and marker != 0xee and not color_profile):
            raise ValueError("JPEG has EXIF, comment or unsupported application metadata; export a clean capture")
        if marker in {0xc0, 0xc1, 0xc2}:
            height, width = struct.unpack('>HH', data[pos + 3:pos + 7]); size = (width, height)
        if marker == 0xda:
            if size:
                return size
            raise ValueError("JPEG has no supported frame")
        pos += length
    raise ValueError("JPEG is incomplete")


def prepare(af: Any, args: Any, candidate: bytes, slug: str) -> tuple[list[dict], bytes | None]:
    value = getattr(args, 'image_plan_file', None)
    if not value:
        return [], None
    try:
        path = Path(value).resolve()
        raw = af.external_revision.read_utf8(af, str(path), 'Revision image plan')
        plan = revision_bundle.json_object(raw)
        if set(plan) != {'images'} or not isinstance(plan['images'], list) or not 1 <= len(plan['images']) <= 4:
            raise ValueError("image plan requires one to four images")
        text = af.external_revision.public_markdown(af, candidate).decode('utf-8').replace('\r\n', '\n')
        assets = []; seen = set()
        for image in plan['images']:
            if not isinstance(image, dict) or set(image) != {'file', 'sha256', 'alt_text', 'caption'}:
                raise ValueError("image fields must be file, sha256, alt_text and caption")
            name = revision_bundle.filename(image['file'])
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.(?:png|jpe?g)', name) or name in seen:
                raise ValueError("capture filenames must be unique lowercase slugs with PNG/JPEG extensions")
            seen.add(name)
            source = path.parent / name
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("capture is missing, linked or larger than 5 MiB")
            data = source.read_bytes()
            if af.sha256_bytes(data) != image['sha256']:
                raise ValueError("capture digest mismatch")
            width, height = dimensions(data, source.suffix)
            if min(width, height) < 80 or max(width, height) > 8000 or width * height > 32000000:
                raise ValueError("capture dimensions are outside the supported bounds")
            alt, caption = image['alt_text'], image['caption']
            if any(not isinstance(t, str) or not lo <= len(t) <= hi or re.search(r'[<>\[\]\r\n\x00-\x1f]', t) for t, lo, hi in ((alt,20,320),(caption,10,600))):
                raise ValueError("capture alt text and caption require bounded plain text")
            public = f'/assets/articles/{slug}/{name}'
            block = f'![{alt}]({public})\n\n{caption}'
            if text.count(block) != 1:
                raise ValueError("draft must contain exactly one declared image block followed by its exact caption")
            destination = (af.publication_repo_root(required=True) / public.lstrip('/')).resolve()
            if destination.exists():
                raise ValueError("new capture would overwrite an existing published asset")
            assets.append({'src': public, 'alt': alt, 'public_path': public, 'sha256': image['sha256'],
                           'bytes': data, 'imported': True, 'caption': caption, 'width': width, 'height': height})
        return assets, raw
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, struct.error, IndexError) as exc:
        raise af.FlowError(f'Invalid revision capture import: {exc}', af.EXIT_USAGE) from exc
