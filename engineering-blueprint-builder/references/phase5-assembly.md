# Phase 5: Assembly — Document Assembly via Node.js + docx Library

**Purpose:** Assemble all content (specs, visuals, architecture) into a production-grade DOCX. Use Node.js `docx` library locally, never globally.

---

## Setup

### npm Initialization
```bash
# In project directory
npm init -y
npm install docx
```

**Never use global install.** Always use local `node_modules/`.

---

## Helper Functions

Copy these into your document generation script (`generate_blueprint.js`).

```javascript
const { Document, Packer, Paragraph, Table, TableRow, TableCell, 
        TextRun, HeadingLevel, WidthType, BorderStyle, AlignmentType, 
        PageBreak, Image, InternalHyperlink, PositionalTab, Bookmark,
        convertInchesToTwip, PageNumber } = require('docx');

const fs = require('fs');
const path = require('path');

// ============= CONSTANTS =============

const COLOR = {
  BG: '0F1117',
  CARD_BG: '1A1D27',
  TEXT: 'E5E7EB',
  TEXT_DIM: '9CA3AF',
  ACCENT: '2E75B6',
  GREEN: '22C55E',
  RED: 'EF4444',
  YELLOW: 'F59E0B',
  BORDER: '30363D',
};

const BORDERS = {
  subtle: {
    top: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER },
    bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER },
    left: { style: BorderStyle.NONE },
    right: { style: BorderStyle.NONE },
  },
  full: {
    top: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER },
    bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER },
    left: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER },
    right: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER },
  },
  none: {
    top: { style: BorderStyle.NONE },
    bottom: { style: BorderStyle.NONE },
    left: { style: BorderStyle.NONE },
    right: { style: BorderStyle.NONE },
  },
};

// ============= TEXT FORMATTING =============

function heading(text, level = 1) {
  const fontSizes = { 1: 36, 2: 28, 3: 24 };
  const outlineLevels = { 1: 0, 2: 1, 3: 2 };
  
  return new Paragraph({
    text: text,
    heading: HeadingLevel[`HEADING_${level}`],
    style: `Heading${level}`,
    spacing: { before: level === 1 ? 400 : 200, after: 200 },
    outlineLevel: outlineLevels[level],
  });
}

function para(text, opts = {}) {
  const {
    color = COLOR.TEXT,
    size = 22,
    bold = false,
    italic = false,
    align = AlignmentType.LEFT,
    spacing_after = 100,
  } = opts;
  
  return new Paragraph({
    text: text,
    spacing: { after: spacing_after },
    alignment: align,
    run: {
      font: 'Arial',
      size: size * 2,  // docx uses half-points
      color: color,
      bold: bold,
      italic: italic,
    },
  });
}

function bold(text) {
  return new TextRun({
    text: text,
    bold: true,
    color: COLOR.ACCENT,
  });
}

function bulletItem(text, indent = 0) {
  return new Paragraph({
    text: text,
    bullet: { level: indent },
    spacing: { after: 100 },
  });
}

function numberItem(text, num, indent = 0) {
  return new Paragraph({
    text: text,
    numbering: { level: indent, reference: 'numbering-1' },
    spacing: { after: 100 },
  });
}

function headerCell(text) {
  return new TableCell({
    children: [new Paragraph({
      text: text,
      bold: true,
      color: COLOR.ACCENT,
    })],
    shading: { fill: COLOR.CARD_BG, type: 'clear' },
    borders: BORDERS.subtle,
    margins: { top: 100, bottom: 100, left: 100, right: 100 },
  });
}

function dataCell(text, opts = {}) {
  const { color = COLOR.TEXT, shading = null } = opts;
  
  return new TableCell({
    children: [new Paragraph({
      text: text,
      color: color,
    })],
    shading: shading ? { fill: shading, type: 'clear' } : null,
    borders: BORDERS.subtle,
    margins: { top: 100, bottom: 100, left: 100, right: 100 },
  });
}

function simpleTable(headers, rows, columnWidths = null) {
  const defaultWidths = new Array(headers.length).fill(100 / headers.length);
  const widths = columnWidths || defaultWidths;
  
  const headerRow = new TableRow({
    children: headers.map(h => headerCell(h)),
    height: { value: 400, rule: 'auto' },
  });
  
  const dataRows = rows.map(row => new TableRow({
    children: row.map((cell, idx) => dataCell(cell)),
    height: { value: 300, rule: 'auto' },
  }));
  
  return new Table({
    rows: [headerRow, ...dataRows],
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: BORDERS.full,
  });
}

function spacer(height = 200) {
  return new Paragraph({
    text: '',
    spacing: { after: height },
  });
}

function tocEntry(text, level = 1, bookmark = null) {
  const indent = level * 360;
  const opts = {
    children: [new Paragraph({
      text: text,
      indent: { left: indent },
    })],
  };
  
  if (bookmark) {
    opts.children[0] = new Paragraph({
      children: [
        new InternalHyperlink({
          children: [new TextRun({
            text: text,
            color: COLOR.ACCENT,
            underline: { type: 'single' },
          })],
          anchor: bookmark,
        }),
      ],
      indent: { left: indent },
    });
  }
  
  return opts.children[0];
}

function embedImage(imagePath, widthInches = 6, altText = 'Diagram') {
  // All three altText fields required
  return new Paragraph({
    children: [new Image({
      data: fs.readFileSync(imagePath),
      transformation: {
        width: convertInchesToTwip(widthInches),
        height: convertInchesToTwip(widthInches * 0.556),  // 16:9 aspect
      },
      altText: {
        title: altText,
        description: altText,
        name: altText,
      },
    })],
    alignment: AlignmentType.CENTER,
  });
}

// ============= PAGE SETUP =============

function pageSetup() {
  return {
    page: {
      margins: {
        top: convertInchesToTwip(1),
        bottom: convertInchesToTwip(1),
        left: convertInchesToTwip(1),
        right: convertInchesToTwip(1),
      },
      size: {
        width: 12240,  // 8.5 inches in twips
        height: 15840, // 11 inches in twips
      },
    },
  };
}

// ============= STYLES & NUMBERING =============

const defaultStyle = {
  styles: {
    normal: {
      name: 'Normal',
      basedOn: 'Normal',
      next: 'Normal',
      run: {
        font: 'Arial',
        size: 22,
        color: COLOR.TEXT,
      },
      paragraph: {
        spacing: { line: 360, lineRule: 'auto' },
      },
    },
    heading1: {
      basedOn: 'Normal',
      next: 'Normal',
      name: 'Heading 1',
      run: {
        font: 'Arial',
        size: 72,
        bold: true,
        color: COLOR.ACCENT,
      },
      paragraph: { outlineLevel: 0, spacing: { before: 400, after: 200 } },
    },
    heading2: {
      basedOn: 'Normal',
      next: 'Normal',
      name: 'Heading 2',
      run: {
        font: 'Arial',
        size: 56,
        bold: true,
        color: COLOR.ACCENT,
      },
      paragraph: { outlineLevel: 1, spacing: { before: 300, after: 200 } },
    },
    heading3: {
      basedOn: 'Normal',
      next: 'Normal',
      name: 'Heading 3',
      run: {
        font: 'Arial',
        size: 48,
        bold: true,
        color: COLOR.ACCENT,
      },
      paragraph: { outlineLevel: 2, spacing: { before: 200, after: 100 } },
    },
  },
};

const numbering = {
  config: [
    {
      reference: 'numbering-1',
      levels: [
        { level: 0, format: 'bullet', text: '•', alignment: AlignmentType.LEFT },
        { level: 1, format: 'bullet', text: '◦', alignment: AlignmentType.LEFT },
      ],
    },
  ],
};

// ============= HEADER & FOOTER =============

function createHeader(documentTitle) {
  return {
    default: new Paragraph({
      text: documentTitle,
      color: COLOR.TEXT_DIM,
      size: 18,
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.BORDER } },
      spacing: { after: 100 },
    }),
  };
}

function createFooter(includePageNumbers = true) {
  return {
    default: new Paragraph({
      text: includePageNumbers ? '' : '',
      alignment: AlignmentType.RIGHT,
      children: includePageNumbers ? [
        new TextRun({
          text: 'Page ',
          color: COLOR.TEXT_DIM,
          size: 18,
        }),
        new PageNumber(),
      ] : [],
    }),
  };
}

// ============= BOOKMARKS =============

function withBookmark(paragraph, bookmarkId) {
  // Wrap paragraph with bookmark range
  return new Paragraph({
    ...paragraph.properties,
    children: [
      new Bookmark({
        name: bookmarkId,
        children: paragraph.children || [new TextRun(paragraph.text || '')],
      }),
    ],
  });
}

// ============= BILINGUAL SUPPORT =============

const BOOKMARK_RANGES = {
  EN: {
    start: 100,
    TOC: 101,
    EXEC_SUMMARY: 110,
    MODULES: 200,
    ARCHITECTURE: 300,
    APPENDICES: 400,
  },
  ZH: {
    start: 500,
    TOC: 501,
    EXEC_SUMMARY: 510,
    MODULES: 600,
    ARCHITECTURE: 700,
    APPENDICES: 800,
  },
};

// ============= MAIN DOCUMENT BUILDER =============

async function generateBlueprint(config) {
  const {
    title = 'Engineering Blueprint',
    exec_summary = '',
    modules = [],
    architecture_image = null,
    bilingual = false,
  } = config;
  
  const sections = [];
  
  // ===== COVER PAGE =====
  sections.push(
    heading(title, 1),
    spacer(400),
    para(`Generated: ${new Date().toISOString().split('T')[0]}`, { color: COLOR.TEXT_DIM }),
    new PageBreak(),
  );
  
  // ===== TABLE OF CONTENTS =====
  sections.push(
    heading('Table of Contents', 1),
    spacer(200),
  );
  
  // Manual TOC (because docx field codes are fragile)
  sections.push(
    tocEntry('Executive Summary', 1, 'exec-summary'),
    spacer(100),
  );
  
  modules.forEach((mod, idx) => {
    sections.push(
      tocEntry(`${idx + 1}. ${mod.name}`, 1, `module-${idx}`),
    );
  });
  
  sections.push(
    spacer(100),
    tocEntry('Architecture', 1, 'architecture'),
    spacer(100),
    tocEntry('Appendices', 1, 'appendices'),
    new PageBreak(),
  );
  
  // ===== EXECUTIVE SUMMARY =====
  sections.push(
    withBookmark(heading('Executive Summary', 1), 'exec-summary'),
    para(exec_summary),
    new PageBreak(),
  );
  
  // ===== MODULES =====
  modules.forEach((mod, idx) => {
    sections.push(
      withBookmark(heading(`${idx + 1}. ${mod.name}`, 1), `module-${idx}`),
      spacer(200),
    );
    
    // Design Rationale
    sections.push(
      heading('Design Rationale', 2),
      para(mod.rationale),
    );
    
    // Component Inventory (if provided)
    if (mod.components) {
      sections.push(
        heading('Component Inventory', 2),
        simpleTable(
          ['Component', 'Type', 'Responsibility', 'Status'],
          mod.components.map(c => [c.name, c.type, c.responsibility, c.status]),
          [20, 15, 50, 15]
        ),
        spacer(200),
      );
    }
    
    // Acceptance Criteria (if provided)
    if (mod.acceptance_criteria) {
      sections.push(
        heading('Acceptance Criteria', 2),
      );
      
      mod.acceptance_criteria.forEach(criterion => {
        sections.push(
          para(criterion, { size: 20, color: COLOR.TEXT }),
          spacer(100),
        );
      });
    }
    
    // Wireframes (if provided)
    if (mod.wireframe_image) {
      sections.push(
        heading('Wireframes', 2),
        embedImage(mod.wireframe_image, 6, `${mod.name} Wireframe`),
        spacer(200),
      );
    }
    
    sections.push(new PageBreak());
  });
  
  // ===== ARCHITECTURE =====
  sections.push(
    withBookmark(heading('Architecture', 1), 'architecture'),
    para('System architecture diagram'),
    spacer(200),
  );
  
  if (architecture_image && fs.existsSync(architecture_image)) {
    sections.push(
      embedImage(architecture_image, 6.5, 'System Architecture'),
      spacer(200),
    );
  }
  
  sections.push(new PageBreak());
  
  // ===== APPENDICES =====
  sections.push(
    withBookmark(heading('Appendices', 1), 'appendices'),
    heading('Glossary', 2),
    bulletItem('API: Application Programming Interface'),
    bulletItem('UUID: Universally Unique Identifier'),
    bulletItem('JSON: JavaScript Object Notation'),
  );
  
  // ===== BUILD DOCUMENT =====
  const doc = new Document({
    sections: [{
      properties: pageSetup().page,
      children: sections,
      headers: createHeader(title),
      footers: createFooter(true),
    }],
    styles: defaultStyle.styles,
    numbering: numbering.config,
  });
  
  // ===== WRITE FILE =====
  const filename = `blueprint_${new Date().toISOString().split('T')[0]}.docx`;
  
  Packer.toFile(doc, filename)
    .then(() => {
      console.log(`✓ Blueprint generated: ${filename}`);
    })
    .catch(err => {
      console.error(`✗ Error: ${err}`);
      process.exit(1);
    });
}

// ============= EXPORT =============

module.exports = {
  generateBlueprint,
  heading,
  para,
  bold,
  bulletItem,
  simpleTable,
  embedImage,
  spacer,
  withBookmark,
  BOOKMARK_RANGES,
};
```

