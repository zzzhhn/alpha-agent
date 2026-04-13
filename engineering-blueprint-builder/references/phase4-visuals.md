# Phase 4: Visuals — Wireframe and Diagram Generation Protocol

**Purpose:** Generate publication-quality wireframes and architecture diagrams using Python + Pillow. These are embedded in the DOCX.

---

## Setup

### Python Imports & Environment
```python
from PIL import Image, ImageDraw, ImageFont
import json
import os

# Define canvas at top of script
CANVAS_WIDTH = 1800
CANVAS_HEIGHT = 1000  # For module wireframes
ARCH_CANVAS_HEIGHT = 900  # For architecture diagrams

# Dark theme color palette
COLOR = {
    'BG': '#0F1117',           # Main background
    'CARD_BG': '#1A1D27',      # Card/panel background
    'TEXT': '#E5E7EB',         # Primary text
    'TEXT_DIM': '#9CA3AF',     # Secondary text
    'ACCENT': '#2E75B6',       # Primary accent (blue)
    'GREEN': '#22C55E',        # Success
    'RED': '#EF4444',          # Error
    'YELLOW': '#F59E0B',       # Warning
    'BORDER': '#30363D',       # Subtle border
}

# Font sizes (scaled for 1800px canvas)
FONT_SIZE = {
    'title': 48,
    'subtitle': 32,
    'body': 24,
    'caption': 18,
}

# Margins & spacing
MARGIN = 40
PADDING = 20
GUTTER = 30
```

### Font Loading (Fallback Pattern)
```python
def load_font(size):
    """Load system font; fallback to default if unavailable."""
    try:
        # Try to load Arial or Helvetica
        return ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", size)
    except:
        return ImageFont.load_default()
```

---

## Helper Functions

Copy these into your generation script.

### draw_card(draw, x, y, width, height, title=None, color=None)
```python
def draw_card(draw, x, y, width, height, title=None, color=None):
    """Draw a card/panel with border."""
    if color is None:
        color = COLOR['CARD_BG']
    
    # Background
    draw.rectangle([x, y, x+width, y+height], fill=color, outline=COLOR['BORDER'], width=2)
    
    # Title if provided
    if title:
        font = load_font(FONT_SIZE['subtitle'])
        draw.text((x + PADDING, y + PADDING), title, fill=COLOR['ACCENT'], font=font)
    
    return {'x': x, 'y': y + height}  # Return bottom edge for next element
```

### draw_sparkline(draw, x, y, width, height, data_points, color=None)
```python
def draw_sparkline(draw, x, y, width, height, data_points, color=None):
    """Draw a small line chart from normalized data points (0.0 to 1.0)."""
    if color is None:
        color = COLOR['ACCENT']
    
    if len(data_points) < 2:
        return
    
    # Normalize to canvas coordinates
    step = width / (len(data_points) - 1)
    points = []
    
    for i, val in enumerate(data_points):
        px = x + (i * step)
        py = y + height - (val * height)  # Invert Y
        points.append((px, py))
    
    # Draw line
    draw.line(points, fill=color, width=2)
    
    # Draw endpoints
    draw.ellipse([points[0][0]-4, points[0][1]-4, points[0][0]+4, points[0][1]+4], fill=color)
    draw.ellipse([points[-1][0]-4, points[-1][1]-4, points[-1][0]+4, points[-1][1]+4], fill=color)
```

### draw_bar(draw, x, y, width, height, value, max_val=100, color=None, label=None)
```python
def draw_bar(draw, x, y, width, height, value, max_val=100, color=None, label=None):
    """Draw a horizontal progress bar."""
    if color is None:
        color = COLOR['GREEN']
    
    # Background track
    draw.rectangle([x, y, x+width, y+height], fill=COLOR['BORDER'], outline=COLOR['BORDER'])
    
    # Fill
    fill_width = (value / max_val) * width
    draw.rectangle([x, y, x+fill_width, y+height], fill=color)
    
    # Label
    if label:
        font = load_font(FONT_SIZE['caption'])
        draw.text((x + PADDING, y - 25), label, fill=COLOR['TEXT_DIM'], font=font)
    
    return height + 25  # Height including label
```

### draw_status_dot(draw, x, y, status='active', size=16)
```python
def draw_status_dot(draw, x, y, status='active', size=16):
    """Draw colored status indicator."""
    color_map = {
        'active': COLOR['GREEN'],
        'inactive': COLOR['TEXT_DIM'],
        'error': COLOR['RED'],
        'warning': COLOR['YELLOW'],
    }
    color = color_map.get(status, COLOR['TEXT_DIM'])
    
    # Outer ring
    draw.ellipse([x-size, y-size, x+size, y+size], outline=color, width=2)
    
    # Inner filled dot
    inner = size - 4
    draw.ellipse([x-inner, y-inner, x+inner, y+inner], fill=color)
```

