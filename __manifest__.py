# -*- coding: utf-8 -*-
#
# DUAL-COMPAT MANIFEST:
#   Default → Odoo 18 (staging / production) uses views_v18/
#   For local Odoo 16 testing:   ./tools/use_odoo_16.sh
#   Before every push to GitHub: ./tools/use_odoo_18.sh
#
{
    'name': 'VCT BigSeller Integration',
    'version': '18.0.7.0.0',
    'sequence': 5,
    'category': 'Sales',
    'summary': 'BigSeller marketplace order management with XLS import, API sync and status tracking',
    'description': """
VCT BigSeller Integration (Phase 1 + Phase 2) for TA-TO.

Features:
- Import BigSeller marketplace orders from XLS (Phase 1)
- Marketplace status tracking on Sale Orders
- Status history tab (One2many)
- BigSeller status mapping (New -> QTN, Shipped -> SO, Completed -> Invoice)
- 3 cancellation scenarios
- BigSeller session-based API connector for bidirectional sync
- Auto-create Sale Orders from BigSeller API (auto-sync every 2 minutes)
- JSON Import Wizard: paste BigSeller API response to create orders instantly
- Browser Auto-Sync: Tampermonkey script pushes orders to Odoo every 1 minute
- Odoo 16 / 18 dual compatibility (swap views/ <-> views_v18/ via tools/)
    """,
    'author': 'RSS',
    'website': 'https://github.com/replyravi/ta-to-works-odoo-Bigseller-v2',
    'depends': [
        'base',
        'sale_management',
        'sale_order_type',
        'sale_order_type_ext',
        'stock',
        'delivery',
        'account',
    ],
    'data': [
        'security/access_record_rule.xml',
        'security/ir.model.access.csv',
        'views_v18/bigseller_sale_wizard.xml',
        'views_v18/sale_order_view.xml',
        'views_v18/res_config_settings_view.xml',
        'data/bigseller_cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': True,
    'post_init_hook': '_bigseller_post_init',
}
