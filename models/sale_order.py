# -*- coding: utf-8 -*-
import re
import logging
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .mp_status_history import BIGSELLER_STATUS_SELECTION

_logger = logging.getLogger(__name__)

# Allowlist: only orders from these BigSeller shops are imported.
# Key = Shop ID (extracted from shopName parentheses), Value = SO Type name.
SHOP_ID_TO_ORDER_TYPE = {
    '1386965355': 'MP: Shopee',           # ContactsDirect Shopee
    '100800160369': 'MP: Lazada',         # ContactsDirect Lazada
    '101414768012': 'MP: Lazada2',        # TA-TO.COM Lazada
    '7494189457190716861': 'MP: TikTok',  # TIKTOK TA-TO.com
}

_SHOP_ID_RE = re.compile(r'\((\d+)\)\s*$')


def _extract_shop_id(shop_name):
    """Extract the numeric Shop ID from a BigSeller shopName string.

    E.g. "ContactsDirect Shopee(1386965355)" -> "1386965355"
    """
    m = _SHOP_ID_RE.search(shop_name or '')
    return m.group(1) if m else ''


STATUS_ACTION_MAP = {
    'new': 'Created Quotation',
    'in_process': None,
    'platform_processing': None,
    'to_pickup': 'Confirmed SO + Confirm Delivery',
    'retry_ship': None,
    'shipped': 'Confirmed SO + Confirm Delivery',
    'completed': 'Created Invoice + Posted',
    'canceled': 'Cancelled SO',
    'voided': None,
}