### draw_sidebar(draw, x, y, width, height, items)
```python
def draw_sidebar(draw, x, y, width, height, items):
    """Draw left sidebar with navigation items."""
    # Background
    draw.rectangle([x, y, x+width, y+height], fill=COLOR['CARD_BG'], outline=COLOR['BORDER'], width=1)
    
    # Title
    font_title = load_font(FONT_SIZE['subtitle'])
    draw.text((x+PADDING, y+PADDING), "Navigation", fill=COLOR['ACCENT'], font=font_title)
    
    # Items
    font_body = load_font(FONT_SIZE['body'])
    item_y = y + PADDING + 60
    
    for item in items:
        is_active = item.get('active', False)
        text_color = COLOR['ACCENT'] if is_active else COLOR['TEXT']
        bg_color = COLOR['ACCENT'] if is_active else None
        
        if bg_color:
            draw.rectangle([x+5, item_y, x+width-5, item_y+40], fill=bg_color)
        
        draw.text((x+PADDING+10, item_y+8), item['label'], fill=text_color, font=font_body)
        item_y += 50
```

---

## Wireframe Composition Rules

### Standard Layout (1800x1000)

```
[LEFT SIDEBAR 240px] | [MAIN CONTENT 1560px]

Sidebar: Navigation, user menu
Main: Header (60px) + Content area (940px)
```

### Every wireframe must include:

1. **Sidebar Navigation** (left 240px)
   - App logo / name at top
   - Active nav item highlighted with accent color
   - At least 3-4 navigation items

2. **Header** (top 60px of main area)
   - Module name (e.g., "Billing & Subscriptions")
   - Right-side actions (buttons)
   - Subtle border bottom

3. **Content Area** (remaining space)
   - Use cards for sections
   - Sample data (realistic, not lorem ipsum)
   - Status indicators where appropriate
   - Show both happy path and error states (if multiple wireframes)

### Example: Subscription List Wireframe

```python
def wireframe_subscriptions_list():
    img = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), COLOR['BG'])
    draw = ImageDraw.Draw(img)
    
    # Sidebar
    draw_sidebar(draw, MARGIN, MARGIN, 240, CANVAS_HEIGHT - 2*MARGIN, 
        items=[
            {'label': 'Dashboard', 'active': False},
            {'label': 'Subscriptions', 'active': True},
            {'label': 'Invoices', 'active': False},
            {'label': 'Settings', 'active': False},
        ])
    
    # Header
    header_x = MARGIN + 240 + GUTTER
    header_y = MARGIN
    header_w = CANVAS_WIDTH - header_x - MARGIN
    font_title = load_font(FONT_SIZE['title'])
    draw.text((header_x, header_y + 10), "Subscriptions", fill=COLOR['TEXT'], font=font_title)
    
    # New Subscription button (top right)
    button_x = CANVAS_WIDTH - MARGIN - 200
    button_y = header_y + 5
    draw.rectangle([button_x, button_y, button_x+180, button_y+40], 
                   fill=COLOR['ACCENT'], outline=COLOR['ACCENT'])
    font_body = load_font(FONT_SIZE['body'])
    draw.text((button_x+20, button_y+8), "+ New Plan", fill='#FFFFFF', font=font_body)
    
    # Table header
    table_y = header_y + 70
    cols = [
        ('Plan', header_x + 20),
        ('Status', header_x + 400),
        ('Next Charge', header_x + 700),
        ('Amount', header_x + 1000),
    ]
    
    for col_name, col_x in cols:
        draw.text((col_x, table_y), col_name, fill=COLOR['TEXT_DIM'], font=font_body)
    
    # Sample rows
    table_y += 50
    rows = [
        ('Pro Annual', 'active', '2026-05-12', '$365.00'),
        ('API Access', 'active', '2026-04-20', '$99.00'),
        ('Starter', 'cancelled', '—', '—'),
    ]
    
    for plan, status, next_charge, amount in rows:
        # Draw status dot
        status_color = COLOR['GREEN'] if status == 'active' else COLOR['TEXT_DIM']
        draw_status_dot(draw, cols[1][1]-20, table_y+12, status=status)
        
        # Row data
        draw.text((cols[0][1], table_y), plan, fill=COLOR['TEXT'], font=font_body)
        draw.text((cols[1][1], table_y), status.title(), fill=COLOR['TEXT'], font=font_body)
        draw.text((cols[2][1], table_y), next_charge, fill=COLOR['TEXT'], font=font_body)
        draw.text((cols[3][1], table_y), amount, fill=COLOR['TEXT'], font=font_body)
        
        table_y += 60
    
    img.save('01_subscriptions_list.png')
    return '01_subscriptions_list.png'
```

---

## Architecture Diagram Composition

### Standard Layout (1800x900)

**Structure:**
```
Top: Service/Module boxes with data flows
Middle: Cross-cutting layers (Security, LLM, Monitoring)
Bottom: External integrations (Stripe, Slack, etc.)
Feedback loops: Dashed arrows
```

### Example: Billing Architecture Diagram

