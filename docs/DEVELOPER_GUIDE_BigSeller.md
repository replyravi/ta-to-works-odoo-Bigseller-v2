# RSS – BigSeller Import Addon: Developer Guide

> **Author:** RSS  
> **Addon name:** `rss_import_bigseller_order`  
> **Odoo version:** 16.0  
> **Purpose:** Import bulk sale orders from a BigSeller `.xls` export file into Odoo sale orders automatically.  
> **Audience:** Junior developers with basic Python knowledge but no prior Odoo experience.

---

## Table of Contents

1. [What Does This Addon Do?](#1-what-does-this-addon-do)
2. [How Odoo Addons Work (Concept)](#2-how-odoo-addons-work-concept)
3. [Folder Structure](#3-folder-structure)
4. [File-by-File Explanation](#4-file-by-file-explanation)
   - [4.1 `__manifest__.py` — Identity Card](#41-__manifestpy--identity-card)
   - [4.2 `__init__.py` — Python Package Marker](#42-__initpy--python-package-marker)
   - [4.3 Security Files](#43-security-files)
   - [4.4 `views/bigseller_sale.xml` — The Popup UI](#44-viewsbigseller_salexml--the-popup-ui)
   - [4.5 `models/bigseller_sale.py` — The Brain](#45-modelsbigseller_salepy--the-brain)
5. [Full Import Flow (Step by Step)](#5-full-import-flow-step-by-step)
6. [Key Odoo Concepts Explained Simply](#6-key-odoo-concepts-explained-simply)
7. [BigSeller XLS Column Map](#7-bigseller-xls-column-map)
8. [How to Create a Similar Addon for Another Marketplace](#8-how-to-create-a-similar-addon-for-another-marketplace)
9. [How to Install an Addon](#9-how-to-install-an-addon)
10. [Common Errors and Fixes](#10-common-errors-and-fixes)

---

## 1. What Does This Addon Do?

BigSeller is a multi-channel e-commerce management platform that aggregates orders from Shopee, Lazada, and other marketplaces. Sellers export orders as `.xls` files from BigSeller.

This addon adds a new menu item in Odoo:

```
Sales → Orders → Import BigSeller Sale Order
```

When clicked, a popup appears where the user:
1. Selects a **Sale Order Type** (a config profile containing sales team, warehouse, salesperson, etc.)
2. Uploads the `.xls` file exported from BigSeller
3. Clicks **Import**

Odoo then reads every row in the file and creates `sale.order` records automatically — one Odoo sale order per unique BigSeller order number.

---

## 2. How Odoo Addons Work (Concept)

Think of Odoo like a **smartphone operating system**:
- The core Odoo = the OS
- Each addon = an app you install

An addon is just a **Python package** (a folder with Python files) that Odoo loads at startup. It can:
- Add new database tables (called **models**)
- Add new fields to existing tables
- Add new menu items and screens (called **views**)
- Add business logic (Python methods)

Odoo follows the **MVC pattern**:

| Layer | Odoo term | File type | What it does |
|---|---|---|---|
| Model | `models/` | `.py` | Database structure + business logic |
| View | `views/` | `.xml` | What the user sees on screen |
| Controller | Odoo's HTTP layer | (built-in) | Handles browser requests |

---

## 3. Folder Structure

```
rss_import_bigseller_order/
│
├── __manifest__.py              ← Addon identity (name, version, dependencies)
├── __init__.py                  ← Marks this folder as a Python package
│
├── models/
│   ├── __init__.py              ← Marks sub-folder as a Python package
│   └── bigseller_sale.py        ← ALL business logic lives here
│
├── security/
│   ├── ir.model.access.csv      ← Database-level access permissions
│   └── access_record_rule.xml   ← Creates the security group for menu access
│
└── views/
    └── bigseller_sale.xml       ← Popup window UI + menu item definition
```

---

## 4. File-by-File Explanation

### 4.1 `__manifest__.py` — Identity Card

```python
{
    'name': 'Import BigSeller Order from XLS File',
    'version': '16.0.1.0.0',
    'category': 'Sales',
    'author': 'RSS',
    'depends': [
        'base',             # Core Odoo (always required)
        'sale',             # Sale orders module
        'sale_order_type',  # OCA addon for Order Types
        'sale_order_type_ext',  # Our own helper addon (adds extra fields)
    ],
    'data': [
        'security/ir.model.access.csv',   # Load security first
        'security/access_record_rule.xml',
        'views/bigseller_sale.xml',        # Then load the UI
    ],
    'installable': True,
}
```

**Rules to remember:**
- `depends` = modules that must be installed **before** this one. If you forget a dependency, Odoo will throw an error at installation.
- `data` = files Odoo reads to set up the database records. **Order matters** — security files must come before views.
- `version` format = `{odoo_version}.{major}.{minor}.{patch}` → e.g. `16.0.1.0.0`

---

### 4.2 `__init__.py` — Python Package Marker

The root `__init__.py`:
```python
from . import models
```

The `models/__init__.py`:
```python
from . import bigseller_sale
```

These files tell Python: "treat this folder as a package and load these files."  
Without them, Python will not find the code even if the files exist.

---

### 4.3 Security Files

#### `security/ir.model.access.csv`

```
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_gen_bigseller_sale,gen.bigseller.sale,model_gen_bigseller_sale,,1,1,1,1
```

This CSV controls **who can interact with the wizard** at the database level.

| Column | Meaning |
|---|---|
| `id` | Unique XML id for this rule |
| `name` | Human-readable name |
| `model_id:id` | Which model this rule applies to (auto-generated as `model_` + model name with dots replaced by underscores) |
| `group_id:id` | Restrict to a group (blank = all users) |
| `perm_read/write/create/unlink` | `1` = allowed, `0` = denied |

#### `security/access_record_rule.xml`

```xml
<record id="group_import_bigseller_order" model="res.groups">
    <field name="name">Import BigSeller Order</field>
    <field name="implied_ids" eval="[(4,ref('base.group_user'))]"/>
</record>
```

This creates a **security group** called "Import BigSeller Order".

- Think of it as a **door lock**. The admin gives the key (assigns users to the group) via Settings → Users & Companies → Groups.
- `implied_ids` with `(4, ref('base.group_user'))` means: "anyone in this group automatically gets the basic internal user rights too."
- The `(4, id)` syntax is Odoo's special Many2many write command — `4` means "add this existing record to the relation."

---

### 4.4 `views/bigseller_sale.xml` — The Popup UI

This XML file has three parts:

#### Part 1 — Define the form layout

```xml
<record id="gen_bigseller_sale_wizard_view" model="ir.ui.view">
    <field name="model">gen.bigseller.sale</field>
    <field name="arch" type="xml">
        <form string="Import BigSeller Order">
            <group>
                <field name="order_type_id" required="1"/>
                <field name="file" filename="file_name"/>
            </group>
            <footer>
                <button name="import_sale" string="Import" type="object" class="oe_highlight"/>
            </footer>
        </form>
    </field>
</record>
```

- `model="ir.ui.view"` — we are creating a View record in the database.
- `<form>` — a form layout (other options: `<list>`, `<kanban>`, `<search>`).
- `<field name="order_type_id" required="1"/>` — shows a dropdown linked to `sale.order.type`.
- `<field name="file"/>` — shows a file upload button (because field type is `Binary`).
- `<button name="import_sale" type="object"/>` — calls the Python method `import_sale()` on click.

#### Part 2 — Define the window action

```xml
<record id="gen_bigseller_sale_import_wizard" model="ir.actions.act_window">
    <field name="res_model">gen.bigseller.sale</field>
    <field name="view_mode">form</field>
    <field name="target">new</field>   <!-- "new" = opens as popup dialog -->
</record>
```

An **act_window** is a record that says: "when triggered, open this model's view."  
`target="new"` opens it as a popup. `target="current"` would replace the whole screen.

#### Part 3 — Create the menu item

```xml
<menuitem
    action="gen_bigseller_sale_import_wizard"
    sequence="62"
    id="gen_bigseller_sale_wizard_import"
    parent="sale.sale_order_menu"
    groups="rss_import_bigseller_order.group_import_bigseller_order"
/>
```

- `action` — links to the act_window above. Clicking the menu runs that action.
- `parent="sale.sale_order_menu"` — places it under **Sales → Orders** (this XML id belongs to the `sale` module).
- `sequence="62"` — controls the order in the dropdown (lower number = higher up).
- `groups` — only users in this group can see the menu item.

---

### 4.5 `models/bigseller_sale.py` — The Brain

This is the most important file. It contains all business logic.

#### Imports

```python
import xlrd               # Reads .xls Excel files
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError
from odoo import models, fields, api, _
```

- `xlrd` — third-party Python library for reading old-format `.xls` files.
- `ValidationError` — shows a red popup error to the user.
- `UserError` — similar, used for configuration/user mistakes.
- `_()` — Odoo's translation function. Wrapping text in `_('...')` allows it to be translated to other languages.

#### Column Constants

```python
COL_ORDER_NO      = 0    # Column A in the XLS
COL_ORDER_STATUS  = 7    # Column H
COL_BUYER         = 13   # Column N
COL_SKU           = 24   # Column Y (product barcode)
COL_QUANTITY      = 31
COL_PRICE         = 32   # Selling price (after discount)
COL_ORIG_PRICE    = 34   # Original price (before discount)
COL_SHIP_OPTION   = 53   # Carrier name
COL_TRACKING      = 55   # Tracking number
COL_ORDER_TIME    = 69   # Order placed date/time
COL_SHIPPED_TIME  = 75   # Shipped date/time
COL_CANCEL_REASON = 79
```

XLS columns are zero-indexed (column A = 0). By naming them as constants, the code is self-documenting and easy to update if BigSeller changes the file format.

#### The Wizard Class

```python
class gen_bigseller_sale(models.TransientModel):
    _name = "gen.bigseller.sale"
```

**`TransientModel` vs `Model`:**

| Type | Saved to DB? | Use case |
|---|---|---|
| `models.Model` | Yes, permanently | Products, customers, sale orders |
| `models.TransientModel` | Yes, but auto-deleted after ~24h | Wizards, import dialogs, one-time actions |

The `_name` is the technical name used everywhere in Odoo to reference this model. Dots (`.`) are used instead of underscores (`_`) by convention for Odoo model names.

#### `_cell()` Helper

```python
def _cell(self, row, idx):
    val = row[idx].value
    if isinstance(val, float):
        return str(int(val)) if val == int(val) else str(val)
    return str(val).strip() if val else ''
```

**Why this is needed:**  
Excel stores numbers as `float`. A barcode like `733905810572` comes out of xlrd as `733905810572.0`. If we search Odoo for barcode `"733905810572.0"` we get no result. This helper strips the `.0` to give `"733905810572"`.

#### `_parse_date()` Helper

```python
def _parse_date(self, raw):
    dt = datetime.strptime(raw, "%d %b %Y %H:%M") - timedelta(hours=7)
    return dt.strftime("%Y-%m-%d %H:%M:%S")
```

- BigSeller date format: `"18 Feb 2026 13:18"` (Thai time, UTC+7)
- Odoo stores all dates in **UTC** (no timezone)
- So we subtract 7 hours before saving
- `strptime` = string → datetime object. `strftime` = datetime object → string.

#### Finder Methods Pattern

Every `_find_*` method follows the same pattern:

```python
def _find_sale_team(self, name):
    obj = self.env['crm.team']            # Get the model (like a DB table)
    rec = obj.search([('name', '=', name)], limit=1)  # SELECT WHERE name='X' LIMIT 1
    if rec:
        return rec                         # Found — return it
    raise ValidationError(...)            # Not found — show error
```

`self.env['model.name']` is how Python code in Odoo accesses any database table.  
`search([domain], limit=1)` is like SQL `SELECT * FROM table WHERE ... LIMIT 1`.

**Some finders auto-create instead of raising errors:**

```python
def _find_cancel_reason(self, name):
    rec = obj.search([('name', '=', name)], limit=1)
    return rec if rec else obj.create({'name': name})  # Auto-create if missing
```

The rule is: **auto-create** things that are safe to generate on-the-fly (buyer names, carrier names, cancel reasons). **Raise errors** for things that must be pre-configured by an admin (sales teams, fiscal positions, warehouses, users, products).

#### `_find_product()` — The Most Important Finder

```python
def _find_product(self, value):
    obj = self.env['product.product']
    if self.import_prod_option == 'barcode':
        clean = value.replace('.', '', 1)
        if clean.isdigit():
            rec = obj.search([('barcode', '=', int(float(value)))], limit=1)
        else:
            rec = obj.search([('barcode', '=', value)], limit=1)
    elif self.import_prod_option == 'code':
        rec = obj.search([('default_code', '=', value)], limit=1)
    else:
        rec = obj.search([('name', '=', value)], limit=1)
    if not rec:
        raise ValidationError(_('"%s" product is not found.') % value)
    return rec[0]
```

The user can choose to match products by barcode, internal reference (SKU), or name.  
**Important:** Products must exist in Odoo before importing. If a product is not found, the import stops with a clear error telling you which barcode is missing.

#### `_make_order_line()` — Create One Product Line on an Order

```python
def _make_order_line(self, values, sale_id, route_id):
    product = self._find_product(values['product'])
    line_vals = {
        'order_id':        sale_id.id,      # Link line to its parent order
        'product_id':      product.id,
        'product_uom_qty': float(values.get('quantity') or 1.0),
        'price_unit':      float(values.get('price') or 0.0),
        'discount':        float(values.get('discount') or 0.0),
        'route_id':        route_id.id if route_id else False,
    }
    self.env['sale.order.line'].create(line_vals)
```

`sale.order.line` is Odoo's model for individual product rows on a sale order.  
`.id` — in Odoo, every record has an `id` field (the database primary key). When linking records (foreign keys), you always pass the `.id`.

#### `_make_sale()` — Create or Update the Sale Order

```python
def _make_sale(self, values, bigseller_partner, upload_sequence):
    order_name = values.get('order', '').strip()

    # Check if this order was already imported
    existing = sale_obj.search([('name', '=', order_name)], limit=1)
    if existing:
        if is_cancel and existing.state != 'cancel':
            existing.state = 'cancel'
        if str(existing.upload_sequence) == str(upload_sequence):
            self._make_order_line(values, existing, route_id)
        return existing

    # Create new sale order
    sale_id = sale_obj.create({
        'name':               order_name,
        'partner_id':         bigseller_partner.id,
        'team_id':            team_id.id,
        'warehouse_id':       warehouse_id.id,
        'date_order':         order_date,
        'tracking_reference': values.get('tracking_reference'),
        'state':              'cancel' if is_cancel else 'draft',
        ...
    })
    self._make_order_line(values, sale_id, route_id)
    return sale_id
```

**Multi-line order handling** — this is the key design:

```
BigSeller XLS Row 1: Order A-001 | Product X | Qty 2
BigSeller XLS Row 2: Order A-001 | Product Y | Qty 1   ← same order, different product
BigSeller XLS Row 3: Order A-002 | Product Z | Qty 3

Result in Odoo:
  Sale Order A-001 ──► Line 1: Product X, Qty 2
                  ──► Line 2: Product Y, Qty 1
  Sale Order A-002 ──► Line 1: Product Z, Qty 3
```

The `upload_sequence` (a Unix timestamp) is used to distinguish "same import session" from "different import session". If you import the same file twice, it will not add duplicate lines.

#### `import_sale()` — Main Method Called by the Import Button

```python
def import_sale(self):
    # Step 1: Validate configuration
    if not self.order_type_id:
        raise UserError("Please select a Sale Order Type.")

    # Step 2: Check all required fields are set on the Order Type
    required = {'sale_team_id': 'Sales Team', 'warehouse_id': 'Warehouse', ...}
    missing = [label for field, label in required.items() if not order_type[field]]
    if missing:
        raise UserError(...)

    # Step 3: Find or create BIGSELLER master partner
    bigseller_partner = self.env['res.partner'].search(
        [('name', '=', 'BIGSELLER'), ('is_company', '=', True)], limit=1)

    # Step 4: Decode uploaded file and open with xlrd
    fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xls")
    fp.write(binascii.a2b_base64(self.file))   # base64 → binary
    wb = xlrd.open_workbook(fp.name)
    ws = wb.sheet_by_index(0)

    # Step 5: Loop through every data row (skip row 0 = header)
    for row_no in range(1, ws.nrows):
        row    = ws.row(row_no)
        status = self._cell(row, COL_ORDER_STATUS)

        if status not in ('Shipped', 'Canceled', 'Completed'):
            continue  # Skip rows with other statuses (e.g., Pending, Ready to Ship)

        # Extract data from columns
        # Calculate discount
        # Build values dict
        # Call _make_sale()

    # Step 6: Auto-confirm if user chose that option
    if self.stage == 'confirm':
        for so in sale_ids:
            so.action_confirm()

    # Step 7: Return action to open list of created orders
    return {
        'type':      'ir.actions.act_window',
        'res_model': 'sale.order',
        'domain':    [('id', 'in', return_ids)],
        'view_mode': 'list,form',
    }
```

**Why base64?** Browsers cannot send raw binary files over HTTP. The file is encoded as a base64 text string for transmission. `binascii.a2b_base64(self.file)` decodes it back to binary so `xlrd` can read it as a real Excel file.

**The return value** is an Odoo "action" dictionary. When the method returns this, Odoo's frontend automatically navigates to the sale orders list filtered to only show the orders just created.

#### Discount Calculation

```python
price      = float(price_raw)       # Selling price (col 32) — what customer paid
orig_price = float(orig_raw)        # Original price (col 34) — before discount
discount   = round((orig_price - price) / orig_price * 100, 2) if orig_price > 0 else 0.0
```

Example: Original price = 1200 THB, Selling price = 900 THB  
`discount = (1200 - 900) / 1200 * 100 = 25.0%`

---

## 5. Full Import Flow (Step by Step)

```
┌─────────────────────────────────────────────────────────────────────┐
│  User: Sales → Orders → Import BigSeller Sale Order                 │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ Odoo opens popup (TransientModel wizard)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  User fills in:                                                      │
│    • Sale Order Type = "MP: BigSeller"                               │
│    • Upload file = "BIGSELLER Order.xls"                             │
│    • Click "Import" button                                           │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ Calls import_sale() method in Python
                                    ▼
             ┌──────────────────────────────────────┐
             │ [1] Validate Order Type is selected   │
             │ [2] Check all required config fields  │
             │ [3] Find/create BIGSELLER partner     │
             │ [4] Decode base64 → read XLS with xlrd│
             └─────────────────┬────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Loop: each row     │
                    │  in XLS (row 1+)    │
                    └──────────┬──────────┘
                               │
               ┌───────────────▼───────────────┐
               │ Status in Shipped/             │
               │ Canceled/Completed?            │
               └──────┬──────────────┬──────────┘
                      │ YES          │ NO
                      │              └──► skip row (continue)
                      ▼
         ┌────────────────────────────┐
         │ Extract all column values  │
         │ Parse dates (UTC-7h)       │
         │ Calculate discount %       │
         └─────────────┬──────────────┘
                       │
                       ▼
         ┌────────────────────────────┐
         │ _make_sale()               │
         │                            │
         │  Does order already exist? │
         │   YES → add line only      │
         │   NO  → create order + line│
         └─────────────┬──────────────┘
                       │
                       ▼ (after all rows processed)
         ┌────────────────────────────┐
         │ stage == 'confirm'?        │
         │  YES → action_confirm()    │
         │  NO  → leave as Draft      │
         └─────────────┬──────────────┘
                       │
                       ▼
         ┌────────────────────────────┐
         │ Return act_window action   │
         │ → Opens list of created    │
         │   sale orders in Odoo UI   │
         └────────────────────────────┘
```

---

## 6. Key Odoo Concepts Explained Simply

| Concept | Simple explanation |
|---|---|
| `self.env['model.name']` | Access any database table, like `db.get_table('...')` |
| `.search([domain])` | Run a SELECT query. Domain = list of `(field, operator, value)` tuples |
| `.create({vals})` | INSERT a new row into the database |
| `.write({vals})` | UPDATE an existing row |
| `record.id` | The database primary key (integer) of a record |
| `Many2one` field | Foreign key — stores the `id` of a related record |
| `Binary` field | Stores file content as base64-encoded bytes |
| `Selection` field | A dropdown with fixed options (like an ENUM) |
| `TransientModel` | Temporary wizard — auto-deleted from DB after ~24 hours |
| `ValidationError` | Shows a red error popup to the user |
| `UserError` | Same as ValidationError — used for config/user mistakes |
| `_()` | Translation wrapper — makes text translatable to other languages |
| `noupdate="0"` in XML | Record CAN be overwritten if you upgrade the addon |
| `noupdate="1"` in XML | Record is created once, never overwritten on upgrade |
| `(4, id)` in Many2many | Odoo command: "add this existing record to the relation" |
| `(0, 0, vals)` in One2many | Odoo command: "create a new related record with these values" |

---

## 7. BigSeller XLS Column Map

| Constant | Col # | Column Header | Example Value |
|---|---|---|---|
| `COL_ORDER_NO` | 0 | Order No | `2503210166BKLB` |
| `COL_ORDER_STATUS` | 7 | Order Status | `Shipped` / `Canceled` / `Completed` |
| `COL_BUYER` | 13 | Buyer Username | `buyer_name_123` |
| `COL_SKU` | 24 | SKU | `733905810572` |
| `COL_QUANTITY` | 31 | Quantity | `2` |
| `COL_PRICE` | 32 | Selling Price | `900` |
| `COL_ORIG_PRICE` | 34 | Original Price | `1200` |
| `COL_SHIP_OPTION` | 53 | Shipping Option | `Shopee Express` |
| `COL_TRACKING` | 55 | Tracking Number | `TH123456789` |
| `COL_ORDER_TIME` | 69 | Order Time | `18 Feb 2026 13:18` |
| `COL_SHIPPED_TIME` | 75 | Shipped Time | `20 Feb 2026 09:00` |
| `COL_CANCEL_REASON` | 79 | Cancel Reason | `Out of stock` |

> **Tip:** If BigSeller changes their export format, open the XLS, count columns from left (starting at 0), and update these constants. Nothing else needs to change.

---

## 8. How to Create a Similar Addon for Another Marketplace

Follow these steps to build, for example, a TikTok Shop import addon:

### Step 1 — Export a sample file from the new marketplace

Get a real export file and open it in Excel. Note the column positions for: order number, status, buyer, product SKU, quantity, price, date, tracking number.

### Step 2 — Copy and rename the addon folder

```bash
cp -r rss_import_bigseller_order rss_import_tiktok_order
```

### Step 3 — Update `__manifest__.py`

```python
'name': 'Import TikTok Shop Order from XLS File',
'author': 'RSS',
# depends stays the same
```

### Step 4 — Update column constants

In `models/bigseller_sale.py` → rename to `tiktok_sale.py` and update:
```python
COL_ORDER_NO     = 0   # wherever order number is in TikTok export
COL_ORDER_STATUS = 5   # wherever status is
COL_SKU          = 18  # wherever SKU/barcode is
# ... etc
```

### Step 5 — Update `PROCESS_STATUSES`

TikTok may use different status names like `"Delivered"` instead of `"Shipped"`:
```python
PROCESS_STATUSES = ('Delivered', 'Cancelled', 'Completed')
```

### Step 6 — Update `_parse_date()` if the date format is different

```python
# TikTok format might be: "2026-02-18 13:18:00"
dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S") - timedelta(hours=7)
```

### Step 7 — Update model name in all files

Replace every occurrence of `gen.bigseller.sale` → `gen.tiktok.sale`  
Replace every occurrence of `gen_bigseller_sale` → `gen_tiktok_sale`  
Replace every occurrence of `bigseller` → `tiktok` (in group names, menu ids, etc.)

### Step 8 — Update `views/` XML

- Change form title
- Change menu item name and sequence number (use a new unique number)

### Step 9 — Install

```bash
cd /path/to/odoo-16
source venv/bin/activate
python odoo-source/odoo-bin -i rss_import_tiktok_order -d tato --stop-after-init
```

---

## 9. How to Install an Addon

### Prerequisites
- Odoo is stopped (or you're doing a live update)
- The addon folder is inside the `custom-addons` directory
- The `custom-addons` path is in `odoo.conf` under `addons_path`

### Install a new addon
```bash
cd /Users/ravishankersingh/Downloads/TA-TO-Works-Mar-26/odoo-16
source venv/bin/activate
python odoo-source/odoo-bin -i rss_import_bigseller_order -d tato --stop-after-init
```

### Update an existing addon (after code changes)
```bash
python odoo-source/odoo-bin -u rss_import_bigseller_order -d tato --stop-after-init
```

- `-i` = install (first time)
- `-u` = update (after code changes)
- `-d tato` = the database name
- `--stop-after-init` = stop Odoo after finishing (so you can restart it normally)

### Start Odoo normally
```bash
bash start-odoo.sh
```

### Verify the addon is installed
Go to: **Settings → Apps → Search "BigSeller"** — it should show as Installed.

---

## 10. Common Errors and Fixes

### `"<barcode>" product is not found`
**Cause:** The product with that barcode does not exist in Odoo.  
**Fix:** Create the product in Odoo first (Inventory → Products) and set its barcode, then import again. Or run the setup script that creates products from the XLS file.

### `"<Name>" Sales Team is not available`
**Cause:** The Sale Order Type you selected has a Sales Team name, but that team doesn't exist in this Odoo database.  
**Fix:** Go to Sales → Configuration → Sales Teams and create the team, or fix the Sale Order Type.

### `Incompatible companies on records`
**Cause:** Records like the warehouse or fiscal position belong to a different company than the sale order being created.  
**Fix:** Make sure all master data (warehouse, fiscal position, sales team, pricelist) belongs to the same company. The company name must match what is in the Sale Order Type.

### `Invalid field 'X' on model 'Y'`
**Cause:** The addon that adds field `X` (likely `sale_order_type_ext`) is not installed or not updated.  
**Fix:** Run `-u sale_order_type_ext` then `-u rss_import_bigseller_order`.

### `ParseError` on XML file during install
**Cause:** A typo in your XML file — wrong tag, missing closing tag, or wrong `inherit_id` reference.  
**Fix:** Check the Odoo log output for the exact line number. Open the XML file and fix the syntax.

### `KeyError` or `AttributeError` during import
**Cause:** Code is trying to access a field that doesn't exist on the model.  
**Fix:** Check if `sale_order_type_ext` is installed (it adds extra fields to `sale.order` and `sale.order.type`).

---

## Quick Reference: Odoo Many2many Write Commands

When setting relational fields in Python code, Odoo uses special tuple commands:

| Command | Meaning |
|---|---|
| `(0, 0, {vals})` | Create a new related record with these values |
| `(1, id, {vals})` | Update existing related record with id |
| `(2, id)` | Delete related record with id |
| `(3, id)` | Remove the link (but don't delete the record) |
| `(4, id)` | Add existing record to the relation |
| `(5,)` | Remove all links |
| `(6, 0, [ids])` | Replace all links with this new list of ids |

---

*Document prepared by RSS for TA-TO project. Last updated: March 2026.*
