# -*- coding: utf-8 -*-
import logging

from . import controllers
from . import models

_logger = logging.getLogger(__name__)


def _bigseller_post_init(*args):
    """Run by Odoo on first install of this module.

    Signature differs between Odoo versions:
      - Odoo 16: post_init_hook(cr, registry)
      - Odoo 17+: post_init_hook(env)
    We handle both.
    """
    if len(args) == 2:
        cr, _registry = args
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr, SUPERUSER_ID, {})
    else:
        env = args[0]
    _bigseller_apply_defaults(env)


def _bigseller_apply_defaults(env):
    """Idempotently apply the BigSeller default settings.

    Called from:
      - post_init_hook (first install)
      - migrations/<ver>/post-rebuild.py (upgrade to 0.7+)

    Each step checks whether the value is already set so re-running this on
    staging / production never overrides a manually configured value.
    """
    ICP = env['ir.config_parameter'].sudo()

    # 1) Carrier Product — pick a sensible default if none is configured.
    if not ICP.get_param('bigseller.carrier_product_id'):
        product = _bigseller_pick_carrier_product(env)
        if product:
            ICP.set_param('bigseller.carrier_product_id', str(product.id))
            _logger.info(
                'BigSeller defaults: carrier_product_id set to %s (id=%s).',
                product.display_name, product.id)
        else:
            _logger.warning(
                'BigSeller defaults: no carrier product configured and no '
                'sensible candidate found. Please set Settings -> BigSeller '
                '-> Carrier Product before importing orders with new carriers.')

    # 2) Import Report Recipient — default to laxman@ta-to.com if empty.
    if not ICP.get_param('bigseller.import_report_recipient'):
        ICP.set_param('bigseller.import_report_recipient', 'laxman@ta-to.com')
        _logger.info(
            'BigSeller defaults: import_report_recipient set to '
            'laxman@ta-to.com.')

    # 3) Auto-Create New Orders — force OFF on first install / upgrade.
    if ICP.get_param('bigseller.auto_create_orders') in (None, False, ''):
        ICP.set_param('bigseller.auto_create_orders', 'False')
        _logger.info(
            'BigSeller defaults: auto_create_orders defaulted to False '
            '(status-only mode).')

    # 4) Audit for leftover duplicate platform_order_ids.
    _bigseller_audit_duplicates(env)


def _bigseller_pick_carrier_product(env):
    """Find or create a product to back BigSeller-auto-created carriers."""
    Product = env['product.product'].sudo()
    candidates = [
        [('default_code', '=', 'BIGSELLER_SHIP')],
        [('detailed_type', '=', 'service'), ('name', 'ilike', 'delivery charges')],
        [('detailed_type', '=', 'service'), ('name', 'ilike', 'deliver')],
    ]
    for domain in candidates:
        product = Product.search(domain, limit=1)
        if product:
            return product
    try:
        return Product.create({
            'name': 'BigSeller Delivery Charges',
            'default_code': 'BIGSELLER_SHIP',
            'detailed_type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
            'list_price': 0.0,
        })
    except Exception as e:
        _logger.warning(
            'BigSeller defaults: could not auto-create a carrier product '
            '(%s). Please configure one manually.', e)
        return False


def _bigseller_audit_duplicates(env):
    """Log leftover duplicate sale_order rows that share a BigSeller ID."""
    env.cr.execute("""
        SELECT bigseller_platform_order_id, COUNT(*)
        FROM sale_order
        WHERE bigseller_platform_order_id IS NOT NULL
        GROUP BY bigseller_platform_order_id
        HAVING COUNT(*) > 1
    """)
    dupes = env.cr.fetchall()
    if dupes:
        _logger.warning(
            'BigSeller audit: %s BigSeller order ID(s) appear on more than '
            'one Sale Order. Clean them up (SET bigseller_platform_order_id = '
            'NULL on duplicates) before the SQL unique constraint can install.',
            len(dupes))
        for pid, count in dupes:
            _logger.warning(
                '  duplicate platform_order_id=%s appears %s times.',
                pid, count)
    else:
        _logger.info('BigSeller audit: no duplicate platform_order_id rows.')
