# -*- coding: utf-8 -*-
"""Migration post-rebuild for vct_bigseller 18.0.7.0.0.

Applies default BigSeller settings (Carrier Product, Import Report Recipient,
Auto-Create Orders OFF) on module upgrade in Odoo 18e environments.
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _logger.info('vct_bigseller 18.0.7.0.0 migration: applying defaults...')
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.vct_bigseller import _bigseller_apply_defaults
    _bigseller_apply_defaults(env)
    _logger.info('vct_bigseller 18.0.7.0.0 migration: done.')
