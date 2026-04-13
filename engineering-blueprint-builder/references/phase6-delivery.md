# Phase 6: Delivery — Validation, Conversion & Delivery Protocol

**Purpose:** Validate the DOCX is well-formed, convert to PDF if needed, and deliver to user.

---

## Step 1: ZIP Integrity Check

Every DOCX is a ZIP file. Verify it's valid.

```python
import zipfile
import sys

def validate_docx_zip(docx_path):
    """Check if DOCX file is a valid ZIP."""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            # Test all files in the ZIP
            bad_files = z.testzip()
            if bad_files:
                print(f'✗ Corrupt ZIP: {bad_files}')
                return False
        print(f'✓ ZIP integrity valid')
        return True
    except zipfile.BadZipFile:
        print(f'✗ Not a valid ZIP file')
        return False
    except Exception as e:
        print(f'✗ Error: {e}')
        return False
```

---

## Step 2: XML Well-Formedness Check

DOCX contains XML files. Parse them to verify structure.

```python
import xml.etree.ElementTree as ET
import zipfile

def validate_docx_xml(docx_path):
    """Check if all XML files in DOCX are well-formed."""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            for name in z.namelist():
                if name.endswith('.xml') or name.endswith('.rels'):
                    try:
                        xml_content = z.read(name)
                        ET.fromstring(xml_content)
                    except ET.ParseError as e:
                        print(f'✗ Malformed XML in {name}: {e}')
                        return False
        
        print(f'✓ All XML well-formed')
        return True
    except Exception as e:
        print(f'✗ Error: {e}')
        return False
```

---

## Step 3: Structural Validation

Count key elements to verify content is present.

```python
import zipfile
import xml.etree.ElementTree as ET

def validate_docx_structure(docx_path):
    """Check document structure (paragraphs, tables, images, bookmarks)."""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            # Read main document XML
            doc_xml = z.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # Define namespaces
            ns = {
                'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
                'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
                'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
            }
            
            # Count elements
            paragraphs = root.findall('.//w:p', ns)
            tables = root.findall('.//w:tbl', ns)
            images = root.findall('.//wp:inline', ns)
            bookmarks = root.findall('.//w:bookmarkStart', ns)
            
            print(f'✓ Paragraphs: {len(paragraphs)}')
            print(f'✓ Tables: {len(tables)}')
            print(f'✓ Images: {len(images)}')
            print(f'✓ Bookmarks: {len(bookmarks)}')
            
            # Validation rules
            if len(paragraphs) < 10:
                print(f'⚠ Warning: Document has very few paragraphs ({len(paragraphs)})')
            
            if len(tables) == 0 and 'table' in docx_path.lower():
                print(f'⚠ Warning: Document filename mentions "table" but has no tables')
            
            return True
    except Exception as e:
        print(f'✗ Error: {e}')
        return False
```

---

## Step 4: Bookmark Uniqueness Check (Informational)