---

## Usage Pattern

### Complete Example Script

```javascript
// generate_blueprint.js

const {
  generateBlueprint,
  heading,
  para,
  bulletItem,
  simpleTable,
  embedImage,
} = require('./blueprint_builder');

const config = {
  title: 'Billing Module - Engineering Blueprint',
  
  exec_summary: `
This document specifies the Billing module architecture, including subscription lifecycle management, 
invoice generation, and refund processing. The module integrates with Stripe for payment processing 
and Redis for event-driven architecture.
  `,
  
  modules: [
    {
      name: 'Subscription Management',
      rationale: `Manages subscription lifecycle. Key decisions: subscriptions are immutable once created 
                  (audit trail), cancellations are immediate (no grace period).`,
      
      components: [
        { name: 'SubscriptionService', type: 'Class', responsibility: 'CRUD operations', status: 'New' },
        { name: 'POST /api/subscriptions', type: 'Endpoint', responsibility: 'Create subscription', status: 'New' },
      ],
      
      acceptance_criteria: [
        'POST /api/subscriptions with valid plan_id returns 201 Created',
        'Duplicate subscriptions (same user + plan) rejected with 409 Conflict',
        'subscription.created event emitted within 100ms',
      ],
      
      wireframe_image: './wireframes/01_subscriptions.png',
    },
  ],
  
  architecture_image: './wireframes/arch_billing.png',
};

generateBlueprint(config);
```