class SaleOrderBigSellerV1(models.Model):
    _inherit = 'sale.order'

    buyer_designed_logistics = fields.Char(string='Buyer Designed Logistics')
    mp_marketplace = fields.Char(string='Marketplace', tracking=True)
    mp_status = fields.Selection(
        BIGSELLER_STATUS_SELECTION, string='MP Status',
        tracking=True, copy=False)
    mp_last_update = fields.Datetime(
        string='MP Last Update', copy=False, tracking=True)
    mp_status_history_ids = fields.One2many(
        'mp.status.history', 'sale_order_id',
        string='MP Status History')
    bigseller_order_id = fields.Char(
        string='BigSeller ID', copy=False, index=True,
        help='Internal BigSeller order ID for API linking')
    bigseller_shop_name = fields.Char(
        string='BigSeller Shop', copy=False)
    bigseller_platform_order_id = fields.Char(
        string='Platform Order ID', copy=False, index=True)
    import_session_id = fields.Char(
        string='Import Session ID',
        copy=False,
        help='Tracks which import batch last wrote lines to this order.')

    _sql_constraints = [
        ('bigseller_platform_order_id_uniq',
         'unique(bigseller_platform_order_id)',
         'A Sale Order with this BigSeller Platform Order ID already exists.'),
    ]

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def action_update_mp_status(self, new_status, mp_status_text='', notes=''):
        """Update marketplace status and trigger the corresponding ODOO action.

        :param new_status: selection key from BIGSELLER_STATUS_SELECTION
        :param mp_status_text: freeform marketplace-specific status text
        :param notes: optional notes for the history record
        """
        self.ensure_one()
        odoo_action = STATUS_ACTION_MAP.get(new_status)

        self.env['mp.status.history'].create({
            'sale_order_id': self.id,
            'marketplace': self.mp_marketplace or '',
            'bigseller_status': new_status,
            'mp_status': mp_status_text or dict(BIGSELLER_STATUS_SELECTION).get(new_status, ''),
            'odoo_action': odoo_action or 'No action',
            'notes': notes,
        })

        self.write({
            'mp_status': new_status,
            'mp_last_update': fields.Datetime.now(),
        })

        if new_status in ('to_pickup', 'shipped'):
            self._mp_confirm_and_deliver()
        elif new_status == 'completed':
            self._mp_create_invoice()
        elif new_status == 'canceled':
            self.action_cancel_mp_order()

    def _mp_confirm_and_deliver(self):
        """Confirm quotation → SO and validate deliveries if possible."""
        self.ensure_one()
        if self.state == 'draft':
            try:
                self.action_confirm()
            except Exception as e:
                _logger.warning('Could not confirm SO %s: %s', self.name, e)
                return
        for picking in self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
            try:
                picking.action_assign()
                for move_line in picking.move_line_ids:
                    move_line.qty_done = move_line.reserved_uom_qty
                picking.button_validate()
            except Exception as e:
                _logger.warning('Could not validate picking %s: %s', picking.name, e)

    def _mp_create_invoice(self):
        """Create and post invoice when status reaches Completed."""
        self.ensure_one()
        if self.state == 'draft':
            self._mp_confirm_and_deliver()
        if self.invoice_status != 'to invoice':
            return
        try:
            invoice = self._create_invoices()
            for inv in invoice:
                inv.action_post()
        except Exception as e:
            _logger.warning('Could not create invoice for SO %s: %s', self.name, e)

    # ------------------------------------------------------------------
    # Cancellation scenarios (Issue-101)
    # ------------------------------------------------------------------

    def action_cancel_mp_order(self):
        """Handle 3 cancellation scenarios based on picking state.

        Scenario 1: Not yet picked → Cancel SO + deliveries
        Scenario 2: Picked, not shipped → Reverse pick step 1, then cancel
        Scenario 3: Already shipped → Mark as return flow (manual credit note)
        """
        self.ensure_one()
        pickings = self.picking_ids

        done_pickings = pickings.filtered(lambda p: p.state == 'done')
        assigned_pickings = pickings.filtered(lambda p: p.state == 'assigned')

        if done_pickings:
            # Scenario 3: goods already shipped
            self._mp_log_history(
                'canceled',
                'Return flow – manual credit note required',
                'Goods already shipped. Return/refund handled manually.')
            return

        if assigned_pickings:
            # Scenario 2: picked but not shipped – reverse
            for picking in assigned_pickings:
                try:
                    picking.action_cancel()
                except Exception as e:
                    _logger.warning('Could not cancel picking %s: %s', picking.name, e)
            self._mp_log_history(
                'canceled',
                'Reversed picking + Cancelled SO',
                'Picked goods returned to stock, SO cancelled.')

        else:
            # Scenario 1: nothing picked
            self._mp_log_history(
                'canceled',
                'Cancelled SO + Deliveries',
                'No picking done yet, clean cancel.')

        # Cancel remaining non-done pickings
        for picking in pickings.filtered(lambda p: p.state not in ('done', 'cancel')):
            try:
                picking.action_cancel()
            except Exception:
                pass

        if self.state not in ('cancel', 'done'):
            try:
                self.action_cancel()
            except Exception as e:
                _logger.warning('Could not cancel SO %s: %s', self.name, e)

    def _mp_log_history(self, status, action_text, notes=''):
        """Convenience to create a status history entry."""
        self.env['mp.status.history'].create({
            'sale_order_id': self.id,
            'marketplace': self.mp_marketplace or '',
            'bigseller_status': status,
            'mp_status': dict(BIGSELLER_STATUS_SELECTION).get(status, ''),
            'odoo_action': action_text,
            'notes': notes,
        })

    # ------------------------------------------------------------------
    # BigSeller API sync helpers
    # ------------------------------------------------------------------

    # PostgreSQL advisory-lock key (stable, unique per cron entry).
    _BIGSELLER_LOCK_KEY = 8723145623897210

    def _bigseller_sync_orders(self, manual=False):
        """Cron entry point: sync orders from BigSeller API.

        Wrapped in a PostgreSQL transaction-level advisory lock so two
        overlapping cron ticks cannot both pull and create the same order
        (root cause of the Production duplicate-order incident).

        :param manual: if True, bypass sync_enabled check (Sync Now button)
        :return: dict with 'created' and 'updated' counts
        """
        self = self.sudo()
        ICP = self.env['ir.config_parameter'].sudo()

        if not manual and ICP.get_param('bigseller.sync_enabled', 'False') != 'True':
            return {'created': 0, 'updated': 0}

        # Advisory lock: try-only, no-block. If another cron tick is mid-run
        # we skip cleanly instead of stacking work.
        self.env.cr.execute(
            'SELECT pg_try_advisory_xact_lock(%s)', (self._BIGSELLER_LOCK_KEY,))
        got_lock = self.env.cr.fetchone()[0]
        if not got_lock:
            _logger.info(
                'BigSeller sync: previous run still in flight; skipping tick.')
            return {'created': 0, 'updated': 0}

        cookie = ICP.get_param('bigseller.session_cookie', '')
        base_url = ICP.get_param('bigseller.base_url', 'https://www.bigseller.com')
        if not cookie:
            ICP.set_param('bigseller.last_sync_error',
                          'No session cookie configured. Go to Settings > '
                          'BigSeller and paste your cookie.')
            return {'created': 0, 'updated': 0}

        from .bigseller_api import BigSellerClient
        client = BigSellerClient(base_url, cookie)

        if not client.test_connection():
            _logger.error('BigSeller sync: session expired or invalid.')
            ICP.set_param('bigseller.last_sync_error',
                          'Session expired or invalid. Please paste a fresh cookie.')
            return {'created': 0, 'updated': 0}

        created_count = 0
        updated_count = 0
        errors = []
        for status in ('new', 'shipped', 'completed', 'canceled'):
            try:
                c, u = self._bigseller_sync_status(client, status)
                created_count += c
                updated_count += u
            except Exception as e:
                _logger.error('BigSeller sync error for status %s: %s', status, e)
                errors.append('%s: %s' % (status, e))

        ICP.set_param('bigseller.last_sync', fields.Datetime.now())
        if errors:
            ICP.set_param('bigseller.last_sync_error', '; '.join(errors))
        else:
            ICP.set_param('bigseller.last_sync_error', '')
        _logger.info(
            'BigSeller sync complete: %d created, %d updated',
            created_count, updated_count)
        return {'created': created_count, 'updated': updated_count}

    def _bigseller_sync_status(self, client, status):
        """Fetch orders with given status from BigSeller and sync to Odoo.

        Returns (created_count, updated_count) tuple.
        """
        page = 1
        created = 0
        updated = 0
        # Default OFF: production was burned by uncontrolled creation. Must be
        # explicitly enabled in Settings → BigSeller after Staging sign-off.
        auto_create = self.env['ir.config_parameter'].sudo().get_param(
            'bigseller.auto_create_orders', 'False') == 'True'

        while True:
            data = client.get_orders(status=status, page=page, page_size=100)

            api_code = data.get('code')
            if api_code is not None and api_code != 0:
                _logger.error(
                    'BigSeller API error for status %s: code=%s msg=%s',
                    status, api_code, data.get('msg', ''))
                break

            resp_data = data.get('data') or {}
            page_data = (resp_data.get('page') or {}) if isinstance(resp_data, dict) else {}
            orders = (page_data.get('rows') or []) if isinstance(page_data, dict) else []
            if not orders:
                _logger.info(
                    'BigSeller sync status=%s: no orders returned (page=%d)',
                    status, page)
                break

            _logger.info(
                'BigSeller sync status=%s: processing %d orders (page %d)',
                status, len(orders), page)

            for bs_order in orders:
                order_no = (bs_order.get('platformOrderId') or '').strip()
                bs_id    = str(bs_order.get('id', '')).strip()
                if not order_no:
                    continue

                # Strict dedup: lookup by the BigSeller-side identifiers ONLY.
                # The previous OR-on-`name` clause was the root cause of the
                # duplicate orders in Production: Odoo's sequence overwrites
                # `name` on create, so the lookup missed and re-created the SO
                # on the next cron tick.
                domain = [('bigseller_platform_order_id', '=', order_no)]
                if bs_id:
                    domain = ['|',
                              ('bigseller_order_id', '=', bs_id),
                              ('bigseller_platform_order_id', '=', order_no)]
                existing = self.search(domain, limit=1)

                if existing:
                    bs_status = self._map_bigseller_status(
                        bs_order.get('state', status))
                    changed = False
                    if existing.mp_status != bs_status:
                        existing.action_update_mp_status(
                            bs_status,
                            notes='Auto-synced from BigSeller API')
                        changed = True
                    if bs_id and not existing.bigseller_order_id:
                        existing.write({'bigseller_order_id': bs_id})
                        changed = True
                    if changed:
                        updated += 1
                elif auto_create:
                    try:
                        new_so = self._bigseller_create_order(bs_order)
                        if new_so:
                            created += 1
                            self.env.cr.commit()
                    except Exception as e:
                        self.env.cr.rollback()
                        _logger.error(
                            'Failed to create order %s: %s', order_no, e)

            total = page_data.get('totalSize', 0) if isinstance(page_data, dict) else 0
            if page * 100 >= total:
                break
            page += 1

        return created, updated

    # ------------------------------------------------------------------
    # Auto-create Sale Orders from BigSeller API data
    # ------------------------------------------------------------------

    @staticmethod
    def _bigseller_is_allowed_shop(shop_name):
        """Return True if the order's shop is in the allowlist."""
        shop_id = _extract_shop_id(shop_name)
        return shop_id in SHOP_ID_TO_ORDER_TYPE

    def _bigseller_create_order(self, bs_order):
        """Create a new Sale Order from a BigSeller API order dict.

        Field-mapping rules (matched to the XLS importer):

        - Customer / Invoice address come from the resolved sale.order.type's
          contact_id (driven by the marketplace / Shop ID).
        - Delivery contact is built from BigSeller's receiver fields, parented
          under the Customer.
        - Products are looked up by `barcode`. If ANY line's SKU is not found
          in Odoo, the entire order is skipped (no product is auto-created).
        - Carrier is resolved from the buyer's logistics; when missing it is
          auto-created using the product configured in
          Settings → BigSeller → Carrier Product.
        - Per-marketplace price formula matches the XLS importer.
        """
        order_no = bs_order.get('platformOrderId', '')
        platform = bs_order.get('viewPlatfrom') or bs_order.get('platform', '')
        shop_name = bs_order.get('shopName', '')
        state = bs_order.get('state', 'new')
        currency_code = bs_order.get('amountUnit', 'THB')

        if not self._bigseller_is_allowed_shop(shop_name):
            _logger.info('Skipping order %s — shop "%s" not in allowlist',
                         order_no, shop_name)
            return self.browse()

        order_type = self._bigseller_resolve_order_type(platform, shop_name)
        if not order_type:
            _logger.warning(
                'Skipping order %s — no sale.order.type matched for '
                'platform="%s" shop="%s"', order_no, platform, shop_name)
            return self.browse()

        # ── Build line items first; if any SKU is missing, abort the SO. ──
        line_items, missing_skus = self._bigseller_build_lines(
            bs_order, platform)
        if missing_skus:
            _logger.warning(
                'Skipping order %s — unknown SKU(s) %s. No product will be '
                'auto-created.', order_no, ', '.join(missing_skus))
            self._bigseller_record_skipped_order(
                order_no, shop_name, platform,
                'Unknown SKU(s): %s' % ', '.join(missing_skus))
            return self.browse()
        if not line_items:
            _logger.warning(
                'Skipping order %s — no order lines could be built.', order_no)
            return self.browse()

        customer = (order_type.contact_id
                    if hasattr(order_type, 'contact_id') else False)
        if not customer:
            _logger.warning(
                'Skipping order %s — sale.order.type "%s" has no Contact '
                '(Customer). Configure it under Sales → Configuration → '
                'Order Types.', order_no, order_type.name)
            return self.browse()

        delivery_contact = self._bigseller_build_delivery_address(
            bs_order, customer)
        currency = self.env['res.currency'].search(
            [('name', '=ilike', currency_code)], limit=1)
        order_date = self._bigseller_parse_order_date(bs_order)
        carrier = self._bigseller_resolve_carrier(bs_order)

        vals = {
            'name': order_no,
            'partner_id': customer.id,
            'partner_invoice_id': customer.id,
            'partner_shipping_id': (delivery_contact.id
                                    if delivery_contact else customer.id),
            'client_order_ref': order_no,
            'mp_marketplace': platform,
            'mp_status': self._map_bigseller_status(state),
            'mp_last_update': fields.Datetime.now(),
            'buyer_designed_logistics': bs_order.get('buyerShippingCarrier', ''),
            'bigseller_order_id': str(bs_order.get('id', '')),
            'bigseller_shop_name': shop_name,
            'bigseller_platform_order_id': order_no,
            'order_line': line_items,
        }
        if carrier:
            vals['carrier_id'] = carrier.id
        if order_date:
            vals['date_order'] = order_date
        if currency:
            vals['currency_id'] = currency.id

        # SO Type fills the remaining defaults (warehouse, pricelist, payment
        # term, sales team, salesperson, source, fiscal position, company).
        self._bigseller_apply_order_type(vals, order_type)

        order = self.create(vals)

        order._mp_log_history(
            vals['mp_status'],
            'Auto-created from BigSeller API',
            'Shop: %s | Platform: %s | BS-ID: %s' % (
                shop_name, platform, bs_order.get('id', '')))

        bs_status = self._map_bigseller_status(state)
        if bs_status in ('to_pickup', 'shipped'):
            order._mp_confirm_and_deliver()
        elif bs_status == 'completed':
            order._mp_confirm_and_deliver()
            order._mp_create_invoice()
        elif bs_status == 'canceled':
            order.action_cancel_mp_order()

        _logger.info(
            'Created SO %s from BigSeller (platform=%s, status=%s)',
            order.name, platform, state)
        return order

    def _bigseller_build_lines(self, bs_order, marketplace):
        """Build (line_commands, missing_skus) for an API payload.

        Per-marketplace price formula matches `_calc_unit_price` in the XLS
        wizard: TikTok uses orig*qty - voucher*qty, Lazada uses
        price*qty - voucher*qty, Shopee uses price as-is.
        """
        Product = self.env['product.product']
        line_items = []
        missing = []
        store_voucher_total = 0.0
        try:
            store_voucher_total = float(bs_order.get('storeVoucher') or 0.0)
        except (TypeError, ValueError):
            store_voucher_total = 0.0

        items = bs_order.get('orderItemList') or []
        for item in items:
            sku = (item.get('varSku') or item.get('sku') or '').strip()
            if not sku:
                missing.append('(empty SKU)')
                continue
            product = Product.search([('barcode', '=', sku)], limit=1)
            if not product:
                missing.append(sku)
                continue
            try:
                qty = float(item.get('quantity') or 1)
            except (TypeError, ValueError):
                qty = 1.0
            price = self._bigseller_parse_price(item)
            orig_price = self._bigseller_parse_orig_price(item)
            voucher = (store_voucher_total / max(len(items), 1)
                       if store_voucher_total else 0.0)
            price_unit = self._calc_api_unit_price(
                marketplace, qty, price, orig_price, voucher)
            line_items.append((0, 0, {
                'product_id':      product.id,
                'product_uom_qty': qty,
                'price_unit':      price_unit,
                'name':            self._bigseller_build_line_name(product, item),
            }))
        return line_items, missing

    @staticmethod
    def _calc_api_unit_price(marketplace, qty, price, orig_price, voucher):
        """Mirror of GenBigsellerSaleV1._calc_unit_price for API payloads."""
        m = (marketplace or '').lower()
        if 'tiktok' in m:
            if orig_price and voucher:
                return (orig_price * qty) - (voucher * qty)
        elif 'lazada' in m:
            if price and voucher:
                return (price * qty) - (voucher * qty)
        elif 'shopee' in m:
            if price:
                return price
        return price

    @staticmethod
    def _bigseller_parse_orig_price(item):
        """Extract the original (pre-discount) price for a line."""
        for key in ('varOriginalPrice', 'originalPrice', 'varDiscountedPrice',
                    'amount'):
            val = item.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return 0.0

    def _bigseller_resolve_carrier(self, bs_order):
        """Resolve a delivery.carrier from the order's logistics info.

        Search by name first; if no carrier exists, auto-create a fixed-price
        carrier using the product configured in
        Settings → BigSeller → Carrier Product (param
        `bigseller.carrier_product_id`). Returns False if no carrier name
        is provided in the payload.
        """
        name = (bs_order.get('buyerShippingCarrier')
                or bs_order.get('shippingCarrier')
                or bs_order.get('logisticsName')
                or '').strip()
        if not name:
            return self.env['delivery.carrier'].browse()
        Carrier = self.env['delivery.carrier']
        carrier = Carrier.search([('name', '=', name)], limit=1)
        if carrier:
            return carrier

        ICP = self.env['ir.config_parameter'].sudo()
        raw_pid = ICP.get_param('bigseller.carrier_product_id', '')
        product_id = False
        if raw_pid:
            try:
                pid = int(raw_pid)
                if self.env['product.product'].browse(pid).exists():
                    product_id = pid
            except (TypeError, ValueError):
                pass
        if not product_id:
            fallback = self.env['product.product'].search(
                [('default_code', '=', 'DELIVERY')], limit=1)
            product_id = fallback.id if fallback else False
        if not product_id:
            _logger.warning(
                'Cannot auto-create carrier "%s": no Carrier Product '
                'configured. Set Settings → BigSeller → Carrier Product.',
                name)
            return Carrier.browse()
        return Carrier.create({
            'name':          name,
            'delivery_type': 'fixed',
            'fixed_price':   0.0,
            'product_id':    product_id,
        })

    def _bigseller_record_skipped_order(self, order_no, shop_name, platform,
                                        reason):
        """Persist a lightweight log entry for an order skipped due to bad
        data so the operations team can chase it.

        Uses ir.config_parameter as a rolling bucket to avoid introducing a
        new model. Latest 200 entries are kept.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        bucket = ICP.get_param('bigseller.skipped_orders', '') or ''
        line = '%s | %s | %s | %s | %s' % (
            fields.Datetime.now(), order_no, shop_name, platform, reason)
        entries = (bucket.splitlines() + [line])[-200:]
        ICP.set_param('bigseller.skipped_orders', '\n'.join(entries))

    def _bigseller_resolve_order_type(self, platform, shop_name):
        """Match BigSeller shop to a sale.order.type using the Shop ID table.

        Primary: extract Shop ID from shopName, look up in
        SHOP_ID_TO_ORDER_TYPE, then search for the exact SO Type name.
        Fallback: keyword-based search by platform name.

        Returns a sale.order.type recordset (possibly empty / False).
        """
        if 'sale.order.type' not in self.env:
            return False

        OrderType = self.env['sale.order.type']

        shop_id = _extract_shop_id(shop_name)
        type_name = SHOP_ID_TO_ORDER_TYPE.get(shop_id)
        if type_name:
            ot = OrderType.search([('name', '=', type_name)], limit=1)
            if ot:
                return ot
            _logger.warning(
                'SO Type "%s" not found for shop_id=%s, trying fallback',
                type_name, shop_id)

        platform_lower = (platform or '').lower()
        shop_lower = (shop_name or '').lower()
        keyword = ''
        if 'lazada' in platform_lower or 'lazada' in shop_lower:
            keyword = 'Lazada'
        elif 'shopee' in platform_lower or 'shopee' in shop_lower:
            keyword = 'Shopee'
        elif 'tiktok' in platform_lower or 'tiktok' in shop_lower:
            keyword = 'TikTok'
        elif platform_lower:
            keyword = platform

        if not keyword:
            return OrderType.browse()

        types = OrderType.search([('name', 'ilike', keyword)])
        if not types:
            _logger.warning(
                'No sale.order.type found for platform "%s" / shop "%s"',
                platform, shop_name)
            return OrderType.browse()

        if len(types) == 1:
            return types

        for ot in types.sorted(key=lambda t: len(t.name), reverse=True):
            type_suffix = ot.name.replace('MP:', '').strip().lower()
            if type_suffix and type_suffix in shop_lower:
                return ot

        return types.sorted(key=lambda t: len(t.name))[0]

    @staticmethod
    def _bigseller_apply_order_type(vals, order_type):
        """Merge fields from a sale.order.type into the SO vals dict."""
        if not order_type:
            return
        vals['type_id'] = order_type.id
        if order_type.warehouse_id:
            vals['warehouse_id'] = order_type.warehouse_id.id
        if order_type.pricelist_id:
            vals['pricelist_id'] = order_type.pricelist_id.id
        if order_type.fiscal_position_id:
            vals['fiscal_position_id'] = order_type.fiscal_position_id.id
        if hasattr(order_type, 'sale_team_id') and order_type.sale_team_id:
            vals['team_id'] = order_type.sale_team_id.id
        if order_type.user_id:
            vals['user_id'] = order_type.user_id.id
        if hasattr(order_type, 'utm_source_id') and order_type.utm_source_id:
            vals['source_id'] = order_type.utm_source_id.id
        if hasattr(order_type, 'company_id') and order_type.company_id:
            vals['company_id'] = order_type.company_id.id

        # contact_id → customer & invoice address. Do NOT overwrite if the
        # caller has already resolved the customer (the API path sets it
        # before calling this helper to keep delivery_id parented correctly).
        if (hasattr(order_type, 'contact_id') and order_type.contact_id
                and not vals.get('partner_id')):
            vals['partner_id'] = order_type.contact_id.id
        if (hasattr(order_type, 'contact_id') and order_type.contact_id
                and not vals.get('partner_invoice_id')):
            vals['partner_invoice_id'] = order_type.contact_id.id

        if hasattr(order_type, 'payment_term_id') and order_type.payment_term_id:
            vals['payment_term_id'] = order_type.payment_term_id.id

        # SO Type's carrier_id wins only when the API payload did not provide
        # buyerShippingCarrier (the caller leaves carrier_id unset in that
        # case).
        if (hasattr(order_type, 'carrier_id') and order_type.carrier_id
                and not vals.get('carrier_id')):
            vals['carrier_id'] = order_type.carrier_id.id

        deadline_days = 0
        if hasattr(order_type, 'delivery_deadline_days'):
            deadline_days = order_type.delivery_deadline_days or 0
        if deadline_days > 0:
            base_date = vals.get('date_order') or fields.Datetime.now()
            if isinstance(base_date, str):
                base_date = fields.Datetime.from_string(base_date)
            vals['commitment_date'] = base_date + timedelta(days=deadline_days)

    def _bigseller_build_delivery_address(self, bs_order, parent_partner):
        """Find or create a delivery contact from BigSeller receiver fields.

        Reads the receiver block (name, phone, postcode, country, state,
        city, street) from the BigSeller payload, parents the contact under
        the resolved marketplace Customer, and reuses an existing delivery
        contact if one with the same name already exists.

        Returns False when no buyer/receiver name is present.
        """
        Partner = self.env['res.partner']

        buyer_name = (
            bs_order.get('receiverName')
            or bs_order.get('contactPerson')
            or bs_order.get('buyerUsername')
            or ''
        ).strip()
        if not buyer_name or not parent_partner:
            return False

        existing = Partner.search([
            ('name', '=ilike', buyer_name),
            ('type', '=', 'delivery'),
            ('parent_id', '=', parent_partner.id),
        ], limit=1)
        if existing:
            return existing

        country_name = (bs_order.get('receiverCountry') or '').strip()
        state_name = (bs_order.get('receiverState')
                      or bs_order.get('receiverProvince')
                      or '').strip()

        country_id = (self.env['res.country'].search(
            [('name', '=', country_name)], limit=1) if country_name else False)
        state_id = (self.env['res.country.state'].search(
            [('name', '=', state_name)], limit=1) if state_name else False)

        delivery = Partner.create({
            'name':       buyer_name,
            'parent_id':  parent_partner.id,
            'type':       'delivery',
            'street':     (bs_order.get('receiverStreet')
                           or bs_order.get('receiverAddress')
                           or '') or False,
            'phone':      (bs_order.get('receiverPhone')
                           or bs_order.get('receiverMobile')
                           or '') or False,
            'zip':        (bs_order.get('receiverPostcode')
                           or bs_order.get('receiverZip')
                           or '') or False,
            'city':       (bs_order.get('receiverCity') or '') or False,
            'state_id':   state_id.id if state_id else False,
            'country_id': country_id.id if country_id else False,
            'comment':    'Delivery address from BigSeller import',
        })
        _logger.info('Created delivery contact: %s (under %s)',
                     buyer_name, parent_partner.name)
        return delivery

    @staticmethod
    def _bigseller_parse_price(item):
        """Extract the best price from an order item dict."""
        for key in ('varDiscountedPrice', 'varOriginalPrice', 'amount'):
            val = item.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return 0.0

    @staticmethod
    def _bigseller_build_line_name(product, item_data):
        """Build a descriptive order-line name from product + BigSeller item.

        Uses product display_name as base, then enriches with the BigSeller
        item description and variant attributes when available.
        """
        parts = [product.display_name or product.name]
        bs_name = (item_data.get('itemName') or item_data.get('vName') or '').strip()
        if bs_name and bs_name.lower() != (product.name or '').lower():
            parts.append(bs_name)
        attr = (item_data.get('varAttr') or '').strip()
        if attr:
            parts.append('(%s)' % attr)
        return ' - '.join(parts) if len(parts) > 1 else parts[0]

    @staticmethod
    def _bigseller_parse_order_date(bs_order):
        """Extract the real order date from BigSeller JSON.

        BigSeller provides dates as epoch-millisecond timestamps in fields
        like paidTime, orderCreateTime, createTime.  Returns a datetime
        or None if no usable date is found.
        """
        from datetime import datetime
        for key in ('paidTime', 'orderCreateTime', 'createTime', 'payTime'):
            val = bs_order.get(key)
            if val:
                try:
                    ts = int(val)
                    if ts > 1e12:
                        ts = ts / 1000
                    return datetime.utcfromtimestamp(ts)
                except (ValueError, TypeError, OSError):
                    continue
        date_str = bs_order.get('orderDate') or bs_order.get('createDate')
        if date_str and isinstance(date_str, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S'):
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        return None

    @api.model
    def _map_bigseller_status(self, raw_status):
        """Map BigSeller web status string to our selection key."""
        mapping = {
            'new': 'new',
            'in_process': 'in_process',
            'inprocess': 'in_process',
            'platform_processing': 'platform_processing',
            'to_pickup': 'to_pickup',
            'topickup': 'to_pickup',
            'retry_ship': 'retry_ship',
            'retryship': 'retry_ship',
            'shipped': 'shipped',
            'completed': 'completed',
            'canceled': 'canceled',
            'cancelled': 'canceled',
            'voided': 'voided',
        }
        return mapping.get(raw_status.lower().replace(' ', '_'), 'new')
