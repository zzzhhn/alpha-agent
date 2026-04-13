#!/bin/bash
# Convert .docx to .pdf using LibreOffice.
# Usage: bash convert_to_pdf.sh input.docx [output_dir]
#
# Tries multiple approaches:
#   1. soffice.py helper from docx skill (sandboxed environments)
#   2. Direct libreoffice command
#   3. soffice command
#
# Output: PDF file in the same directory as input (or output_dir if specified)

set -e

if [ -z "$1" ]; then
    echo "Usage: bash convert_to_pdf.sh input.docx [output_dir]"
    exit 1
fi

INPUT="$1"
OUTDIR="${2:-$(dirname "$INPUT")}"
BASENAME=$(basename "$INPUT" .docx)

if [ ! -f "$INPUT" ]; then
    echo "Error: File not found: $INPUT"
    exit 1
fi

# Try method 1: soffice.py helper (works in sandboxed Cowork environments)
SOFFICE_PY=""
for candidate in \
    "/sessions/*/mnt/.claude/skills/docx/scripts/office/soffice.py" \
    "$(dirname "$0")/../../docx/scripts/office/soffice.py"; do
    # shellcheck disable=SC2086
    for f in $candidate; do
        if [ -f "$f" ]; then
            SOFFICE_PY="$f"
            break 2
        fi
    done
done

if [ -n "$SOFFICE_PY" ]; then
    echo "Converting via soffice.py helper..."
    python3 "$SOFFICE_PY" --headless --convert-to pdf "$INPUT"
    # soffice.py outputs to CWD or a temp location; find and move the PDF
    PDF_NAME="${BASENAME}.pdf"
    for search_dir in "." "/tmp" "$(dirname "$INPUT")"; do
        if [ -f "${search_dir}/${PDF_NAME}" ]; then
            if [ "${search_dir}/${PDF_NAME}" != "${OUTDIR}/${PDF_NAME}" ]; then
                cp "${search_dir}/${PDF_NAME}" "${OUTDIR}/${PDF_NAME}"
            fi
            echo "✓ PDF saved: ${OUTDIR}/${PDF_NAME}"
            exit 0
        fi
    done
fi

# Try method 2: Direct libreoffice
if command -v libreoffice &>/dev/null; then
    echo "Converting via libreoffice..."
    libreoffice --headless --convert-to pdf --outdir "$OUTDIR" "$INPUT"
    echo "✓ PDF saved: ${OUTDIR}/${BASENAME}.pdf"
    exit 0
fi

# Try method 3: soffice
if command -v soffice &>/dev/null; then
    echo "Converting via soffice..."
    soffice --headless --convert-to pdf --outdir "$OUTDIR" "$INPUT"
    echo "✓ PDF saved: ${OUTDIR}/${BASENAME}.pdf"
    exit 0
fi

echo "Error: No LibreOffice installation found. Install libreoffice or use the docx skill's soffice.py."
exit 1