Verify no duplicate bookmark IDs (doesn't block delivery, but helps debugging).

```python
import zipfile
import xml.etree.ElementTree as ET

def check_bookmark_uniqueness(docx_path):
    """Report if there are duplicate bookmarks (informational only)."""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            doc_xml = z.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            bookmarks = {}
            for bm in root.findall('.//w:bookmarkStart', ns):
                bm_id = bm.get('{' + ns['w'] + '}name')
                if bm_id:
                    if bm_id in bookmarks:
                        print(f'⚠ Duplicate bookmark: {bm_id}')
                    else:
                        bookmarks[bm_id] = True
            
            if not bookmarks:
                print(f'ℹ No bookmarks found')
            else:
                print(f'✓ {len(bookmarks)} unique bookmarks')
            
            return True
    except Exception as e:
        print(f'✗ Error: {e}')
        return False
```

---

## Step 5: PDF Conversion (Optional)

Convert DOCX to PDF using LibreOffice.

### Option A: System LibreOffice (if available)

```bash
soffice --headless --convert-to pdf blueprint.docx
```

### Option B: Python LibreOffice Integration

```python
import subprocess
import os

def convert_docx_to_pdf(docx_path, output_dir=None):
    """Convert DOCX to PDF using LibreOffice."""
    
    if not os.path.exists(docx_path):
        print(f'✗ File not found: {docx_path}')
        return None
    
    if output_dir is None:
        output_dir = os.path.dirname(docx_path)
    
    try:
        # Run LibreOffice conversion
        result = subprocess.run([
            'soffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            docx_path,
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f'✗ Conversion failed: {result.stderr}')
            return None
        
        # Derive PDF filename
        base = os.path.splitext(os.path.basename(docx_path))[0]
        pdf_path = os.path.join(output_dir, f'{base}.pdf')
        
        if os.path.exists(pdf_path):
            size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            print(f'✓ PDF generated: {pdf_path} ({size_mb:.1f} MB)')
            return pdf_path
        else:
            print(f'✗ PDF not created at expected path')
            return None
    
    except subprocess.TimeoutExpired:
        print(f'✗ Conversion timeout (>60 seconds)')
        return None
    except Exception as e:
        print(f'✗ Error: {e}')
        return None
```

---

## Step 6: Copy to Workspace Folder

Move validated DOCX (and optionally PDF) to the workspace folder.

```python
import shutil
import os

def copy_to_workspace(source_file, workspace_dir='./blueprints'):
    """Copy generated file to workspace folder."""
    
    # Create workspace if needed
    os.makedirs(workspace_dir, exist_ok=True)
    
    if not os.path.exists(source_file):
        print(f'✗ Source file not found: {source_file}')
        return None
    
    filename = os.path.basename(source_file)
    dest_path = os.path.join(workspace_dir, filename)
    
    try:
        shutil.copy2(source_file, dest_path)
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f'✓ Copied to workspace: {dest_path} ({size_mb:.1f} MB)')
        return dest_path
    except Exception as e:
        print(f'✗ Copy failed: {e}')
        return None
```

---

## Step 7: Delivery Format & Links

### Computer:// Links (Primary)

Present files to user as clickable cards using `mcp__cowork__present_files`.

```python
def deliver_blueprints(files):
    """
    Present generated files to user.
    
    files: list of absolute file paths
    Example: ['/workspace/blueprint.docx', '/workspace/blueprint.pdf']
    """
    
    file_cards = [
        {'file_path': f} for f in files if os.path.exists(f)
    ]
    
    # In actual integration, call mcp__cowork__present_files with file_cards
    
    print('Blueprints ready:')
    for card in file_cards:
        filepath = card['file_path']
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f'  - {os.path.basename(filepath)} ({size_mb:.1f} MB)')
        print(f'    computer://{filepath}')
```

### Grouped by Language (Bilingual Support)

If bilingual, organize files:

```python
def deliver_bilingual_blueprints(docx_en, docx_zh, pdf_en=None, pdf_zh=None):
    """Present bilingual blueprints organized by language."""
    
    print('\n📄 English Version')
    print(f'  DOCX: computer://{docx_en}')
    if pdf_en:
        print(f'  PDF:  computer://{pdf_en}')
    
    print('\n📄 Chinese Version (中文)')
    print(f'  DOCX: computer://{docx_zh}')
    if pdf_zh:
        print(f'  PDF:  computer://{pdf_zh}')
    
    print('\n✓ All blueprints ready. Click to download.')
```

---

## Complete Validation Pipeline

Combine all checks into one script:

```python
#!/usr/bin/env python3

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
import subprocess
import shutil

def full_validation_and_delivery(docx_path, convert_to_pdf=False, workspace_dir='./blueprints'):
    """
    Complete validation and delivery pipeline.
    
    Returns: dict with 'docx_path', 'pdf_path' (if generated), 'success' (bool)
    """
    
    result = {
        'docx_path': None,
        'pdf_path': None,
        'success': False,
    }
    
    print(f'\n=== VALIDATING {os.path.basename(docx_path)} ===\n')
    
    # Step 1: ZIP integrity
    if not validate_docx_zip(docx_path):
        print('\n✗ Validation failed at ZIP integrity check')
        return result
    
    # Step 2: XML well-formedness
    if not validate_docx_xml(docx_path):
        print('\n✗ Validation failed at XML check')
        return result
    
    # Step 3: Structural validation
    if not validate_docx_structure(docx_path):
        print('\n✗ Validation failed at structure check')
        return result
    
    # Step 4: Bookmark check (informational)
    check_bookmark_uniqueness(docx_path)
    
    # Step 5: Copy to workspace
    workspace_path = copy_to_workspace(docx_path, workspace_dir)
    if not workspace_path:
        print('\n✗ Failed to copy to workspace')
        return result
    
    result['docx_path'] = workspace_path
    
    # Step 6: Optional PDF conversion
    if convert_to_pdf:
        pdf_path = convert_docx_to_pdf(workspace_path, os.path.dirname(workspace_path))
        if pdf_path:
            result['pdf_path'] = pdf_path
    
    # Step 7: Success!
    result['success'] = True
    print(f'\n✓ All validations passed\n')
    
    return result

# ===== HELPER FUNCTIONS (from above) =====

def validate_docx_zip(docx_path):
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            bad_files = z.testzip()
            if bad_files:
                print(f'✗ Corrupt ZIP: {bad_files}')
                return False
        print(f'✓ ZIP integrity valid')
        return True
    except zipfile.BadZipFile:
        print(f'✗ Not a valid ZIP file')
        return False
    except Exception as e:
        print(f'✗ Error: {e}')
        return False

def validate_docx_xml(docx_path):
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            for name in z.namelist():
                if name.endswith('.xml') or name.endswith('.rels'):
                    try:
                        xml_content = z.read(name)
                        ET.fromstring(xml_content)
                    except ET.ParseError as e:
                        print(f'✗ Malformed XML in {name}: {e}')
                        return False
        print(f'✓ All XML well-formed')
        return True
    except Exception as e:
        print(f'✗ Error: {e}')
        return False

def validate_docx_structure(docx_path):
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            doc_xml = z.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            paragraphs = root.findall('.//w:p', ns)
            tables = root.findall('.//w:tbl', ns)
            images = root.findall('.//wp:inline', ns)
            bookmarks = root.findall('.//w:bookmarkStart', ns)
            
            print(f'✓ Paragraphs: {len(paragraphs)}')
            print(f'✓ Tables: {len(tables)}')
            print(f'✓ Images: {len(images)}')
            print(f'✓ Bookmarks: {len(bookmarks)}')
            return True
    except Exception as e:
        print(f'✗ Error: {e}')
        return False

def check_bookmark_uniqueness(docx_path):
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            doc_xml = z.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            bookmarks = {}
            for bm in root.findall('.//w:bookmarkStart', ns):
                bm_id = bm.get('{' + ns['w'] + '}name')
                if bm_id and bm_id not in bookmarks:
                    bookmarks[bm_id] = True
            
            print(f'✓ {len(bookmarks)} unique bookmarks')
    except:
        pass

def convert_docx_to_pdf(docx_path, output_dir=None):
    if output_dir is None:
        output_dir = os.path.dirname(docx_path)
    
    try:
        result = subprocess.run([
            'soffice', '--headless', '--convert-to', 'pdf',
            '--outdir', output_dir, docx_path,
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f'✗ Conversion failed: {result.stderr}')
            return None
        
        base = os.path.splitext(os.path.basename(docx_path))[0]
        pdf_path = os.path.join(output_dir, f'{base}.pdf')
        
        if os.path.exists(pdf_path):
            size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            print(f'✓ PDF generated: {os.path.basename(pdf_path)} ({size_mb:.1f} MB)')
            return pdf_path
    except:
        print(f'✗ PDF conversion failed')
    
    return None

def copy_to_workspace(source_file, workspace_dir='./blueprints'):
    os.makedirs(workspace_dir, exist_ok=True)
    filename = os.path.basename(source_file)
    dest_path = os.path.join(workspace_dir, filename)
    
    try:
        shutil.copy2(source_file, dest_path)
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        print(f'✓ Copied: {os.path.basename(dest_path)} ({size_mb:.1f} MB)')
        return dest_path
    except Exception as e:
        print(f'✗ Copy failed: {e}')
        return None

# ===== USAGE =====

if __name__ == '__main__':
    # Example
    docx_file = sys.argv[1] if len(sys.argv) > 1 else 'blueprint.docx'
    result = full_validation_and_delivery(docx_file, convert_to_pdf=True)
    
    if result['success']:
        print(f'\n✓ DELIVERY READY')
        print(f'  DOCX: {result["docx_path"]}')
        if result['pdf_path']:
            print(f'  PDF:  {result["pdf_path"]}')
    else:
        print(f'\n✗ DELIVERY FAILED')
        sys.exit(1)
```

---

## Delivery Checklist

Before presenting files to user:

- [ ] ZIP integrity verified (all files readable)
- [ ] XML well-formed (no parsing errors)
- [ ] Document structure valid (>10 paragraphs, expected tables/images)
- [ ] Bookmark uniqueness checked (reported)
- [ ] Files copied to workspace folder
- [ ] PDF generated (if requested)
- [ ] File sizes reasonable (>100KB, <50MB)
- [ ] Files open in Word/Google Docs without errors
- [ ] All images embedded and visible
- [ ] TOC bookmarks clickable
- [ ] No password/encryption (open fully)

**IMPORTANT:** Never post-process .docx with Python zipfile repack. This causes corruption. Assembly must be 100% complete in Node.js phase.

---

## Delivery Output

```
✓ Blueprints Ready for Download

English Version:
  DOCX: computer:///workspace/blueprints/blueprint_2026-04-12.docx (2.3 MB)
  PDF:  computer:///workspace/blueprints/blueprint_2026-04-12.pdf (1.8 MB)

Chinese Version (中文):
  DOCX: computer:///workspace/blueprints/blueprint_2026-04-12_zh.docx (2.5 MB)
  PDF:  computer:///workspace/blueprints/blueprint_2026-04-12_zh.pdf (1.9 MB)

All files validated. Open in Word, Google Docs, or your PDF viewer.
```