### Run

```bash
node generate_blueprint.js
```

---

## Critical Rules

1. **Never use `\n` for line breaks.** Use separate Paragraph objects instead.

2. **Never use unicode bullets.** Use the `bullet` property; docx renders it.

3. **Always set table widths** in two ways:
   - `width: { size: 100, type: WidthType.PERCENTAGE }`
   - Column widths in array (relative percentages)

4. **ShadingType must be CLEAR** (or omitted). Never use other shading types; they corrupt the DOCX.

5. **Images require all three altText fields:**
   ```javascript
   altText: {
     title: 'Description',
     description: 'Description',
     name: 'Description',
   }
   ```

6. **Never post-process .docx with Python zipfile.** This corrupts the file and Word won't open it. Assembly must be 100% complete in Node.js.

7. **Bookmarks must be unique** (use prefixes like `module-0`, `module-1`).

8. **Page numbers use `PageNumber()` constructor, not `new PageNumber()`.**

---

## Assembly Checklist

Before Phase 6, verify:

- [ ] npm install docx completed successfully
- [ ] All helper functions tested with sample content
- [ ] Cover page includes title and date
- [ ] TOC with clickable bookmarks (internal hyperlinks)
- [ ] Each module section has complete spec
- [ ] All wireframe images embedded with correct altText
- [ ] Architecture diagram embedded
- [ ] Header/footer with page numbers
- [ ] No \n characters (use separate Paragraphs)
- [ ] No unicode bullets (use bullet property)
- [ ] All tables have dual width setup
- [ ] All shading is type CLEAR
- [ ] Document generated as .docx file
- [ ] File opens successfully in Word and Google Docs

**If any fail, fix before Phase 6.**
