#!/usr/bin/env python3
"""
Validate a .docx file for structural integrity before delivery.
Checks: ZIP validity, XML well-formedness, structural counts, bookmark consistency.

Usage:
    python validate_docx.py path/to/document.docx [--strict]

Exit code 0 = pass, 1 = fail (only in --strict mode for bookmark dupes).
"""
import sys
import os
import re
import zipfile
import xml.etree.ElementTree as ET


def validate(path, strict=False):
    name = os.path.basename(path)
    size_kb = os.path.getsize(path) / 1024
    errors = []
    warnings = []

    # 1. ZIP integrity
    try:
        z = zipfile.ZipFile(path, 'r')
        bad = z.testzip()
        if bad:
            errors.append(f"Corrupt ZIP entry: {bad}")
    except zipfile.BadZipFile as e:
        errors.append(f"Not a valid ZIP: {e}")
        _report(name, size_kb, errors, warnings, {})
        return len(errors) == 0

    # 2. Required entries
    required = ["[Content_Types].xml", "word/document.xml", "_rels/.rels"]
    for r in required:
        if r not in z.namelist():
            errors.append(f"Missing required entry: {r}")

    if errors:
        z.close()
        _report(name, size_kb, errors, warnings, {})
        return False

    # 3. XML well-formedness
    content = z.read("word/document.xml").decode("utf-8")
    try:
        ET.fromstring(content)
    except ET.ParseError as e:
        errors.append(f"document.xml malformed XML: {e}")

    # 4. Structural counts
    stats = {
        "paragraphs": len(re.findall(r'<w:p[ >]', content)),
        "tables": len(re.findall(r'<w:tbl>', content)),
        "images": len(re.findall(r'<a:blip', content)),
        "bookmarks_start": len(re.findall(r'<w:bookmarkStart', content)),
        "bookmarks_end": len(re.findall(r'<w:bookmarkEnd', content)),
    }

    if stats["paragraphs"] < 10:
        warnings.append(f"Very few paragraphs ({stats['paragraphs']}) — document may be nearly empty")

    # 5. Bookmark consistency
    bm_starts = re.findall(r'w:bookmarkStart[^>]*w:id="(\d+)"', content)
    bm_ends = re.findall(r'w:bookmarkEnd[^>]*w:id="(\d+)"', content)
    stats["bookmarks_unique"] = len(set(bm_starts)) == len(bm_starts)
    stats["bookmarks_matched"] = bm_starts == bm_ends

    if not stats["bookmarks_unique"]:
        msg = f"Duplicate bookmark IDs detected ({len(bm_starts)} starts, {len(set(bm_starts))} unique)"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg + " — Word tolerates this, not blocking")

    if not stats["bookmarks_matched"]:
        warnings.append("Bookmark start/end IDs don't fully match — minor spec violation")

    # 6. Image references
    rels_path = "word/_rels/document.xml.rels"
    if rels_path in z.namelist():
        rels = z.read(rels_path).decode("utf-8")
        img_targets = re.findall(r'Target="media/([^"]+)"', rels)
        media_files = [n.replace("word/media/", "") for n in z.namelist() if n.startswith("word/media/")]
        for target in img_targets:
            if target not in media_files:
                errors.append(f"Missing referenced image: word/media/{target}")

    z.close()
    _report(name, size_kb, errors, warnings, stats)
    return len(errors) == 0


def _report(name, size_kb, errors, warnings, stats):
    print(f"\n{'=' * 60}")
    print(f"  Validation: {name} ({size_kb:.0f} KB)")
    print(f"{'=' * 60}")

    if stats:
        print(f"  Paragraphs:  {stats.get('paragraphs', '?')}")
        print(f"  Tables:      {stats.get('tables', '?')}")
        print(f"  Images:      {stats.get('images', '?')}")
        print(f"  Bookmarks:   {stats.get('bookmarks_start', '?')} (unique: {stats.get('bookmarks_unique', '?')}, matched: {stats.get('bookmarks_matched', '?')})")

    if warnings:
        print(f"\n  ⚠ Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")

    if errors:
        print(f"\n  ✗ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")
    else:
        print(f"\n  ✓ PASSED")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_docx.py <path.docx> [--strict]")
        sys.exit(1)

    path = sys.argv[1]
    strict = "--strict" in sys.argv

    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    ok = validate(path, strict)
    sys.exit(0 if ok else 1)