```python
def diagram_billing_architecture():
    img = Image.new('RGB', (CANVAS_WIDTH, ARCH_CANVAS_HEIGHT), COLOR['BG'])
    draw = ImageDraw.Draw(img)
    
    # Title
    font_title = load_font(FONT_SIZE['title'])
    draw.text((MARGIN, MARGIN), "Billing System Architecture", fill=COLOR['TEXT'], font=font_title)
    
    # Top tier: Core services
    services = [
        {'name': 'Subscription\nService', 'x': 100, 'y': 150},
        {'name': 'Invoice\nCalculator', 'x': 450, 'y': 150},
        {'name': 'Refund\nProcessor', 'x': 800, 'y': 150},
    ]
    
    for service in services:
        draw.rectangle([service['x'], service['y'], service['x']+280, service['y']+120],
                      fill=COLOR['CARD_BG'], outline=COLOR['ACCENT'], width=2)
        draw.text((service['x']+40, service['y']+40), service['name'], 
                 fill=COLOR['TEXT'], font=load_font(FONT_SIZE['body']))
    
    # Data flows between services (solid arrows)
    for i in range(len(services)-1):
        x1 = services[i]['x'] + 280
        y1 = services[i]['y'] + 60
        x2 = services[i+1]['x']
        y2 = services[i+1]['y'] + 60
        
        draw.line([(x1, y1), (x2, y1), (x2, y2)], fill=COLOR['ACCENT'], width=2)
        # Arrowhead (simplified triangle)
        arrow_size = 10
        draw.polygon([(x2, y2), (x2-arrow_size, y2-arrow_size), (x2-arrow_size, y2+arrow_size)],
                    fill=COLOR['ACCENT'])
    
    # Middle tier: Cross-cutting concerns
    middleware_y = 350
    middleware_items = [
        {'name': 'Auth & ACL', 'x': 100, 'color': COLOR['RED']},
        {'name': 'Error Handling', 'x': 500, 'color': COLOR['YELLOW']},
        {'name': 'Logging', 'x': 900, 'color': COLOR['ACCENT']},
    ]
    
    for item in middleware_items:
        draw.rectangle([item['x'], middleware_y, item['x']+280, middleware_y+80],
                      fill=item['color'], outline=item['color'])
        draw.text((item['x']+20, middleware_y+25), item['name'], 
                 fill='#FFFFFF', font=load_font(FONT_SIZE['body']))
    
    # Bottom tier: External integrations
    external_y = 500
    externals = [
        {'name': 'Stripe API', 'x': 100},
        {'name': 'Event Bus\n(Redis)', 'x': 450},
        {'name': 'Database\n(PostgreSQL)', 'x': 800},
    ]
    
    for ext in externals:
        draw.rectangle([ext['x'], external_y, ext['x']+280, external_y+100],
                      fill=COLOR['CARD_BG'], outline=COLOR['GREEN'], width=2)
        draw.text((ext['x']+20, external_y+35), ext['name'], 
                 fill=COLOR['GREEN'], font=load_font(FONT_SIZE['body']))
    
    # Feedback loops (dashed arrows back to top)
    for i, ext in enumerate(externals):
        x1 = ext['x'] + 140
        y1 = external_y
        x2 = services[i]['x'] + 140
        y2 = services[i]['y'] + 120
        
        # Draw dashed line
        draw.line([(x1, y1-20), (x1, y1-100), (x2, y2+60)], 
                 fill=COLOR['TEXT_DIM'], width=2)
        # Arrowhead
        draw.polygon([(x2, y2+60), (x2-8, y2+50), (x2+8, y2+50)],
                    fill=COLOR['TEXT_DIM'])
    
    img.save('arch_billing.png')
    return 'arch_billing.png'
```

---

## File Naming Convention

Organize wireframes by module number:

```
00_overview.png                 # System overview (architecture + flow)
01_module_auth.png              # Auth module screens
01_module_auth_error.png        # Auth error state
02_module_billing.png           # Billing module screens
02_module_billing_refund.png    # Refund flow
03_module_reports.png           # Reports module
arch_system.png                 # Overall architecture diagram
arch_data_flow.png              # Data flow diagram
```

---

## Visuals Checklist

Before Phase 5 (Assembly), verify:

- [ ] All wireframes are 1800x1000 or 1800x900 (correct dimensions)
- [ ] Every wireframe includes sidebar navigation (at least 3-4 items)
- [ ] Every wireframe includes header with module name
- [ ] Sample data is realistic (not "Lorem ipsum" or placeholder)
- [ ] Color palette uses defined COLOR dict (dark theme)
- [ ] All text is legible at display size
- [ ] Architecture diagrams show module boxes, data flows, and feedback loops
- [ ] File naming follows convention (00_, 01_, etc., or arch_)
- [ ] All PNG files are saved to correct directory
- [ ] Image dimensions verified (use `identify` or PIL to check)

**If any are incomplete, regenerate before Phase 5.**
