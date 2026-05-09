# VCT BigSeller Integration — Full Developer Guide

> **Audience:** Fresher developers joining the TA-TO team who need to understand, install, test, or extend this Odoo module.  
> **Last updated:** May 2026  
> **Module name:** `vct_bigseller`  
> **GitHub repo:** https://github.com/replyravi/ta-to-works-odoo-Bigseller-v2

---

## Table of Contents

1. [What This Module Does](#1-what-this-module-does)
2. [Environment Overview](#2-environment-overview)
3. [Prerequisites — Local Development](#3-prerequisites--local-development)
4. [Getting the Code](#4-getting-the-code)
5. [Module File Structure](#5-module-file-structure)
6. [Architecture: How Everything Connects](#6-architecture-how-everything-connects)
7. [Installing on Local Odoo 16](#7-installing-on-local-odoo-16)
8. [Installing on Staging / Production (Odoo 18e)](#8-installing-on-staging--production-odoo-18e)
9. [Required Post-Install Configuration](#9-required-post-install-configuration)
10. [How to Use the Module (Functional Walkthrough)](#10-how-to-use-the-module-functional-walkthrough)
11. [How Synchronisation Works (Technical Deep Dive)](#11-how-synchronisation-works-technical-deep-dive)
12. [Tampermonkey Auto-Sync Script](#12-tampermonkey-auto-sync-script)
13. [Key Business Rules You Must Know](#13-key-business-rules-you-must-know)
14. [Shop ID → Order Type Mapping](#14-shop-id--order-type-mapping)
15. [Making Changes — Step-by-Step](#15-making-changes--step-by-step)
16. [Odoo 16 vs Odoo 18 Dual Compatibility](#16-odoo-16-vs-odoo-18-dual-compatibility)
17. [Git Workflow — How to Push Changes](#17-git-workflow--how-to-push-changes)
18. [Troubleshooting Common Errors](#18-troubleshooting-common-errors)
19. [Database SQL Cheatsheet](#19-database-sql-cheatsheet)
20. [Glossary](#20-glossary)

---

## 1. What This Module Does

`vct_bigseller` connects **BigSeller** (a multi-platform order management system used by TA-TO) with **Odoo** (the ERP system). It handles:

| Feature | Description |
|---|---|
| **XLS Import** | Import orders from a BigSeller Excel export file into Odoo as Sale Orders |
| **JSON Import (Manual)** | Paste a BigSeller API JSON response into a wizard to create/update Sale Orders |
| **Browser Auto-Sync** | A Tampermonkey browser script that runs on BigSeller.com and pushes orders to Odoo every 1 minute automatically |
| **API Cron Sync** | Odoo cron job polls the BigSeller API every 2 minutes to update order statuses |
| **Status Tracking** | Every Sale Order shows its BigSeller marketplace status (New, Shipped, Completed, Cancelled) with a full history tab |
| **3 Cancellation Scenarios** | Handles cancel-before-pick, cancel-after-pick, cancel-after-ship differently |

**Supported marketplaces:** Shopee, Lazada, Lazada2, TikTok

---

## 2. Environment Overview

| Environment | Odoo Version | URL | Purpose |
|---|---|---|---|
| **Local** | Odoo 16 | `http://localhost:8069` | Developer testing |
| **Staging** | Odoo 18e | Ask your team lead | QA / UAT |
| **Production** | Odoo 18e | Ask your team lead | Live system |

> **Important:** Local uses Odoo 16 view syntax (`<tree>`, `attrs`). Staging/Production use Odoo 18e syntax (`<list>`, direct `invisible`). This module has both versions; see [Section 16](#16-odoo-16-vs-odoo-18-dual-compatibility).

---

## 3. Prerequisites — Local Development

### 3.1 Required Software

Install all of these before you start:

| Tool | How to Install |
|---|---|
| **Python 3.10** | `pyenv install 3.10.12` (use pyenv to manage versions) |
| **PostgreSQL 14+** | `brew install postgresql` (macOS) or system package manager |
| **Git** | `brew install git` |
| **wkhtmltopdf** | Download from https://wkhtmltopdf.org/downloads.html |
| **Node.js 16+** | `brew install node` |

### 3.2 Python Libraries

After cloning Odoo 16 source:

```bash
cd /path/to/odoo-16/odoo-source
pip install -r requirements.txt
```

Also install the XLS reading library:

```bash
pip install xlrd==1.2.0
```

### 3.3 PostgreSQL Setup

```bash
# Start PostgreSQL
brew services start postgresql   # macOS

# Create the Odoo database user
psql postgres -c "CREATE USER odoo WITH CREATEDB PASSWORD 'odoo';"

# Create the local development database
createdb -U odoo odoo_dev
```

---

## 4. Getting the Code

### 4.1 Clone the module repository

```bash
# Go to your custom-addons folder
cd /path/to/odoo-16/custom-addons

# Clone vct_bigseller (this module)
git clone https://github.com/replyravi/ta-to-works-odoo-Bigseller-v2.git vct_bigseller
```

### 4.2 Get dependent modules

This module depends on `sale_order_type` and `sale_order_type_ext`. Make sure both are in your `custom-addons` folder:

```
custom-addons/
├── vct_bigseller/          ← This module (cloned from GitHub)
├── sale_order_type/        ← OCA module (ask team for source)
└── sale_order_type_ext/    ← Internal extension (ask team for source)
```

### 4.3 Set up Odoo config file

Create `/etc/odoo16.conf` (or `~/.odoorc`):

```ini
[options]
addons_path = /path/to/odoo-16/odoo-source/addons,/path/to/odoo-16/custom-addons
db_name = odoo_dev
db_user = odoo
db_password = odoo
http_port = 8069
logfile = /path/to/odoo-16/logs/odoo.log
```

---

## 5. Module File Structure

```
vct_bigseller/
│
├── __manifest__.py                 ← Module metadata (name, version, depends, data files)
├── __init__.py                     ← Post-install hook + default settings logic
├── .gitignore                      ← Files excluded from git
│
├── models/
│   ├── __init__.py                 ← Import all models
│   ├── sale_order.py               ← Core: Sale Order fields + all BigSeller sync logic
│   ├── bigseller_sale.py           ← XLS Import wizard model
│   ├── bigseller_json_import.py    ← JSON Import wizard model
│   ├── bigseller_api.py            ← BigSeller HTTP client (session cookie auth)
│   ├── mp_status_history.py        ← Marketplace status history line model
│   └── res_config_settings.py      ← Settings page fields (cookie, sync toggle, etc.)
│
├── views/                          ← Odoo 16 syntax views (tree, attrs)
│   ├── sale_order_view.xml         ← Sale Order form extensions
│   ├── bigseller_sale_wizard.xml   ← XLS + JSON import wizard UI + menu items
│   └── res_config_settings_view.xml ← BigSeller section in Settings
│
├── views_v18/                      ← Odoo 18 syntax views (list, direct invisible)
│   ├── sale_order_view.xml         ← Same as views/ but Odoo 18 compatible
│   ├── bigseller_sale_wizard.xml   ← Same as views/ but Odoo 18 compatible
│   └── res_config_settings_view.xml ← Same as views/ but Odoo 18 compatible
│
├── controllers/
│   └── bigseller_webhook.py        ← HTTP endpoint /bigseller/auto_import
│
├── data/
│   └── bigseller_cron.xml          ← Cron job definition (2-minute API sync)
│
├── security/
│   ├── access_record_rule.xml      ← Group definition: group_import_bigseller_order_v1
│   └── ir.model.access.csv         ← Model access rules (who can read/write)
│
├── static/src/tampermonkey/
│   └── bigseller_odoo_sync.user.js ← Browser script for auto-sync
│
├── migrations/
│   ├── 16.0.7.0.0/post-rebuild.py  ← Runs on `odoo-bin -u vct_bigseller` in Odoo 16
│   └── 18.0.7.0.0/post-rebuild.py  ← Runs on upgrade in Odoo 18
│
├── tools/
│   ├── use_odoo_16.sh              ← Switch manifest to Odoo 16 mode
│   └── use_odoo_18.sh              ← Switch manifest to Odoo 18 mode (default)
│
└── docs/
    ├── DEVELOPER_GUIDE_BigSeller.md
    └── USER_GUIDE_BigSeller_V1.md
```

---

## 6. Architecture: How Everything Connects

```
BigSeller.com
     │
     ├─[Browser]── Tampermonkey Script ──► POST /bigseller/auto_import
     │                                           │
     │                                    controllers/bigseller_webhook.py
     │                                           │
     ├─[XLS File]── Upload in Odoo ──────► models/bigseller_sale.py
     │                                    (gen.bigseller.sale.v1 wizard)
     │
     ├─[JSON Paste]─ Paste in Odoo ─────► models/bigseller_json_import.py
     │                                    (bigseller.json.import wizard)
     │
     └─[API Cron]── Every 2 minutes ────► models/sale_order.py
                                          _bigseller_sync_orders()
                                                │
                                                └── models/bigseller_api.py
                                                    (BigSellerClient HTTP)

All paths converge on:
    models/sale_order.py → _bigseller_create_order() / action_update_mp_status()
         │
         ├── Looks up product by barcode (SKU)
         ├── Resolves customer from sale.order.type.contact_id
         ├── Builds delivery address from receiver fields
         ├── Applies order type defaults (warehouse, pricelist, payment term)
         └── Creates mp.status.history records
```

---

## 7. Installing on Local Odoo 16

### Step 1: Switch to Odoo 16 mode

```bash
cd /path/to/custom-addons/vct_bigseller
bash tools/use_odoo_16.sh
```

This changes the manifest to use `views/` (Odoo 16 syntax) and sets version to `16.0.7.0.0`.

### Step 2: First-time install

```bash
cd /path/to/odoo-16/odoo-source
python3 odoo-bin \
    -c /etc/odoo16.conf \
    -d odoo_dev \
    -i vct_bigseller \
    --stop-after-init
```

> The `-i vct_bigseller` flag tells Odoo to install the module and then stop. This also runs the `post_init_hook` which sets default BigSeller settings automatically.

### Step 3: Start Odoo normally

```bash
python3 odoo-bin -c /etc/odoo16.conf
```

Open your browser at `http://localhost:8069`, log in, and go to **Settings → BigSeller** to see the new settings section.

### Step 4: Upgrading after code changes

Every time you change a Python model or XML view:

```bash
python3 odoo-bin \
    -c /etc/odoo16.conf \
    -d odoo_dev \
    -u vct_bigseller \
    --stop-after-init
```

> Use `-u` (update) not `-i` (install). `-i` only works on fresh install; `-u` re-loads everything.

### Step 5: Checking logs

```bash
tail -f /path/to/odoo-16/logs/odoo.log | grep -E "BigSeller|ERROR|WARNING"
```

---

## 8. Installing on Staging / Production (Odoo 18e)

> **Always back up the database first!**

### Step 1: Backup database

```bash
# SSH into the server
ssh your-server

# Backup
pg_dump -U odoo -F c -b -v -f /tmp/backup_$(date +%Y%m%d_%H%M).dump your_db_name
```

### Step 2: Make sure manifest is in Odoo 18 mode

Before pulling code or pushing, always ensure the manifest is in v18 mode:

```bash
cd /path/to/custom-addons/vct_bigseller
bash tools/use_odoo_18.sh
git add __manifest__.py
git commit -m "chore: ensure v18 manifest for deployment"
git push
```

### Step 3: Pull latest code on the server

```bash
# SSH into server
cd /path/to/custom-addons/vct_bigseller
git pull origin main
```

### Step 4: Verify the manifest is v18

```bash
grep "version\|views_v18" __manifest__.py
# Should show:
#   'version': '18.0.7.0.0',
#   'views_v18/bigseller_sale_wizard.xml',
#   etc.
```

If it shows `views/` instead of `views_v18/`, run `bash tools/use_odoo_18.sh` and commit again.

### Step 5: Run the upgrade

```bash
# The exact command depends on your server setup.
# Common patterns:

# Docker-based:
docker exec -it <container_name> odoo-bin \
    -c /etc/odoo/odoo.conf \
    -d <your_db_name> \
    -u vct_bigseller \
    --stop-after-init

# Systemd-based:
sudo systemctl stop odoo
odoo-bin -c /etc/odoo/odoo.conf -d <your_db_name> -u vct_bigseller --stop-after-init
sudo systemctl start odoo
```

### Step 6: Verify in Odoo

1. Log into Odoo
2. Go to **Settings → BigSeller**
3. You should see: Session Cookie, Base URL, Auto Sync toggle, Carrier Product, Import Report Recipient, Auto-Sync Token, Test Connection button, Sync Now button

### Step 7: Check logs for errors

```bash
# Docker:
docker logs <container_name> --tail 200 | grep -i "bigseller\|error\|warning"

# File-based:
tail -200 /var/log/odoo/odoo.log | grep -i "bigseller\|error\|warning"
```

---

## 9. Required Post-Install Configuration

After installing (both local and staging/production), configure these settings in **Settings → BigSeller**:

### 9.1 Session Cookie (for API Cron Sync)

1. Open **bigseller.com** in Chrome and log in
2. Press `F12` → Application tab → Cookies → `www.bigseller.com`
3. Find the `PHPSESSID` cookie (or all cookies) and copy the full cookie string
4. Paste it into **BigSeller Session Cookie** field in Odoo Settings
5. Click **Test Connection** — you should see "Connection Successful"

> **Note:** The cookie expires. If sync stops working, come back and paste a fresh cookie.

### 9.2 Carrier Product

1. In Odoo, go to **Inventory → Products** (or create a new product)
2. Create a product named "Delivery Charges" with type = **Service**
3. Back in **Settings → BigSeller → Carrier Product**, select that product
4. This product is used when a new delivery carrier is auto-created from BigSeller data

The post-install hook tries to auto-create a product called "BigSeller Delivery Charges" (internal reference: `BIGSELLER_SHIP`). Check if it exists first.

### 9.3 Import Report Recipient

Default is `laxman@ta-to.com`. Change to whoever should receive XLS import summary emails.

### 9.4 Auto-Create New Orders

**Keep this OFF** unless you have explicitly tested in Staging. When ON, the API cron sync will create Sale Orders for any new BigSeller orders it finds. When OFF (safe mode), it only updates statuses on existing orders.

### 9.5 Enable Auto Sync (optional)

Toggle this ON only after:
- Session cookie is valid
- Test Connection passes
- Auto-Create is tested and confirmed safe
- Carrier Product is configured

### 9.6 Generate Auto-Sync Token

Click **Generate Token** in the Browser Auto-Sync section. Copy the token and paste it into the Tampermonkey script. See [Section 12](#12-tampermonkey-auto-sync-script).

### 9.7 Sale Order Types

This is the most important configuration. Go to **Sales → Configuration → Order Types** and ensure these 4 types exist with the correct Contact set:

| Order Type Name | Marketplace | Contact (Customer) |
|---|---|---|
| `MP: Shopee` | Shopee | The company-level Shopee partner |
| `MP: Lazada` | Lazada (ContactsDirect) | The company-level Lazada partner |
| `MP: Lazada2` | Lazada (TA-TO.COM) | The company-level Lazada2 partner |
| `MP: TikTok` | TikTok | The company-level TikTok partner |

Each Order Type should also have: **Carrier** (delivery method), **Payment Term**, **Warehouse** configured.

---

## 10. How to Use the Module (Functional Walkthrough)

### 10.1 Import Orders from XLS File

1. Go to **Sales → Import BigSeller Sale Order V1 (XLS)**
2. Click the **File** field and select the `.xls` file exported from BigSeller
3. Click **Import**
4. Wait for the result — a summary is emailed to the Import Report Recipient
5. Go to **Sales → Orders** to see the newly created Sale Orders

**What the importer does:**
- Reads each row of the XLS file
- Looks up the product by its barcode (SKU column)
- If the product does NOT exist → row is skipped (no auto-creation)
- If the order already exists → only status is updated
- Creates a Sale Order with customer from the matched Order Type's Contact

### 10.2 Import Orders from JSON (Manual)

1. Open bigseller.com → F12 (DevTools) → Network tab
2. Navigate to the Orders page in BigSeller
3. Find the `pageList.json` request → click it → Response tab → Ctrl+A, Ctrl+C
4. In Odoo: **Sales → Import BigSeller Orders (JSON)**
5. Paste the JSON → click **Preview** → review what will be created/updated
6. Click **Import Orders**

### 10.3 Check Order Status

Open any Sale Order that was imported from BigSeller. You will see:
- **Marketplace** group: shows Marketplace name, MP Status, BigSeller Shop, Order ID
- **MP Status** tab: full history of status changes with timestamps

### 10.4 Manual Sync (Settings)

1. Go to **Settings → BigSeller**
2. Click **Sync Now** — this immediately polls the BigSeller API for all 4 statuses
3. A notification shows how many orders were created/updated

---

## 11. How Synchronisation Works (Technical Deep Dive)

### 11.1 Data Flow for a New Order

```
BigSeller order (e.g. Shopee order #SPX123456)
    │
    ▼
1. Extract platformOrderId = "SPX123456"
2. Extract shopName = "ContactsDirect Shopee(1386965355)"
3. _extract_shop_id("ContactsDirect Shopee(1386965355)") → "1386965355"
4. SHOP_ID_TO_ORDER_TYPE["1386965355"] → "MP: Shopee"
5. Search sale.order.type where name = "MP: Shopee" → order_type
6. order_type.contact_id → Customer (e.g. "Shopee Ltd")
7. Build line items:
   - For each item: look up product.product where barcode = varSku
   - If ANY sku is missing → skip entire order, log to bigseller.skipped_orders
8. Build delivery address from receiverName, receiverPhone, receiverStreet, etc.
   (parented under the Customer)
9. Calculate price per marketplace:
   - TikTok:  (orig_price × qty) - (voucher × qty)
   - Lazada:  (price × qty) - (voucher × qty)
   - Shopee:  price as-is
10. Resolve carrier from buyerShippingCarrier name
    - Search delivery.carrier by name
    - If not found: auto-create using Carrier Product from Settings
11. Apply order_type defaults (warehouse, pricelist, payment_term, carrier fallback)
12. self.create(vals) → new Sale Order
13. Log to mp.status.history
14. Apply initial action based on status (ship, invoice, cancel)
```

### 11.2 Deduplication Logic

The module uses a **SQL UNIQUE constraint** on `bigseller_platform_order_id` to prevent duplicates at the database level. Before creating, the code also checks:

```python
domain = ['|',
    ('bigseller_order_id', '=', bs_id),
    ('bigseller_platform_order_id', '=', order_no),
]
existing = self.search(domain, limit=1)
```

If an existing order is found → only update its `mp_status`.

### 11.3 Advisory Lock (Cron Protection)

The cron sync uses a PostgreSQL advisory lock to prevent two cron ticks running at the same time and creating duplicate orders:

```python
self.env.cr.execute(
    'SELECT pg_try_advisory_xact_lock(%s)', (8723145623897210,))
got_lock = self.env.cr.fetchone()[0]
if not got_lock:
    return {'created': 0, 'updated': 0}  # previous tick still running
```

### 11.4 Status to Odoo Action Mapping

| BigSeller Status | Odoo Action |
|---|---|
| `new` | Create Quotation (state: draft) |
| `to_pickup` | Confirm SO + Confirm Delivery |
| `shipped` | Confirm SO + Confirm Delivery |
| `completed` | Create Invoice + Post |
| `canceled` | Run cancellation scenario (see below) |
| `in_process` | No Odoo action (status update only) |
| `platform_processing` | No Odoo action (status update only) |
| `retry_ship` | No Odoo action (status update only) |
| `voided` | No Odoo action (status update only) |

### 11.5 Cancellation Scenarios

| Scenario | Condition | Action |
|---|---|---|
| **1** | No delivery done yet | Cancel SO + all pickings |
| **2** | Picking assigned but not validated | Cancel the picking (returns stock) + Cancel SO |
| **3** | Delivery already validated (goods shipped) | Log note "Return flow – manual credit note required" |

---

## 12. Tampermonkey Auto-Sync Script

The file is at `static/src/tampermonkey/bigseller_odoo_sync.user.js`.

### 12.1 What it does

- Runs in your browser while you are on bigseller.com
- Every 60 seconds, fetches all orders from BigSeller's internal API (all statuses, all pages)
- Sends the orders to Odoo's webhook endpoint `/bigseller/auto_import`
- Shows a floating badge in the bottom-right corner of BigSeller showing sync status

### 12.2 How to Install

1. Install the **Tampermonkey** extension in Chrome:  
   https://www.tampermonkey.net/
2. Click the Tampermonkey icon → **Create a new script**
3. Delete the default content
4. Copy the full content of `static/src/tampermonkey/bigseller_odoo_sync.user.js`
5. Paste it into Tampermonkey
6. Edit the 4 configuration lines at the top (see Section 12.3)
7. Click **File → Save** (or Ctrl+S)
8. Open bigseller.com — you should see the floating badge

### 12.3 Configuration Lines to Edit

Open the script and find this block at the top:

```javascript
const ODOO_URL    = 'https://tatov16.odoo.com';       // ← Your Odoo URL (no trailing slash)
const ODOO_DB     = 'your-database-name';              // ← Your Odoo database name
const ODOO_USER   = 'bigseller@ta-to.com';             // ← Odoo user email
const ODOO_APIKEY = 'your-api-key-here';               // ← Odoo API key (NOT password)
```

**How to get the API Key:**
1. Log into Odoo
2. Click your user avatar (top right) → **My Profile** or **Preferences**
3. Go to the **Account Security** tab
4. Under **API Keys**, click **New API Key**
5. Give it a name (e.g. "Tampermonkey Sync") and copy the key

**For Staging:** Change `ODOO_URL` and `ODOO_DB` to the staging values. Generate a SEPARATE API key for the staging Odoo user.

**For Production:** Use the production URL, DB, and a dedicated production API key.

> **Security Rule:** Never commit your real API key to GitHub. The file in the repo has a placeholder. Only set the real key locally in your Tampermonkey extension.

### 12.4 The Webhook Endpoint

The script calls `POST /bigseller/auto_import` on Odoo. This route is handled by `controllers/bigseller_webhook.py`. It:

1. Validates the `token` from the request body against `bigseller.auto_sync_token` in Odoo Settings
2. Looks up the database by `db` name
3. Passes the `orders_data` to `bigseller.json.import` wizard for processing

**Auto-Sync Token** is generated in Odoo Settings → BigSeller → Generate Token. You do NOT need this token in the Tampermonkey script — the script authenticates using `ODOO_USER` + `ODOO_APIKEY` via Odoo's JSON-RPC auth, not the auto-sync token. The auto-sync token is only for the webhook direct-POST approach.

---

## 13. Key Business Rules You Must Know

These rules are enforced in code and must not be broken when making changes:

### Rule 1: Never Auto-Create Products
Products are **NEVER** auto-created from BigSeller data. If a product's SKU (barcode) does not exist in Odoo, the entire order is **skipped**. This prevents the ~750 phantom product incident that happened in production.

### Rule 2: Dedup by Platform Order ID
Orders are de-duplicated by `bigseller_platform_order_id` (the marketplace order number like `SPX123456789`). If an order with that ID already exists in Odoo, only the status is updated.

### Rule 3: Customer Comes from Order Type
The customer (invoice address) on every BigSeller Sale Order comes from `sale.order.type.contact_id`, NOT from the buyer name. Buyer name becomes the **delivery** contact only.

### Rule 4: Auto-Create Orders is OFF by Default
On fresh install, `bigseller.auto_create_orders` is forced to `False`. This must be explicitly enabled in Settings after Staging validation.

### Rule 5: One Cron at a Time
The PostgreSQL advisory lock prevents two cron ticks from overlapping. Do not disable this lock.

### Rule 6: Shop Allowlist
Only orders from the 4 shops listed in `SHOP_ID_TO_ORDER_TYPE` are processed. Orders from other shops are silently skipped. To add a new shop, update this dictionary in `models/sale_order.py`.

---

## 14. Shop ID → Order Type Mapping

This is the master mapping table defined in `models/sale_order.py`:

```python
SHOP_ID_TO_ORDER_TYPE = {
    '1386965355':          'MP: Shopee',    # ContactsDirect Shopee
    '100800160369':        'MP: Lazada',    # ContactsDirect Lazada
    '101414768012':        'MP: Lazada2',   # TA-TO.COM Lazada
    '7494189457190716861': 'MP: TikTok',   # TIKTOK TA-TO.com
}
```

### How to find a Shop ID

BigSeller sends the shop name in this format: `"ContactsDirect Shopee(1386965355)"`. The number in parentheses is the Shop ID.

### How to add a new shop

1. Find the Shop ID from BigSeller (look at the `shopName` field in any API response from that shop)
2. Open `models/sale_order.py`
3. Add the new entry to `SHOP_ID_TO_ORDER_TYPE`
4. Create the matching `sale.order.type` in Odoo with the exact same name
5. Configure Contact, Carrier, Payment Term, Warehouse on the new Order Type
6. Run `-u vct_bigseller` to apply changes

---

## 15. Making Changes — Step-by-Step

### 15.1 Changing a Python Model

**Example:** Adding a new field `bigseller_tracking_number` to Sale Orders.

**Step 1:** Open `models/sale_order.py` and add the field inside the `SaleOrderBigSellerV1` class:

```python
bigseller_tracking_number = fields.Char(
    string='Tracking Number', copy=False)
```

**Step 2:** Add it to the view. For Odoo 16 (`views/sale_order_view.xml`):

```xml
<field name="bigseller_tracking_number" readonly="1"
       attrs="{'invisible': [('bigseller_tracking_number', '=', False)]}"/>
```

For Odoo 18 (`views_v18/sale_order_view.xml`):

```xml
<field name="bigseller_tracking_number" readonly="1"
       invisible="not bigseller_tracking_number"/>
```

**Step 3:** Run the upgrade:

```bash
python3 odoo-bin -c /etc/odoo16.conf -d odoo_dev -u vct_bigseller --stop-after-init
```

**Step 4:** Check the logs for any errors, then open Odoo and verify the field appears.

### 15.2 Changing the XLS Column Mapping

The XLS column indices are defined as constants at the top of `models/bigseller_sale.py`:

```python
COL_ORDER_NO        = 0
COL_ORDER_STATUS    = 7
COL_MARKETPLACE     = 9
# ... etc.
```

**To change a column:** Update the constant number. Column counting starts at 0 (first column = 0). Then run `-u vct_bigseller`.

> **How to find column numbers:** Open the BigSeller XLS in Excel, count from column A (=0).

### 15.3 Adding a New Status

1. Add the new status to `BIGSELLER_STATUS_SELECTION` in `models/mp_status_history.py`
2. Add the status to `STATUS_ACTION_MAP` in `models/sale_order.py`
3. Add the status to `XLS_STATUS_MAP` in `models/bigseller_sale.py`
4. Add the status to `_map_bigseller_status()` mapping dict in `models/sale_order.py`
5. Run `-u vct_bigseller`

### 15.4 Changing Settings Fields

Settings fields are in `models/res_config_settings.py`. Each field has a `config_parameter` that links it to an `ir.config_parameter` key. To add a new setting:

```python
bigseller_my_new_setting = fields.Char(
    string='My New Setting',
    config_parameter='bigseller.my_new_setting',
    help='What this setting does.')
```

Then add it to the view in both `views/res_config_settings_view.xml` and `views_v18/res_config_settings_view.xml`.

### 15.5 Changing the Cron Interval

The cron interval is in `data/bigseller_cron.xml`. **But** because cron records have `noupdate="1"`, you cannot change the XML and expect Odoo to update the existing record during `-u`.

**Correct way:** Change it in Odoo UI directly.

Go to **Settings → Technical → Automation → Scheduled Actions** → find "BigSeller: Sync Orders" → change the interval.

Or via SQL:

```sql
UPDATE ir_cron SET interval_number = 5 WHERE name = 'BigSeller: Sync Orders (every 2 min)';
```

---

## 16. Odoo 16 vs Odoo 18 Dual Compatibility

This module maintains two sets of view files to work on both Odoo 16 (local dev) and Odoo 18e (staging/production).

| Syntax difference | Odoo 16 (`views/`) | Odoo 18 (`views_v18/`) |
|---|---|---|
| Table element | `<tree>` | `<list>` |
| Conditional visibility | `attrs="{'invisible': [('field', '=', value)]}"` | `invisible="not field_name"` |
| Boolean toggle | `attrs="{'invisible': [('enabled', '=', False)]}"` | `invisible="not enabled"` |

### When to use which mode

```bash
# Working locally with Odoo 16:
bash tools/use_odoo_16.sh
# This changes manifest: views/ paths + version 16.0.x.x.x

# Before pushing to GitHub (for staging/production):
bash tools/use_odoo_18.sh
# This changes manifest: views_v18/ paths + version 18.0.x.x.x
```

### Rule: Always push in Odoo 18 mode

Before every `git push`, run `bash tools/use_odoo_18.sh` to ensure the repo is in the correct state for staging/production deployment.

### When you add a new view element

You must add it to **both** `views/` and `views_v18/` files with the appropriate syntax for each.

---

## 17. Git Workflow — How to Push Changes

### 17.1 Standard workflow

```bash
# 1. Make your code changes in vct_bigseller/

# 2. Test locally with Odoo 16 (already in Odoo 16 mode)
python3 odoo-bin -c /etc/odoo16.conf -d odoo_dev -u vct_bigseller --stop-after-init

# 3. If tests pass, switch to Odoo 18 mode for the push
cd /path/to/custom-addons/vct_bigseller
bash tools/use_odoo_18.sh

# 4. Stage all changes
git add -A

# 5. Review what you are committing
git status
git diff --cached

# 6. Commit with a clear message
git commit -m "feat: add bigseller_tracking_number field to Sale Order

- Added Char field bigseller_tracking_number to sale.order
- Added to views/ (Odoo 16 attrs syntax)
- Added to views_v18/ (Odoo 18 direct invisible syntax)
- Populated from XLS column COL_TRACKING"

# 7. Push
git push origin main
```

### 17.2 Commit message convention

Use this format:

```
<type>: <short description>

<optional detailed body>
```

Types:
- `feat:` — new feature
- `fix:` — bug fix
- `refactor:` — code restructure (no behavior change)
- `chore:` — maintenance (version bumps, gitignore, etc.)
- `docs:` — documentation only

### 17.3 DO NOT commit these files

- Real API keys, session cookies, passwords
- `.DS_Store`, `__pycache__/` (covered by `.gitignore`)
- Database dump files

---

## 18. Troubleshooting Common Errors

### Error: `sale.order.type has no attribute contact_id`

**Cause:** The `sale_order_type_ext` module is missing or not installed.  
**Fix:** Install `sale_order_type_ext` which adds `contact_id`, `payment_term_id`, and `carrier_id` fields to `sale.order.type`.

```bash
python3 odoo-bin -c /etc/odoo16.conf -d odoo_dev -i sale_order_type_ext --stop-after-init
```

---

### Error: `duplicate key value violates unique constraint "bigseller_platform_order_id_uniq"`

**Cause:** There are already duplicate `bigseller_platform_order_id` values in the database from before the unique constraint was added.  
**Fix:** Run this SQL to find duplicates, then clean them:

```sql
-- Find duplicates
SELECT bigseller_platform_order_id, COUNT(*)
FROM sale_order
WHERE bigseller_platform_order_id IS NOT NULL
GROUP BY bigseller_platform_order_id
HAVING COUNT(*) > 1;

-- For each duplicate, keep the best one (lowest id = oldest)
-- and nullify the bigseller_platform_order_id on duplicates:
UPDATE sale_order
SET bigseller_platform_order_id = NULL
WHERE id NOT IN (
    SELECT MIN(id)
    FROM sale_order
    WHERE bigseller_platform_order_id IS NOT NULL
    GROUP BY bigseller_platform_order_id
)
AND bigseller_platform_order_id IS NOT NULL;
```

Then run `-u vct_bigseller` again.

---

### Error: `Module 'xlrd' not found` or `No module named xlrd`

**Fix:**
```bash
pip install xlrd==1.2.0
```

> Important: Use version `1.2.0` — newer versions of xlrd dropped `.xls` support and only support `.xlsx`.

---

### Error: `BigSeller sync: session expired or invalid`

**Cause:** The session cookie in Odoo Settings has expired.  
**Fix:**
1. Log into bigseller.com
2. Open DevTools → Application → Cookies → Copy all cookies
3. Go to Odoo → Settings → BigSeller → paste fresh cookie → Save → Test Connection

---

### Error: `No sale.order.type found for platform "Shopee" / shop "..."`

**Cause:** The shop ID is not in `SHOP_ID_TO_ORDER_TYPE` OR the matching `sale.order.type` doesn't exist in Odoo.  
**Fix:**
1. Check `SHOP_ID_TO_ORDER_TYPE` in `models/sale_order.py` — is the shop ID listed?
2. Go to **Sales → Configuration → Order Types** — does `MP: Shopee` exist?
3. If the shop is new, add the Shop ID to the dictionary and create the Order Type

---

### Error: `Skipping order — unknown SKU(s): ABC123`

**Cause:** The product with barcode `ABC123` does not exist in Odoo.  
**Fix:** Create the product in Odoo with the exact SKU value set as the **Barcode** field.

To find all skipped orders:
```sql
SELECT value FROM ir_config_parameter WHERE key = 'bigseller.skipped_orders';
```

---

### Error: Views don't load on Staging (Odoo 18e)

**Cause:** The manifest is still pointing to `views/` (Odoo 16 syntax) instead of `views_v18/`.  
**Fix:**
```bash
cd /path/to/vct_bigseller
bash tools/use_odoo_18.sh
git add __manifest__.py && git commit -m "chore: switch to v18 views" && git push
# Then on staging server: git pull && -u vct_bigseller
```

---

### Error: `field bigseller_session_cookie does not exist`

**Cause:** You're trying to query `res_config_settings` directly — these are transient fields and don't have database columns.  
**Fix:** Use `ir.config_parameter` to read the value:

```python
# In Python:
cookie = env['ir.config_parameter'].sudo().get_param('bigseller.session_cookie', '')

# In SQL (read-only):
SELECT value FROM ir_config_parameter WHERE key = 'bigseller.session_cookie';
```

---

## 19. Database SQL Cheatsheet

Use these queries for debugging and administration. **Always test on Staging before running on Production.**

```sql
-- List all BigSeller Sale Orders with their status
SELECT name, bigseller_platform_order_id, mp_status, mp_marketplace, state
FROM sale_order
WHERE mp_marketplace IS NOT NULL
ORDER BY create_date DESC
LIMIT 50;

-- Count orders per marketplace
SELECT mp_marketplace, mp_status, COUNT(*)
FROM sale_order
WHERE mp_marketplace IS NOT NULL
GROUP BY mp_marketplace, mp_status
ORDER BY mp_marketplace, mp_status;

-- Show all BigSeller config parameters
SELECT key, value
FROM ir_config_parameter
WHERE key LIKE 'bigseller.%'
ORDER BY key;

-- See recent skipped orders (bad SKUs etc.)
SELECT value FROM ir_config_parameter WHERE key = 'bigseller.skipped_orders';

-- Find orders created today
SELECT name, bigseller_platform_order_id, mp_marketplace, create_date
FROM sale_order
WHERE mp_marketplace IS NOT NULL
  AND create_date >= CURRENT_DATE
ORDER BY create_date DESC;

-- Find duplicate platform_order_ids (should return empty if constraint is active)
SELECT bigseller_platform_order_id, COUNT(*)
FROM sale_order
WHERE bigseller_platform_order_id IS NOT NULL
GROUP BY bigseller_platform_order_id
HAVING COUNT(*) > 1;

-- Reset auto-sync error message
UPDATE ir_config_parameter SET value = '' WHERE key = 'bigseller.last_sync_error';

-- Manually disable auto-create (safety)
UPDATE ir_config_parameter SET value = 'False' WHERE key = 'bigseller.auto_create_orders';

-- Check if cron is active
SELECT name, active, interval_number, interval_type, nextcall
FROM ir_cron
WHERE name LIKE '%BigSeller%';

-- Enable the cron (alternative to UI)
UPDATE ir_cron SET active = true
WHERE name = 'BigSeller: Sync Orders (every 2 min)';
```

---

## 20. Glossary

| Term | Meaning |
|---|---|
| **BigSeller** | Third-party order management platform used by TA-TO |
| **platformOrderId** | The marketplace's own order number (e.g. `SPX123456789` from Shopee) |
| **bigseller_order_id** | BigSeller's internal ID for the order (a different number) |
| **Sale Order (SO)** | An order record in Odoo (`sale.order` model) |
| **Quotation (QTN)** | A Sale Order in draft state (not yet confirmed) |
| **sale.order.type** | A template that groups marketplace settings (warehouse, pricelist, carrier, customer) |
| **mp_status** | Marketplace status stored on the Sale Order (new, shipped, completed, etc.) |
| **mp.status.history** | A log line recording each status change with timestamp and Odoo action taken |
| **XLS Import** | Uploading a BigSeller Excel export file to create/update Sale Orders |
| **JSON Import** | Pasting a BigSeller API response JSON to create/update Sale Orders |
| **Tampermonkey** | A browser extension that runs custom JavaScript on specific websites |
| **auto_sync_token** | A secret token generated in Odoo Settings used to authenticate the webhook POST |
| **advisory lock** | A PostgreSQL mechanism to prevent two processes running the same code simultaneously |
| **carrier_product_id** | A product in Odoo used as the "service product" when auto-creating a delivery carrier |
| **barcode** | The field on `product.product` used to match a BigSeller SKU to an Odoo product |
| **contact_id** | Field on `sale.order.type` that defines the Customer for marketplace orders |
| **Odoo 16** | Local development version of Odoo (view syntax: `<tree>`, `attrs`) |
| **Odoo 18e** | Enterprise edition used on staging/production (view syntax: `<list>`, direct `invisible`) |
| **post_init_hook** | Python function Odoo calls automatically when a module is first installed |
| **migration script** | Python file in `migrations/<version>/post-rebuild.py` that Odoo runs during `-u` upgrades |
| **ir.config_parameter** | Odoo's key-value store used to persist BigSeller settings |
| **SHOP_ID_TO_ORDER_TYPE** | Python dictionary in `sale_order.py` that maps shop IDs to Order Type names |

---

*For questions or issues, contact the module author or check the GitHub repo.*
