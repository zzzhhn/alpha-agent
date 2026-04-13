/**
 * Reusable helper functions for docx-js document generation.
 * Import these into your generator script to avoid repeating boilerplate.
 *
 * Usage:
 *   const h = require("./docx_helpers");
 *   const sections = [];
 *   sections.push(h.heading("Module 1", HeadingLevel.HEADING_1, "mod1"));
 *   sections.push(h.para([h.bold("Status: "), "Operational"]));
 *   sections.push(h.simpleTable(["Col A", "Col B"], [["a1","b1"]], [4680, 4680]));
 */

const {
  Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  InternalHyperlink, Bookmark, AlignmentType, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageBreak,
  PositionalTab, PositionalTabAlignment, PositionalTabRelativeTo, PositionalTabLeader,
} = require("docx");
const fs = require("fs");

// ── Color constants ──
const BLUE = "1B4F72";
const ACCENT = "2E75B6";
const TABLE_HEADER_BG = "1B4F72";
const TABLE_ALT_BG = "F2F7FB";
const BORDER_COLOR = "BDC3C7";
const GREEN = "27AE60";
const RED = "E74C3C";

// ── Layout constants ──
const border = { style: BorderStyle.SINGLE, size: 1, color: BORDER_COLOR };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };
const PAGE_W = 12240;  // US Letter width in DXA
const MARGIN = 1440;   // 1 inch
const CONTENT_W = PAGE_W - 2 * MARGIN;  // 9360

// ── Bookmark counter ──
let _bm = 200;
function resetBookmarkCounter(start = 200) { _bm = start; }

// ── Text helpers ──

function heading(text, level, bookmarkId) {
  if (bookmarkId) {
    return new Paragraph({
      heading: level,
      children: [new Bookmark({ id: `bm_${_bm++}`, children: [new TextRun(text)] })],
    });
  }
  return new Paragraph({ heading: level, children: [new TextRun(text)] });
}

function para(text, opts = {}) {
  const runs = Array.isArray(text)
    ? text.map(t => typeof t === "string" ? new TextRun(t) : new TextRun(t))
    : [new TextRun(typeof text === "string" ? text : text)];
  return new Paragraph({ children: runs, spacing: { after: 120 }, ...opts });
}

function bold(text) { return { text, bold: true }; }
function italic(text) { return { text, italics: true }; }
function colored(text, color) { return { text, color }; }

function bulletItem(text, ref = "bullets") {
  const runs = Array.isArray(text)
    ? text.map(t => typeof t === "string" ? new TextRun(t) : new TextRun(t))
    : [new TextRun(text)];
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: runs,
    spacing: { after: 60 },
  });
}

function numberItem(text, ref = "numbers") {
  const runs = Array.isArray(text)
    ? text.map(t => typeof t === "string" ? new TextRun(t) : new TextRun(t))
    : [new TextRun(text)];
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: runs,
    spacing: { after: 60 },
  });
}

// ── Table helpers ──

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: TABLE_HEADER_BG, type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({
      children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })],
      alignment: AlignmentType.LEFT,
    })],
  });
}

function dataCell(text, width, opts = {}) {
  const runs = Array.isArray(text)
    ? text.map(t => typeof t === "string"
        ? new TextRun({ text: t, font: "Arial", size: 20 })
        : new TextRun({ font: "Arial", size: 20, ...t }))
    : [new TextRun({ text: String(text), font: "Arial", size: 20 })];
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: opts.bg ? { fill: opts.bg, type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: [new Paragraph({ children: runs, alignment: AlignmentType.LEFT })],
  });
}

function simpleTable(headers, rows, colWidths) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      new TableRow({ children: headers.map((h, i) => headerCell(h, colWidths[i])) }),
      ...rows.map((row, ri) =>
        new TableRow({
          children: row.map((c, ci) =>
            dataCell(c, colWidths[ci], { bg: ri % 2 === 1 ? TABLE_ALT_BG : undefined })
          ),
        })
      ),
    ],
  });
}

// ── Layout helpers ──

function spacer(pts = 200) {
  return new Paragraph({ spacing: { after: pts }, children: [] });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ── TOC helpers ──

function tocEntry(text, anchor, indent = 0) {
  return new Paragraph({
    indent: { left: indent * 360 },
    tabStops: [{ type: "right", position: CONTENT_W, leader: "dot" }],
    children: [
      new InternalHyperlink({
        anchor,
        children: [new TextRun({ text, style: "Hyperlink", font: "Arial", size: 22 })],
      }),
      new TextRun({
        children: [new PositionalTab({
          alignment: PositionalTabAlignment.RIGHT,
          relativeTo: PositionalTabRelativeTo.MARGIN,
          leader: PositionalTabLeader.DOT,
        })],
        font: "Arial",
        size: 22,
      }),
    ],
    spacing: { after: 80 },
  });
}

// ── Image helpers ──

function embedImage(filePath, widthPx, heightPx, altTitle, altDesc) {
  if (!fs.existsSync(filePath)) {
    console.warn(`Warning: Image not found: ${filePath}`);
    return para(`[Image not found: ${filePath}]`);
  }
  return new Paragraph({
    children: [new ImageRun({
      type: "png",
      data: fs.readFileSync(filePath),
      transformation: { width: widthPx, height: heightPx },
      altText: {
        title: altTitle || "Wireframe",
        description: altDesc || altTitle || "Wireframe diagram",
        name: altTitle || "wireframe",
      },
    })],
    spacing: { after: 120 },
  });
}

// ── Exports ──
module.exports = {
  // Colors
  BLUE, ACCENT, TABLE_HEADER_BG, TABLE_ALT_BG, BORDER_COLOR, GREEN, RED,
  // Layout
  border, borders, cellMargins, PAGE_W, MARGIN, CONTENT_W,
  // Functions
  resetBookmarkCounter,
  heading, para, bold, italic, colored,
  bulletItem, numberItem,
  headerCell, dataCell, simpleTable,
  spacer, pageBreak,
  tocEntry, embedImage,
};
