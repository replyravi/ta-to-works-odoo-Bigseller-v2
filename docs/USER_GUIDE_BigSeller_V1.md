# BigSeller Order V1 — User Guide for Odoo Functional Users

> **Module:** RSS BigSeller Order V1  
> **For:** Odoo functional consultants, operations managers, and end users  
> **Odoo version:** 16 (also supports Odoo 18)  
> **Last updated:** April 2026  
> **No coding knowledge required** — this guide is written entirely in business language.

---

## Table of Contents

1. [What Is This Module?](#1-what-is-this-module)
2. [What You See in Odoo After Installation](#2-what-you-see-in-odoo-after-installation)
3. [Before You Start — Setup Checklist](#3-before-you-start--setup-checklist)
4. [How to Import Orders from BigSeller XLS File](#4-how-to-import-orders-from-bigseller-xls-file)
5. [How to View Marketplace Information on a Sale Order](#5-how-to-view-marketplace-information-on-a-sale-order)
6. [Understanding the MP Status Tab (History)](#6-understanding-the-mp-status-tab-history)
7. [What Happens Automatically When Status Changes](#7-what-happens-automatically-when-status-changes)
8. [How Cancellations Are Handled](#8-how-cancellations-are-handled)
9. [BigSeller API Configuration (Settings Page)](#9-bigseller-api-configuration-settings-page)
10. [How to Set Up the Session Cookie (Step by Step)](#10-how-to-set-up-the-session-cookie-step-by-step)
11. [How Automatic Sync Works](#11-how-automatic-sync-works)
12. [Marketplace Statuses Explained](#12-marketplace-statuses-explained)
13. [What Master Data Must Exist Before Importing](#13-what-master-data-must-exist-before-importing)
14. [Frequently Asked Questions (FAQ)](#14-frequently-asked-questions-faq)
15. [If Something Changes in the Future — What to Tell the Developer](#15-if-something-changes-in-the-future--what-to-tell-the-developer)
16. [Troubleshooting — Common Problems and Solutions](#16-troubleshooting--common-problems-and-solutions)
17. [User Permission (Security Group)](#17-user-permission-security-group)
18. [Quick Reference Card](#18-quick-reference-card)

---

## 1. What Is This Module?

BigSeller is a platform that connects multiple e-commerce marketplaces (Shopee, Lazada, TikTok Shop, etc.) into one dashboard. Sellers manage all their marketplace orders through BigSeller.

This Odoo module **bridges BigSeller and Odoo**, so that:

- **Marketplace orders** created on Shopee/Lazada/TikTok appear in Odoo as Sale Orders (Quotations)
- **Status changes** (e.g., order shipped, order completed) are tracked and recorded
- **Odoo actions happen automatically** — when an order ships, Odoo confirms the sale order and delivery; when an order completes, Odoo creates an invoice
- **Cancellations are handled intelligently** depending on warehouse progress

**Two ways to bring orders in:**

| Method | How it works | When to use |
|---|---|---|
| **XLS Import** | Export orders from BigSeller as `.xls` file, upload in Odoo | Daily manual import, or when API sync is not available |
| **API Auto-Sync** | Odoo connects to BigSeller website automatically | Continuous synchronisation (requires session cookie setup) |

---

## 2. What You See in Odoo After Installation

### New menu item
```
Sales  >  Orders  >  Import BigSeller Sale Order V1
```
This opens a popup where you upload the XLS file.

### New section on every Sale Order form

When you open a Sale Order that was imported from BigSeller, you will see:

**Marketplace group** (visible near the top of the form, below the main header):

| Field | What it shows | Example |
|---|---|---|
| Marketplace | Which platform the order came from | Shopee |
| MP Status | Current marketplace status | Shipped |
| MP Last Update | Date/time when status was last updated | 2026-04-10 14:30:00 |

**MP Status tab** (visible as a new tab at the bottom, next to "Order Lines"):

A table showing the **complete history** of every status change for this order:

| Column | What it shows |
|---|---|
| Update Date | When the status changed |
| Marketplace | Platform name (Shopee, Lazada, etc.) |
| BigSeller Status | The status from BigSeller's system |
| MP Status | Marketplace-specific status text |
| Odoo Action | What Odoo did in response |
| Notes | Any additional information |

> **Note:** The Marketplace group and MP Status tab only appear on orders that have marketplace data. Regular Odoo orders (not from BigSeller) will look exactly the same as before.

### New section in Settings
```
Settings  >  Sales  >  BigSeller
```
This is where you configure the API connection (session cookie, sync toggle, etc.).

### New Scheduled Action
```
Settings  >  Technical  >  Automation  >  Scheduled Actions  >  "BigSeller: Sync Orders"
```
This is the background job that automatically syncs orders. It is **turned off by default**.

---

## 3. Before You Start — Setup Checklist

Before importing any orders, make sure these items exist in Odoo:

### Required Master Data

| What | Where to set up | Example | Why needed |
|---|---|---|---|
| **Sale Order Type** | Sales > Configuration > Order Types | "Shopee Store A" | Groups all import settings (team, warehouse, salesperson, etc.) |
| **Sales Team** | Sales > Configuration > Sales Teams | "Marketplace Team" | Assigned to imported orders |
| **Salesperson** | Settings > Users & Companies > Users | "John Smith" | Assigned to imported orders |
| **Fiscal Position** | Accounting > Configuration > Fiscal Positions | "Thailand VAT" | Tax rules for marketplace orders |
| **Pricelist** | Sales > Configuration > Pricelists | "THB Pricelist" | Currency and pricing rules |
| **Source** (UTM) | Sales > Configuration > UTM Sources | "Shopee" | Tracks where the order came from |
| **Warehouse** | Inventory > Configuration > Warehouses | "Main Warehouse" | Where goods are shipped from |
| **Products** | Inventory > Products | All SKUs from BigSeller | Matched by Internal Reference (SKU code) |
| **Payment Term** | Accounting > Configuration > Payment Terms | "BIGSELLER Payment" | Must exist with this exact name |
| **Partner / Company** | Contacts | "BIGSELLER" (company) | Master partner record for marketplace orders |

### Configuring a Sale Order Type

The Sale Order Type is the most important configuration. It acts as a **profile** that tells the import wizard which settings to use. Here's how to set one up:

1. Go to **Sales > Configuration > Order Types**
2. Click **Create**
3. Fill in:
   - **Name:** Use the store nickname from BigSeller (e.g., "TATO-Shopee-TH"). This must **exactly match** what appears in column L (Store Nickname) of the XLS file.
   - **Sales Team:** Select the team
   - **Salesperson:** Select the user
   - **Fiscal Position:** Select the tax configuration
   - **Pricelist:** Select the currency/pricing
   - **Source:** Select the UTM source
   - **Warehouse:** Select the warehouse
4. Click **Save**

> **Important:** The "Name" of the Sale Order Type must **exactly match** the Store Nickname value in the BigSeller XLS export. If BigSeller shows the store as "TATO-Shopee-TH" in column L, the Order Type name must be "TATO-Shopee-TH" (case-sensitive).

---

## 4. How to Import Orders from BigSeller XLS File

### Step 1 — Export orders from BigSeller

1. Log into **bigseller.com**
2. Go to **Orders** section
3. Select the status tab you want to export (Shipped, Completed, or Cancelled)
4. Click **Export** and download the `.xls` file
5. Save it to your computer

### Step 2 — Import into Odoo

1. In Odoo, go to **Sales > Orders > Import BigSeller Sale Order V1**
2. A popup window appears
3. Click **Upload your file** and select the `.xls` file you downloaded
4. Click **Import**

### Step 3 — Review results

After the import completes:
- Odoo automatically opens a **list of all created/updated Sale Orders**
- Each order appears as a **Quotation (Draft)** or **Cancelled** (depending on the BigSeller status)
- Orders that already exist in Odoo are **updated** (not duplicated)

### What the import does for each row in the XLS file:

```
For each row in the XLS:
  │
  ├─ Is the status "Shipped", "Completed", or "Canceled"?
  │    NO  → Skip this row (other statuses are not imported)
  │    YES → Continue
  │
  ├─ Does this order number already exist in Odoo?
  │    YES → Update the existing order (add new product lines if needed)
  │    NO  → Create a new Sale Order (Quotation)
  │
  ├─ Is the status "Canceled"?
  │    YES → Create the order in "Cancelled" state
  │    NO  → Create the order in "Draft" (Quotation) state
  │
  └─ For the new order:
       - Set the marketplace name (Shopee/Lazada/TikTok)
       - Set the MP Status
       - Create the first MP Status history entry
       - Add product line(s) with quantity, price, and discount
```

### Important notes about importing:

- **Only 3 statuses are imported:** Shipped, Completed, and Canceled. Other statuses (like "New" or "In Process") are skipped. This is by design — those orders are not yet ready for Odoo.
- **Duplicate protection:** If you import the same file twice, it will not create duplicate orders. It checks by order number.
- **Multi-line orders:** If an order has multiple products, each product appears as a separate row in the XLS. The import correctly groups them into one Sale Order with multiple order lines.
- **Products must exist first:** Every SKU in the XLS file must already exist as a Product in Odoo (matched by "Internal Reference" / `default_code`). If a product is not found, the import stops and shows an error message telling you which SKU is missing.

---

## 5. How to View Marketplace Information on a Sale Order

1. Go to **Sales > Orders**
2. Open any Sale Order that was imported from BigSeller
3. Look at the top of the form — you will see the **Marketplace** section:

```
┌─────────────────────────────────────────────────────────────┐
│ Marketplace                                                  │
│                                                              │
│  Marketplace:    Shopee          MP Last Update: 10/04/2026  │
│  MP Status:      Shipped                        14:30:00     │
└─────────────────────────────────────────────────────────────┘
```

4. Scroll down to the tabs area (below Order Lines) and click the **"MP Status"** tab:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ MP Status                                                                 │
│                                                                           │
│ Update Date      │ Marketplace │ BigSeller Status │ Odoo Action   │ Notes │
│──────────────────┼─────────────┼──────────────────┼───────────────┼───────│
│ 10/04/2026 14:30 │ Shopee      │ Shipped          │ Confirmed SO  │ ...   │
│ 10/04/2026 09:00 │ Shopee      │ New              │ Created QTN   │ ...   │
└──────────────────────────────────────────────────────────────────────────┘
```

> **Tip:** The Marketplace group and MP Status tab only appear when the order has a marketplace value. If you don't see them on an order, it means that order was not imported from BigSeller.

---

## 6. Understanding the MP Status Tab (History)

The MP Status tab shows a **timeline of everything that happened** to this order on the marketplace side and what Odoo did in response. You cannot add, edit, or delete rows manually — they are created automatically by the system.

Each row represents one status change event:

| Column | Meaning |
|---|---|
| **Update Date** | When the status change was recorded in Odoo |
| **Marketplace** | The platform name (Shopee, Lazada, TikTok) |
| **BigSeller Status** | The standardised status name from BigSeller |
| **MP Status** | The marketplace's own status text (may differ between platforms) |
| **Odoo Action** | What Odoo did automatically (e.g., "Confirmed SO + Confirm Delivery") |
| **Notes** | Additional context (e.g., "Initial import via XLS" or "Auto-synced from BigSeller API") |

**Example history for a normal order lifecycle:**

| # | BigSeller Status | Odoo Action | What happened |
|---|---|---|---|
| 1 | New | Created Quotation | Order was first imported from XLS |
| 2 | Shipped | Confirmed SO + Confirm Delivery | Customer's order was shipped → Odoo confirmed the SO and delivery |
| 3 | Completed | Created Invoice + Posted | Order was delivered → Odoo created and posted the invoice |

---

## 7. What Happens Automatically When Status Changes

This is the most important section. When the marketplace status changes (detected via a new XLS import or API sync), Odoo takes action automatically:

| When status changes to... | Odoo does this automatically |
|---|---|
| **New** | Creates a Quotation (draft Sale Order). No further action. |
| **In Process** | Nothing — order is being processed by the marketplace. |
| **Platform Processing** | Nothing — platform is verifying payment (Shopee-specific). |
| **To Pickup** | **Confirms the Quotation into a Sale Order** + **Validates the delivery** (marks goods as sent). |
| **Retry Ship** | Nothing — courier pickup failed, marketplace will retry. |
| **Shipped** | **Confirms the Quotation into a Sale Order** + **Validates the delivery** (marks goods as sent). |
| **Completed** | **Creates an Invoice** + **Posts (validates) the Invoice**. If the order is not yet confirmed, it confirms and delivers first. |
| **Canceled** | **Cancels the Sale Order** (see cancellation scenarios in Section 8). |
| **Voided** | Nothing — order is on manual hold. |

### Visual flow of automatic actions:

```
                         XLS Import or API Sync detects status change
                                          │
                         ┌────────────────┼────────────────────┐
                         │                │                    │
                    Shipped/To Pickup   Completed          Canceled
                         │                │                    │
                         ▼                ▼                    ▼
              ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
              │ Is order still   │  │ Is order still   │  │ Check warehouse  │
              │ a draft QTN?     │  │ a draft QTN?     │  │ picking status   │
              │  YES → Confirm   │  │  YES → Confirm   │  │ (see Section 8)  │
              │  NO  → Skip      │  │  + Deliver first │  └──────────────────┘
              └────────┬─────────┘  └────────┬─────────┘
                       │                     │
                       ▼                     ▼
              ┌──────────────────┐  ┌──────────────────┐
              │ Validate all     │  │ Create Invoice   │
              │ delivery pickings│  │ Post Invoice     │
              │ (mark as sent)   │  └──────────────────┘
              └──────────────────┘
```

> **Note:** If any automatic action fails (e.g., product is out of stock so delivery cannot be validated), Odoo logs a warning but does NOT stop. The order remains in its current state and can be handled manually.

---

## 8. How Cancellations Are Handled

When a marketplace order is cancelled, the system checks **how far the order has progressed in the warehouse** and handles it differently:

### Scenario 1 — Nothing has been picked yet

**Situation:** The warehouse has not started processing the order.

**What Odoo does:**
- Cancels all delivery orders
- Cancels the Sale Order
- Records in history: "Cancelled SO + Deliveries"

**Action needed from you:** None. Everything is cleaned up automatically.

---

### Scenario 2 — Goods have been picked but not shipped

**Situation:** Warehouse staff have reserved/picked the items, but they haven't left the building yet.

**What Odoo does:**
- Cancels the pending delivery pickings (goods return to available stock)
- Cancels the Sale Order
- Records in history: "Reversed picking + Cancelled SO"

**Action needed from you:** None. Stock is automatically returned.

---

### Scenario 3 — Goods have already been shipped

**Situation:** The goods have already left the warehouse (delivery is marked as "Done").

**What Odoo does:**
- Does NOT cancel the Sale Order (because goods are already with the customer)
- Records in history: "Return flow — manual credit note required"

**Action needed from you:**
1. Wait for the goods to be physically returned
2. Go to Inventory > Operations > create a **Return** for the delivered goods
3. Go to Accounting > create a **Credit Note** to reverse the invoice
4. Manually cancel the Sale Order if needed

---

## 9. BigSeller API Configuration (Settings Page)

The API connection allows Odoo to automatically check BigSeller for status changes without you having to export and import XLS files every time.

### How to access the settings:

1. Go to **Settings** (top menu)
2. Scroll down to find the **Sales** section
3. Look for the **BigSeller** subsection

### Settings fields explained:

| Field | What it does | Default |
|---|---|---|
| **Enable Auto Sync** | Toggle switch. When ON, Odoo will periodically check BigSeller for order updates. | OFF |
| **Sync Interval** | How often (in minutes) Odoo checks BigSeller. Only visible when Auto Sync is enabled. | 30 minutes |
| **BigSeller Base URL** | The website address of BigSeller. | `https://www.bigseller.com` |
| **Session Cookie** | Your login session from BigSeller's website (see Section 10 for how to get this). | Empty |
| **Test Connection** button | Checks if the session cookie is valid and BigSeller recognises the session. | — |
| **Sync Now** button | Immediately runs a sync (instead of waiting for the next scheduled run). | — |
| **Last Sync** | Shows when the last successful sync happened. Read-only. | — |
| **Last Sync Error** | Shows the error message if the last sync failed. Read-only. | — |

### After changing settings:
Always click **Save** at the top of the Settings page before testing the connection or syncing.

---

## 10. How to Set Up the Session Cookie (Step by Step)

BigSeller does not have a public API. To connect, we use the same session that your browser uses when you are logged in. Here's how to capture it:

### Step 1 — Log into BigSeller

1. Open **Google Chrome** (recommended)
2. Go to **https://www.bigseller.com**
3. Log in with your BigSeller username and password
4. Complete the CAPTCHA if prompted
5. Make sure you can see the BigSeller dashboard (you are logged in)

### Step 2 — Open Developer Tools

1. Press **F12** on your keyboard (or right-click anywhere on the page and select "Inspect")
2. A panel opens on the right side of the screen
3. Click on the **Application** tab at the top of this panel
   - If you don't see "Application", click the **>>** arrows to find it

### Step 3 — Copy the cookies

1. In the left sidebar of the Application panel, expand **Cookies**
2. Click on **https://www.bigseller.com**
3. You will see a table of cookie names and values
4. You need to copy ALL cookies as a single string. The easiest way:
   - Click in the **Console** tab instead
   - Type this and press Enter: `document.cookie`
   - Select and copy the entire output text

**Alternative method (easier):**
- In the Application > Cookies view, look for the cookie named **PHPSESSID**
- Copy its value
- The session cookie to paste in Odoo looks like: `PHPSESSID=your_session_id_here`

### Step 4 — Paste into Odoo

1. Go to **Settings > Sales > BigSeller**
2. Paste the cookie text into the **Session Cookie** field
3. Click **Save**
4. Click **Test Connection**
5. If you see a green "Connection Successful" message — you're done!
6. If you see an error — the cookie may be expired, log into BigSeller again and repeat

### How often do I need to do this?

The session cookie expires after approximately **24 hours** of inactivity. If auto-sync stops working and you see "Session expired" in the Last Sync Error field, you need to:
1. Log into BigSeller again in your browser
2. Copy fresh cookies
3. Paste in Odoo Settings
4. Save and Test Connection

---

## 11. How Automatic Sync Works

When enabled, the system runs a background job every 30 minutes (configurable) that:

1. **Checks** if auto sync is enabled in settings
2. **Reads** the session cookie from settings
3. **Tests** the connection to BigSeller
4. **Fetches** orders with statuses: New, Shipped, Completed, Canceled
5. For each order found in BigSeller:
   - **Looks up** the order number in Odoo
   - If the order exists in Odoo and the status has changed → **Updates** the MP status and triggers the automatic Odoo action
   - If the order does not exist in Odoo → Skips it (new orders are only created via XLS import)
6. **Records** the sync timestamp

### What Auto Sync does NOT do:

- It does **NOT create new orders** in Odoo. It only updates statuses of existing orders that were already imported via XLS.
- It does **NOT** update prices, quantities, or product lines.
- It does **NOT** work if the session cookie is expired.

### How to enable Auto Sync:

1. Go to **Settings > Sales > BigSeller**
2. Toggle ON **Enable Auto Sync**
3. Set the **Sync Interval** (default: 30 minutes)
4. Paste a valid **Session Cookie**
5. Click **Save**
6. Click **Test Connection** to verify
7. Optionally click **Sync Now** to run immediately

### How to check if sync is working:

- Check the **Last Sync** timestamp in Settings — it should update every 30 minutes
- If **Last Sync Error** shows a message, the sync is failing (most likely expired cookie)
- You can also check in Settings > Technical > Scheduled Actions > "BigSeller: Sync Orders" to see the job's run history

---

## 12. Marketplace Statuses Explained

Here's what each BigSeller status means in real-world business terms:

| BigSeller Status | What It Means | Shopee Equivalent | Lazada Equivalent |
|---|---|---|---|
| **New** | Customer placed the order, not yet processed | To Ship (Unprocessed) | Pending |
| **In Process** | Seller accepted and is preparing the order | To Ship (Processed) | Ready to Ship |
| **Platform Processing** | Platform is verifying payment (Shopee-specific) | Payment Verifying | — |
| **To Pickup** | Packed and waiting for courier to collect | To Ship (Processed) | Ready to Ship |
| **Retry Ship** | Courier missed the pickup, will try again | Pickup Failed | — |
| **Shipped** | Goods are with the courier, in transit | Shipping | Shipped |
| **Completed** | Customer received goods, order is finished | Completed | Delivered |
| **Canceled** | Order was cancelled (by customer, seller, or platform) | Cancelled | Cancelled |
| **Voided** | Manual hold — might be fraud investigation | — | — |

---

## 13. What Master Data Must Exist Before Importing

If you get errors during import, it is almost always because some **master data is missing** in Odoo. Here is a complete list of what must be pre-configured:

### Must exist with exact matching names:

| Data | How it's matched | Where to create/check |
|---|---|---|
| **Sale Order Type** | Matched by name = Store Nickname from XLS column L | Sales > Configuration > Order Types |
| **Products** | Matched by Internal Reference (SKU) = SKU from XLS column Y | Inventory > Products |
| **Payment Term** | Must exist with name = "BIGSELLER Payment" | Accounting > Configuration > Payment Terms |
| **Delivery Route** | Must exist with name = "TATO 21 (MP): Deliver in 1-Step" | Inventory > Configuration > Routes |

### Must be configured on the Sale Order Type:

| Field on Order Type | Example value | Where to check |
|---|---|---|
| Sales Team | "Marketplace Team" | Sales > Configuration > Sales Teams |
| Salesperson | "John Smith" | Settings > Users |
| Fiscal Position | "Thailand VAT" | Accounting > Configuration > Fiscal Positions |
| Pricelist | "THB Pricelist" | Sales > Configuration > Pricelists |
| Source | "Shopee" | Settings > Technical > UTM Sources |
| Warehouse | "Main Warehouse" | Inventory > Configuration > Warehouses |
| Company | Must match the active company | Settings > Companies |

### Auto-created (you don't need to set up):

| Data | What happens |
|---|---|
| **Buyer names** (contacts) | Created automatically as delivery addresses under the marketplace partner |
| **Cancel reasons** | Created automatically if they don't exist |
| **Marketplace partner** (e.g., "Shopee") | Created automatically as a company-type contact |

---

## 14. Frequently Asked Questions (FAQ)

### Q: I imported the same file twice. Will it create duplicate orders?
**A:** No. The system checks by order number. If an order already exists, it updates the status and adds any new product lines that weren't there before. It does not create duplicates.

### Q: Why do I only see Shipped, Completed, and Canceled orders after import? Where are the New orders?
**A:** By design, only orders with status "Shipped", "Completed", or "Canceled" are imported. "New" and "In Process" orders are not yet confirmed by the marketplace and should not be processed in Odoo yet.

### Q: An order was imported but I don't see the Marketplace group on the form. Why?
**A:** The Marketplace group only appears when the `Marketplace` field has a value. Check if the XLS file had the marketplace name in column J. If the column was empty, the group won't be visible.

### Q: Can I manually change the MP Status on a Sale Order?
**A:** No, the Marketplace and MP Status fields are read-only. They can only be changed by the import wizard or the API sync. This is intentional to keep the history accurate.

### Q: The import failed with "product is not found". What do I do?
**A:** The error message includes the SKU that was not found. Go to **Inventory > Products**, create the product, and set its **Internal Reference** to the exact SKU from the error message. Then try importing again.

### Q: The import failed with "Sale Order Type is not configured". What do I do?
**A:** The Store Nickname from the XLS file (column L) does not match any Sale Order Type in Odoo. Go to **Sales > Configuration > Order Types** and create one with a name that exactly matches the store nickname.

### Q: What happens if I import an XLS with mixed statuses (some Shipped, some Completed)?
**A:** Each order is processed independently. Shipped orders become draft quotations. Completed orders also become quotations initially, but the status change will trigger auto-confirm, delivery, and invoicing.

### Q: Can I use this module without the BigSeller API? Just XLS import?
**A:** Yes! The API connection is optional. You can use only the XLS import method and ignore the Settings > BigSeller section entirely.

### Q: What happens when an order has multiple products?
**A:** In the BigSeller XLS, each product is a separate row with the same order number. The import groups them correctly — one Sale Order is created with multiple order lines (one per product).

### Q: Can I undo an automatic action (e.g., undo a confirmed delivery)?
**A:** Odoo's standard reversal processes apply. For deliveries, you can create a Return. For invoices, you can create a Credit Note. For sale order confirmation, there is no undo — you would need to cancel and re-create.

### Q: The API sync ran but no orders were updated. Why?
**A:** The API sync only updates **existing orders** in Odoo. If the orders from BigSeller were never imported via XLS first, the sync has nothing to update. Import the orders via XLS first, then the sync will keep them updated.

---

## 15. If Something Changes in the Future — What to Tell the Developer

### "BigSeller changed their XLS export format"

Tell the developer:
> "BigSeller changed their export columns. Please open the new XLS file, check the column positions, and update the column numbers in `models/bigseller_sale.py` (the COL_ constants at the top of the file)."

Provide: A sample of the new XLS file.

---

### "We need to import a new status (e.g., 'Returned')"

Tell the developer:
> "We need to add a new status called 'Returned' to the marketplace status list. It should trigger [describe what Odoo should do when this status is received — e.g., create a return/refund]."

Provide: The exact status name as it appears in BigSeller.

---

### "We're adding a new marketplace (e.g., TikTok Shop)"

Tell the developer:
> "We're connecting a new marketplace called 'TikTok Shop' to BigSeller. We need a new Sale Order Type for it. The store nickname in BigSeller is '[exact name]'."

Then in Odoo:
1. Create a new **Sale Order Type** with the exact store nickname
2. Fill in all required fields (team, warehouse, salesperson, etc.)

No code changes needed — the import works with any marketplace as long as the Sale Order Type is configured.

---

### "The automatic actions should change (e.g., don't auto-create invoices)"

Tell the developer:
> "When the status changes to 'Completed', we no longer want Odoo to automatically create and post the invoice. Just confirm the SO and delivery."

Provide: The exact status and what Odoo should or should not do.

---

### "We need a new field on the Sale Order from BigSeller"

Tell the developer:
> "We need to capture [field name] from BigSeller. In the XLS file, it's in column [letter/number]. It should appear on the Sale Order form in the Marketplace section."

Provide: A sample XLS file with the column highlighted.

---

### "The session cookie keeps expiring too fast"

Tell the developer:
> "The BigSeller session expires every [X hours]. Can we increase the cookie lifetime or automate the login?"

Note: This is a BigSeller platform limitation, not an Odoo issue. The developer may not be able to change it, but they can explore browser automation options.

---

### "We want to push status updates FROM Odoo back TO BigSeller"

Tell the developer:
> "When we confirm an order in Odoo, we want to update the status in BigSeller too (bidirectional sync). The BigSeller endpoint for this needs to be discovered — check their website's network traffic when manually changing an order status."

---

## 16. Troubleshooting — Common Problems and Solutions

| Problem | Likely Cause | Solution |
|---|---|---|
| "Product not found" error during import | The SKU from BigSeller doesn't exist as a product in Odoo | Create the product in Inventory > Products with the correct Internal Reference |
| "Sale Order Type is not configured" error | The Store Nickname from the XLS doesn't match any Order Type | Create a Sale Order Type with the exact store nickname from column L |
| "Sales Team is not available" error | The team name on the Order Type doesn't exist | Create the Sales Team in Sales > Configuration > Sales Teams |
| Marketplace group not visible on Sale Order | The order has no marketplace data | This order was not imported from BigSeller, or the XLS had an empty marketplace column |
| Settings page shows server error | A technical issue with field types | Contact the developer with the exact error message |
| "Test Connection" fails | Session cookie is expired or invalid | Log into bigseller.com again and paste fresh cookies |
| Auto sync not running | The scheduled action is inactive | Go to Settings > Technical > Scheduled Actions > find "BigSeller: Sync Orders" > check Active |
| Orders imported but not confirmed | This is by design — orders start as Quotations | Status change to Shipped/Completed will auto-confirm. Or confirm manually. |
| Invoice was not created automatically | Order status didn't reach "Completed" | Check the MP Status tab — the order may still be "Shipped". Invoice is only created at "Completed". |
| Delivery not validated automatically | Products may be out of stock | Check Inventory > Operations > Delivery Orders for errors |

---

## 17. User Permission (Security Group)

The module creates a security group called **"BigSeller Order V1"**. Only users in this group can see and use the BigSeller import menu.

### How to give a user access:

1. Go to **Settings > Users & Companies > Users**
2. Select the user
3. Click **Edit**
4. Scroll down to the **"Other"** section (or look for extra permissions)
5. Check the box for **"BigSeller Order V1"**
6. Click **Save**

### Who needs access:

| Role | Needs access? |
|---|---|
| Operations / Order Manager | Yes — they run the daily imports |
| Warehouse Staff | No — they just process deliveries as usual |
| Accountant | No — invoices appear automatically |
| Admin | Yes — they configure settings and manage users |
| Sales Team | Maybe — if they need to view marketplace status on orders |

> **Note:** Even without the BigSeller group, regular users can still **see** the Marketplace group and MP Status tab on sale orders. The security group only controls access to the **Import wizard** menu item.

---

## 18. Quick Reference Card

### Daily Operations

| Task | Where | Steps |
|---|---|---|
| Import orders from BigSeller | Sales > Orders > Import BigSeller Sale Order V1 | Upload XLS → Click Import |
| Check order marketplace status | Open any Sale Order form | Look at Marketplace group + MP Status tab |
| Run manual API sync | Settings > Sales > BigSeller | Click "Sync Now" button |
| Refresh session cookie | Settings > Sales > BigSeller | Paste new cookie → Save → Test Connection |

### Monthly / As-Needed Tasks

| Task | Where | Steps |
|---|---|---|
| Add new product (SKU) | Inventory > Products | Create product → Set Internal Reference to BigSeller SKU |
| Add new marketplace store | Sales > Configuration > Order Types | Create Order Type with exact store nickname |
| Handle returned goods (Scenario 3 cancel) | Inventory > Operations | Create Return picking + Credit Note |
| Check sync history | Settings > Technical > Scheduled Actions | View "BigSeller: Sync Orders" log |
| Give user access | Settings > Users | Edit user → Check "BigSeller Order V1" group |

### Status Quick Reference

| If BigSeller shows... | Odoo will... |
|---|---|
| New | Create Quotation (draft) |
| Shipped / To Pickup | Confirm SO + Validate Delivery |
| Completed | Create + Post Invoice |
| Canceled | Cancel SO (3 scenarios based on warehouse state) |
| In Process / Platform Processing / Retry Ship / Voided | Do nothing (informational only) |

---

*Document prepared by RSS for TA-TO project. Last updated: April 2026.*
