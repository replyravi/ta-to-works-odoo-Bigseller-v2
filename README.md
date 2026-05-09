# RSS BigSeller Order V1 — Odoo Custom Module

> **Odoo 16 / 18 compatible** | Built by RSS for TA-TO

## What This Module Does

Bridges **BigSeller** (multi-channel e-commerce platform for Shopee, Lazada, TikTok Shop) with **Odoo ERP** for automated order management.

### Features

| Feature | Description |
|---|---|
| **XLS Import** | Upload BigSeller `.xls` export → creates Sale Orders in Odoo |
| **API Auto-Sync** | Pulls order status updates from BigSeller every 30 minutes |
| **Marketplace Tracking** | Marketplace name, MP Status, and full status history on every SO |
| **Auto Odoo Actions** | Shipped → Confirm SO + Delivery. Completed → Create Invoice. Canceled → 3 scenarios. |
| **Cancellation Handling** | 3 intelligent scenarios based on warehouse progress |
| **Settings UI** | BigSeller session cookie config, sync toggle, test connection |
| **Odoo 16 + 18** | Separate XML views for both versions, shared Python codebase |

### Order Flow

```
BigSeller (Shopee/Lazada/TikTok)
    │
    ├── Method 1: XLS Upload
    ├── Method 2: API Sync (every 30 min)
    │
    ▼
Odoo: Quotation (draft)
    │
    ├── Status: Shipped/To Pickup → Confirm SO + Validate Delivery
    ├── Status: Completed → Create + Post Invoice
    └── Status: Canceled → Cancel SO (3 scenarios)
```

## Installation

```bash
cd /path/to/odoo-16
source venv/bin/activate
python odoo-source/odoo-bin -d YOUR_DB -i rss_bigseller_order_v1 --stop-after-init
```

### Dependencies

Requires these Odoo modules to be installed first:
- `base`, `sale`, `sale_order_type`, `sale_order_type_ext`, `stock`, `delivery`, `account`

## Module Structure

```
rss_bigseller_order_v1/
├── models/
│   ├── mp_status_history.py     # Status history model (new table)
│   ├── sale_order.py            # SO extensions + status logic + cancellation
│   ├── bigseller_sale.py        # XLS import wizard
│   ├── bigseller_api.py         # BigSeller session-based API connector
│   └── res_config_settings.py   # Settings page
├── views/                       # Odoo 16 XML views
├── views_v18/                   # Odoo 18 XML views
├── security/                    # Access rules + security group
├── data/                        # Cron job definition
└── docs/                        # Full documentation
```

## Documentation

| Document | Audience |
|---|---|
| [Developer Guide (Phase 1)](docs/DEVELOPER_GUIDE_BigSeller.md) | Developers — original XLS import module |
| [Developer Guide (V1/Phase 2)](docs/DEVELOPER_GUIDE_BigSeller_V1.md) | Developers — this module, file-by-file |
| [User Guide](docs/USER_GUIDE_BigSeller_V1.md) | Functional users — how to use, configure, troubleshoot |

## Odoo 18 Compatibility

Default views are for Odoo 16. For Odoo 18, edit `__manifest__.py` and replace `views/` paths with `views_v18/` paths.

## License

LGPL-3

---

*Developed by RSS for TA-TO project — April 2026*
