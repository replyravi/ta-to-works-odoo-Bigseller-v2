# -*- coding: utf-8 -*-
# RSS – BigSeller Order Import V1 for TA-TO (Phase 2)
#
# XLS importer wizard. Field-mapping rules are driven by sale.order.type:
# Customer / Invoice / Payment Terms / Warehouse / Sales Team / Salesperson /
# Fiscal Position / Pricelist / Source / Company are all read from the SO Type
# resolved via the marketplace name (Lazada / Shopee / TikTok). Receiver
# address is built from the BigSeller XLS columns.
#
# Products are looked up by barcode and are NEVER auto-created — an order
# whose SKU does not exist in Odoo is skipped and recorded in the import
# report email.

import logging
import tempfile
import binascii
import xlrd
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError
from odoo import models, fields, exceptions, api, _

_logger = logging.getLogger(__name__)

try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')

# ── BigSeller XLS column indices ──────────────────────────────────────────────
COL_ORDER_NO        = 0
COL_ORDER_STATUS    = 7
COL_MARKETPLACE     = 9
COL_STORE_NICK      = 11
COL_BUYER           = 13
COL_RECEIVER_NAME   = 16
COL_PHONE           = 17
COL_ZIP             = 18
COL_COUNTRY         = 19
COL_STATE           = 20
COL_CITY            = 21
COL_STREET          = 24
COL_SKU             = 25
COL_QUANTITY        = 32
COL_PRICE           = 33
COL_ORIG_PRICE      = 35
COL_BUYER_LOGISTICS = 54
COL_SHIP_OPTION     = 55
COL_TRACKING        = 57
COL_SELLER_S_DISC   = 60
COL_SELLER_DISC     = 66
COL_STORE_VOUCHER   = 69
COL_ORDER_TIME      = 71
COL_SHIPPED_TIME    = 77
COL_CANCEL_REASON   = 81

PROCESS_STATUSES = ('Shipped', 'Canceled', 'Completed')
CANCEL_STATUS    = 'Canceled'

XLS_STATUS_MAP = {
    'Shipped':             'shipped',
    'Completed':           'completed',
    'Canceled':            'canceled',
    'Cancelled':           'canceled',
    'New':                 'new',
    'In Process':          'in_process',
    'Platform Processing': 'platform_processing',
    'To Pickup':           'to_pickup',
    'Retry Ship':          'retry_ship',
    'Voided':              'voided',
}


class GenBigsellerSaleV1(models.TransientModel):
    _name        = "gen.bigseller.sale.v1"
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _description = "Import BigSeller Sale Order V1"

    file      = fields.Binary('File')
    file_name = fields.Char('File Name')

    # ── helpers ───────────────────────────────────────────────────────────────

    def _cell(self, row, idx):
        val = row[idx].value
        if isinstance(val, float):
            return str(int(val)) if val == int(val) else str(val)
        return str(val).strip() if val else ''

    def _parse_date(self, raw):
        if not raw:
            return False
        raw = raw.strip()
        try:
            dt = datetime.strptime(raw, "%d %b %Y %H:%M") - timedelta(hours=7)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            raise ValidationError(
                _('Wrong date format "%s". Expected "DD Mon YYYY HH:MM".') % raw)

    def _carrier_fallback_product_id(self):
        """Resolve the product.product to use when auto-creating a carrier.

        Priority:
        1. Settings parameter `bigseller.carrier_product_id`.
        2. Product whose default_code = 'DELIVERY'.
        3. Falsy → caller must handle (carrier creation is then skipped).
        """
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param('bigseller.carrier_product_id', '')
        if raw:
            try:
                pid = int(raw)
                if self.env['product.product'].browse(pid).exists():
                    return pid
            except (TypeError, ValueError):
                pass
        fallback = self.env['product.product'].search(
            [('default_code', '=', 'DELIVERY')], limit=1)
        return fallback.id if fallback else False

    # ── finders ───────────────────────────────────────────────────────────────

    def find_company(self, name):
        obj = self.env['res.company']
        rec = obj.search([('name', '=', name)], limit=1)
        return rec if rec else obj.create({'name': name})

    def find_partner(self, name):
        obj = self.env['res.partner']
        rec = obj.search([('name', '=', name), ('is_company', '=', True)], limit=1)
        return rec if rec else obj.create({'name': name, 'is_company': True})

    def find_delivery_address(self, name, parent_partner, phone=False, zip=False,
                              city=False, state=False, country=False, street=False):
        obj = self.env['res.partner']
        rec = obj.search([
            ('name', '=', name),
            ('type', '=', 'delivery'),
            ('parent_id', '=', parent_partner.id),
        ], limit=1)
        if rec:
            return rec

        country_id = self.env['res.country'].search(
            [('name', '=', country)], limit=1) if country else False
        state_id = self.env['res.country.state'].search(
            [('name', '=', state)], limit=1) if state else False

        return obj.create({
            'name':       name,
            'parent_id':  parent_partner.id,
            'type':       'delivery',
            'street':     street or False,
            'phone':      phone or False,
            'zip':        zip or False,
            'city':       city or False,
            'state_id':   state_id.id if state_id else False,
            'country_id': country_id.id if country_id else False,
        })

    def find_delivery_method(self, name):
        if not name:
            return self.env['delivery.carrier'].browse()
        carrier = self.env['delivery.carrier'].search(
            [('name', '=', name)], limit=1)
        if carrier:
            return carrier
        product_id = self._carrier_fallback_product_id()
        if not product_id:
            _logger.warning(
                'Cannot auto-create delivery carrier "%s": no carrier product '
                'configured. Set Settings → BigSeller → Carrier Product or '
                'create a product with default_code=DELIVERY.', name)
            return self.env['delivery.carrier'].browse()
        return self.env['delivery.carrier'].create({
            'name':          name,
            'delivery_type': 'fixed',
            'fixed_price':   0.0,
            'product_id':    product_id,
        })

    def find_sale_team(self, name):
        rec = self.env['crm.team'].search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" Sale Team is not available.') % name)

    def find_user(self, name):
        rec = self.env['res.users'].search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" User is not available.') % name)

    def find_fiscal_position(self, name):
        rec = self.env['account.fiscal.position'].search(
            [('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" Fiscal Position is not available.') % name)

    def find_currency(self, name):
        rec = self.env['product.pricelist'].search(
            [('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" Pricelist is not available.') % name)

    def find_payment_term(self, name):
        rec = self.env['account.payment.term'].search(
            [('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" Payment Term is not available.') % name)

    def find_source(self, name):
        rec = self.env['utm.source'].search([('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" Source is not available.') % name)

    def find_warehouse(self, name):
        rec = self.env['stock.warehouse'].search(
            [('name', '=', name)], limit=1)
        if rec:
            return rec
        raise ValidationError(_('"%s" Warehouse is not available.') % name)

    def find_route(self, name):
        if not name:
            return self.env['stock.route'].browse()
        return self.env['stock.route'].search([('name', '=', name)], limit=1)

    def find_cancel_reason(self, name):
        if not name:
            return False
        if 'sale.order.reason' not in self.env:
            return False
        obj = self.env['sale.order.reason']
        rec = obj.search([('name', '=', name)], limit=1)
        return rec if rec else obj.create({'name': name})

    def find_order_type(self, name):
        """Resolve a sale.order.type by marketplace name (e.g. 'Lazada')."""
        if 'sale.order.type' not in self.env:
            _logger.warning(
                'sale_order_type module not installed — skipping "%s"', name)
            return False
        obj = self.env['sale.order.type']
        rec = obj.search([('name', 'ilike', name)], limit=1)
        if not rec:
            raise ValidationError(
                _('Sale Order Type "%s" is not configured in Odoo.\n'
                  'Please create it under Sales → Configuration → Order '
                  'Types.') % name)
        required = {
            'sale_team_id':       'Sales Team',
            'user_id':            'Salesperson',
            'fiscal_position_id': 'Fiscal Position',
            'pricelist_id':       'Pricelist',
            'warehouse_id':       'Warehouse',
        }
        missing = [label for f, label in required.items() if not rec[f]]
        if missing:
            raise ValidationError(
                _('Order Type "%s" is missing required fields:\n- %s')
                % (name, '\n- '.join(missing)))
        return rec

    def find_product(self, value):
        """Lookup a product.product by barcode. NEVER creates.

        Raises ValidationError if the SKU is not found — callers catch this
        and record the failure in the import summary.
        """
        value = str(value).strip()
        rec   = self.env['product.product'].search(
            [('barcode', '=', value)], limit=1)
        if not rec:
            raise ValidationError(_('"%s" product is not found.') % value)
        return rec[0]

    # ── price calculation ─────────────────────────────────────────────────────

    def _calc_unit_price(self, marketplace, qty, price, orig_price, store_voucher):
        """Compute price_unit for a single XLS row.

        Each BigSeller XLS row encodes one unit; quantity > 1 is represented
        as repeated rows. Price formula varies per marketplace.
        """
        if marketplace == 'TikTok':
            if orig_price and store_voucher:
                return (orig_price * qty) - (store_voucher * qty)
        elif marketplace == 'Lazada':
            if price and store_voucher:
                return (price * qty) - (store_voucher * qty)
        elif marketplace == 'Shopee':
            if price:
                return price
        return price

    # ── order line helpers ────────────────────────────────────────────────────

    def make_order_line(self, values, sale_id):
        """Create a fresh order line — first occurrence of (order, SKU)."""
        product = self.find_product(values['product'])

        marketplace   = values.get('marketplace', '')
        price         = float(values.get('price') or 0.0)
        orig_price    = float(values.get('original_price') or 0.0)
        store_voucher = float(values.get('store_voucher') or 0.0)
        qty           = float(values.get('quantity') or 1.0)

        price_unit = self._calc_unit_price(
            marketplace, qty, price, orig_price, store_voucher)

        self.env['sale.order.line'].create({
            'order_id':        sale_id.id,
            'product_id':      product.id,
            'product_uom_qty': qty,
            'price_unit':      price_unit,
        })

    def update_order_line(self, line, values):
        """Subsequent rows for the same (order, SKU): accumulate qty."""
        marketplace   = values.get('marketplace', '')
        price         = float(values.get('price') or 0.0)
        orig_price    = float(values.get('original_price') or 0.0)
        store_voucher = float(values.get('store_voucher') or 0.0)
        qty           = float(values.get('quantity') or 1.0)

        price_unit = self._calc_unit_price(
            marketplace, qty, price, orig_price, store_voucher)

        line.write({
            'product_uom_qty': line.product_uom_qty + qty,
            'price_unit':      price_unit,
        })

    # ── sale order logic ──────────────────────────────────────────────────────

    def make_sale(self, values):
        """Session-aware import logic.

        Confirmed SO (state='sale'):
            mp_status sync only — lines are never touched.

        Existing SO (draft/cancel):
            · SAME session  → SKU on SO → update_order_line
                              SKU not on SO → make_order_line
            · OTHER session → wipe ALL lines + recreate from this row.

        Brand-new SO:
            Create SO from SO-Type-driven mapping + first order line.
        """
        order_name    = values.get('order', '').strip()
        order_status  = values.get('state', '')
        session_id    = values.get('import_session_id', '')
        is_cancel     = (order_status == CANCEL_STATUS)
        state         = 'cancel' if is_cancel else 'draft'
        sku           = str(values.get('product', '')).strip()
        mp_status_key = XLS_STATUS_MAP.get(order_status, 'new')

        if not order_name:
            raise ValidationError(
                _("Order number is missing in the import file."))

        sale_obj      = self.env['sale.order']
        cancel_reason = self.find_cancel_reason(values.get('cancel_reason'))

        existing = sale_obj.search([('name', '=', order_name)], limit=1)
        if existing:
            # ── Confirmed SO: never touch lines ───────────────────────────────
            if existing.state == 'sale':
                return existing, 'ignored'

            # ── Draft / cancel: sync status fields ────────────────────────────
            if is_cancel and existing.state != 'cancel':
                existing.state = 'cancel'
                if cancel_reason:
                    existing.cancel_reason_id = cancel_reason.id

            # ── Session check: wipe lines when session changes ────────────────
            so_session = existing.import_session_id or ''
            if so_session != session_id:
                existing.order_line.unlink()
                existing.import_session_id = session_id

            matching_line = self.env['sale.order.line'].search([
                ('order_id', '=', existing.id),
                ('product_id.barcode', '=', sku),
            ], limit=1)
            if matching_line:
                self.update_order_line(matching_line, values)
            else:
                self.make_order_line(values, existing)

            return existing, 'updated'

        # ── Brand-new SO ──────────────────────────────────────────────────────
        order_type = self.find_order_type(values['marketplace'])
        company_id = partner_id = team_id = user_id = fiscal_id = False
        pricelist_id = payment_term_id = source_id = warehouse_id = False
        if order_type:
            company_id      = self.find_company(order_type.company_id.name)
            partner_id      = self.find_partner(order_type.contact_id.name)
            payment_term_id = self.find_payment_term(
                order_type.payment_term_id.name)
            team_id         = self.find_sale_team(order_type.sale_team_id.name)
            user_id         = self.find_user(order_type.user_id.name)
            fiscal_id       = self.find_fiscal_position(
                order_type.fiscal_position_id.name)
            pricelist_id    = self.find_currency(order_type.pricelist_id.name)
            source_id       = (self.find_source(order_type.utm_source_id.name)
                               if order_type.utm_source_id else False)
            warehouse_id    = self.find_warehouse(order_type.warehouse_id.name)

        carrier_id = (self.find_delivery_method(values.get('buyer_logistics'))
                      if not is_cancel
                      else self.env['delivery.carrier'].browse())

        receiver_name = values.get('customer_name') or values.get('buyer', '')
        delivery_partner = False
        if receiver_name and partner_id:
            delivery_partner = self.find_delivery_address(
                receiver_name, partner_id,
                phone=values.get('phone', ''),
                zip=values.get('zip', ''),
                city=values.get('city', ''),
                state=values.get('state_name', ''),
                country=values.get('country', ''),
                street=values.get('street', ''),
            )

        sale_id = sale_obj.create({
            'name':                     order_name,
            'client_order_ref':         order_name,
            'company_id':               company_id.id if company_id else False,
            'partner_id':               (delivery_partner.id if delivery_partner
                                         else (partner_id.id if partner_id else False)),
            'partner_invoice_id':       partner_id.id if partner_id else False,
            'partner_shipping_id':      (delivery_partner.id if delivery_partner
                                         else (partner_id.id if partner_id else False)),
            'team_id':                  team_id.id if team_id else False,
            'user_id':                  user_id.id if user_id else False,
            'fiscal_position_id':       fiscal_id.id if fiscal_id else False,
            'pricelist_id':             pricelist_id.id if pricelist_id else False,
            'payment_term_id':          payment_term_id.id if payment_term_id else False,
            'source_id':                source_id.id if source_id else False,
            'warehouse_id':             warehouse_id.id if warehouse_id else False,
            'type_id':                  order_type.id if order_type else False,
            'carrier_id':               carrier_id.id if carrier_id else False,
            'date_order':               values.get('date') or False,
            'commitment_date':          (values.get('commitment_date')
                                         if not is_cancel else False),
            'tracking_reference':       values.get('tracking_reference', ''),
            'cancel_reason_id':         cancel_reason.id if cancel_reason else False,
            'state':                    state,
            'buyer_designed_logistics': values.get('buyer_logistics', ''),
            'mp_marketplace':           values.get('marketplace', ''),
            'mp_status':                mp_status_key,
            'mp_last_update':           fields.Datetime.now(),
            'import_session_id':        session_id,
        })

        self.env['mp.status.history'].create({
            'sale_order_id':    sale_id.id,
            'marketplace':      values.get('marketplace', ''),
            'bigseller_status': mp_status_key,
            'mp_status':        order_status,
            'odoo_action':      ('Created Quotation' if not is_cancel
                                 else 'Cancelled SO'),
            'notes':            'Initial import via XLS',
        })

        self.make_order_line(values, sale_id)
        return sale_id, 'created'

    # ── main import ───────────────────────────────────────────────────────────

    def import_sale(self):
        if not self.file:
            raise UserError(_("Please upload a BigSeller XLS file."))

        # One session ID per file upload. SOs touched in this batch are stamped
        # with this value. On re-import, any SO whose stored session ID differs
        # has its lines wiped + recreated from the new file.
        import_session_id = fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        try:
            fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xls")
            fp.write(binascii.a2b_base64(self.file))
            fp.seek(0)
            wb = xlrd.open_workbook(fp.name)
            ws = wb.sheet_by_index(0)
        except Exception as e:
            raise exceptions.ValidationError(
                _("Invalid XLS file: %s") % str(e))

        sale_ids        = []
        return_sale_ids = []
        summary = {
            'total_rows': 0,
            'created':    0,
            'updated':    0,
            'skipped':    0,
            'cancelled':  0,
            'errors':     [],
            'by_status':  {},
            'by_market':  {},
        }

        for row_no in range(1, ws.nrows):
            row    = ws.row(row_no)
            status = self._cell(row, COL_ORDER_STATUS)

            if not status or status == 'Order Status':
                summary['skipped'] += 1
                continue

            summary['total_rows'] += 1
            summary['by_status'][status] = (
                summary['by_status'].get(status, 0) + 1)

            order_no        = self._cell(row, COL_ORDER_NO)
            marketplace     = self._cell(row, COL_MARKETPLACE)
            store_nickname  = self._cell(row, COL_STORE_NICK)
            buyer           = self._cell(row, COL_BUYER)
            customer_name   = self._cell(row, COL_RECEIVER_NAME)
            phone           = self._cell(row, COL_PHONE)
            zip_code        = self._cell(row, COL_ZIP)
            country         = self._cell(row, COL_COUNTRY)
            state_name      = self._cell(row, COL_STATE)
            city            = self._cell(row, COL_CITY)
            street          = self._cell(row, COL_STREET)
            sku             = self._cell(row, COL_SKU)
            qty_raw         = self._cell(row, COL_QUANTITY)
            price_raw       = self._cell(row, COL_PRICE)
            orig_raw        = self._cell(row, COL_ORIG_PRICE)
            buyer_logistics = self._cell(row, COL_BUYER_LOGISTICS)
            carrier         = self._cell(row, COL_SHIP_OPTION)
            tracking        = self._cell(row, COL_TRACKING)
            seller_s_disc   = self._cell(row, COL_SELLER_S_DISC)
            seller_disc     = self._cell(row, COL_SELLER_DISC)
            store_voucher   = self._cell(row, COL_STORE_VOUCHER)
            order_time      = self._cell(row, COL_ORDER_TIME)
            shipped_time    = self._cell(row, COL_SHIPPED_TIME)
            cancel_rsn      = self._cell(row, COL_CANCEL_REASON)

            summary['by_market'][marketplace] = (
                summary['by_market'].get(marketplace, 0) + 1)

            order_date = self._parse_date(order_time)
            if not order_date:
                summary['errors'].append((order_no, _('Missing order date')))
                summary['skipped'] += 1
                continue

            commitment_date = (self._parse_date(shipped_time)
                               if status != CANCEL_STATUS else False)
            if status == CANCEL_STATUS:
                summary['cancelled'] += 1

            try:
                price      = float(price_raw) if price_raw else 0.0
                orig_price = float(orig_raw)  if orig_raw  else 0.0
                discount   = (round((orig_price - price) / orig_price * 100, 2)
                              if orig_price > 0 else 0.0)
            except Exception:
                price = orig_price = discount = 0.0

            values = {
                'order':              order_no,
                'state':              status,
                'marketplace':        marketplace,
                'store_nickname':     store_nickname,
                'buyer':              buyer,
                'customer_name':      customer_name,
                'phone':              phone,
                'zip':                zip_code,
                'state_name':         state_name,
                'city':               city,
                'street':             street,
                'country':            country,
                'product':            sku,
                'quantity':           float(qty_raw) if qty_raw else 1.0,
                'price':              price,
                'original_price':     orig_price,
                'discount':           discount,
                'seller_s_disc':      seller_s_disc,
                'seller_disc':        seller_disc,
                'store_voucher':      store_voucher,
                'buyer_logistics':    buyer_logistics,
                'carrier_id':         carrier or False,
                'tracking_reference': tracking,
                'date':               order_date,
                'commitment_date':    commitment_date,
                'cancel_reason':      cancel_rsn,
                'import_session_id':  import_session_id,
            }

            try:
                sale_id, action = self.make_sale(values)
                if sale_id:
                    if action == 'ignored':
                        summary['skipped'] += 1
                    elif sale_id.id not in return_sale_ids:
                        return_sale_ids.append(sale_id.id)
                        sale_ids.append(sale_id)
                        if action == 'created':
                            summary['created'] += 1
                        else:
                            summary['updated'] += 1
                    else:
                        summary['updated'] += 1
            except ValidationError as e:
                summary['errors'].append((order_no, str(e)))
                summary['skipped'] += 1
            except Exception as e:
                summary['errors'].append((order_no, str(e)))
                summary['skipped'] += 1

        self._send_import_report_email(summary, return_sale_ids)

        level    = 'warning' if summary['errors'] else 'success'
        headline = _('%d orders imported (%d created, %d updated, %d skipped)') % (
            summary['total_rows'],
            summary['created'],
            summary['updated'],
            summary['skipped'],
        )
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Import Complete'),
                'message': headline,
                'type':    level,
                'sticky':  True,
                'next': {
                    'type':      'ir.actions.act_window',
                    'name':      _('Sale Orders'),
                    'res_model': 'sale.order',
                    'views':     [[False, 'list'], [False, 'form']],
                    'domain':    [('id', 'in', return_sale_ids)],
                    'target':    'current',
                },
            },
        }

    # ── email report ──────────────────────────────────────────────────────────

    def _send_import_report_email(self, summary, return_sale_ids):
        """Send the import summary as an HTML email.

        Recipient is taken from Settings parameter
        `bigseller.import_report_recipient`, defaulting to laxman@ta-to.com.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        recipient = ICP.get_param(
            'bigseller.import_report_recipient', 'laxman@ta-to.com')

        status_rows = ''.join(
            '<tr><td style="padding:4px 12px 4px 0">%s</td><td>%d</td></tr>'
            % (s, c)
            for s, c in sorted(summary['by_status'].items(),
                               key=lambda x: -x[1])
        )
        market_rows = ''.join(
            '<tr><td style="padding:4px 12px 4px 0">%s</td><td>%d</td></tr>'
            % (m, c)
            for m, c in sorted(summary['by_market'].items(),
                               key=lambda x: -x[1])
        )
        error_sample = summary['errors'][:50]
        error_rows = ''.join(
            '<tr>'
            '<td style="padding:4px 12px 4px 0;color:#c0392b"><b>%s</b></td>'
            '<td style="color:#c0392b">%s</td>'
            '</tr>' % (o, r)
            for o, r in error_sample
        ) or '<tr><td colspan="2" style="color:green">None</td></tr>'
        more_errors_row = (
            '<tr><td colspan="2"><i>and %d more errors</i></td></tr>'
            % (len(summary['errors']) - 50)
        ) if len(summary['errors']) > 50 else ''

        status_color = '#27ae60' if not summary['errors'] else '#e67e22'

        body_html = """
        <div style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;">
            <div style="background:{status_color};padding:16px 24px;border-radius:6px 6px 0 0;">
                <h2 style="color:#fff;margin:0">BigSeller Import Report</h2>
                <p style="color:#fff;margin:4px 0 0;opacity:.85">Imported on {date}</p>
            </div>
            <div style="background:#f9f9f9;padding:24px;border:1px solid #e0e0e0;border-top:none;">
                <h3 style="margin-top:0">Overview</h3>
                <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e0e0e0;">
                    <tbody>
                        <tr style="background:#f0f0f0">
                            <td style="padding:8px 16px"><b>Total rows processed</b></td>
                            <td style="padding:8px 16px"><b>{total}</b></td>
                        </tr>
                        <tr>
                            <td style="padding:8px 16px;color:#27ae60">Created</td>
                            <td style="padding:8px 16px;color:#27ae60"><b>{created}</b></td>
                        </tr>
                        <tr style="background:#f0f0f0">
                            <td style="padding:8px 16px;color:#2980b9">Updated</td>
                            <td style="padding:8px 16px;color:#2980b9"><b>{updated}</b></td>
                        </tr>
                        <tr>
                            <td style="padding:8px 16px;color:#e67e22">Cancelled orders</td>
                            <td style="padding:8px 16px;color:#e67e22"><b>{cancelled}</b></td>
                        </tr>
                        <tr style="background:#f0f0f0">
                            <td style="padding:8px 16px;color:#7f8c8d">Skipped / errors</td>
                            <td style="padding:8px 16px;color:#7f8c8d"><b>{skipped}</b></td>
                        </tr>
                        <tr>
                            <td style="padding:8px 16px">Unique orders</td>
                            <td style="padding:8px 16px"><b>{unique}</b></td>
                        </tr>
                    </tbody>
                </table>
                <h3>By Order Status</h3>
                <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e0e0e0;">
                    <thead>
                        <tr style="background:#f0f0f0">
                            <th style="padding:8px 16px;text-align:left">Status</th>
                            <th style="padding:8px 16px;text-align:left">Count</th>
                        </tr>
                    </thead>
                    <tbody>{status_rows}</tbody>
                </table>
                <h3>By Marketplace</h3>
                <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e0e0e0;">
                    <thead>
                        <tr style="background:#f0f0f0">
                            <th style="padding:8px 16px;text-align:left">Marketplace</th>
                            <th style="padding:8px 16px;text-align:left">Count</th>
                        </tr>
                    </thead>
                    <tbody>{market_rows}</tbody>
                </table>
                <h3>Errors / Skipped Rows</h3>
                <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e0e0e0;">
                    <thead>
                        <tr style="background:#f0f0f0">
                            <th style="padding:8px 16px;text-align:left">Order No</th>
                            <th style="padding:8px 16px;text-align:left">Reason</th>
                        </tr>
                    </thead>
                    <tbody>{error_rows}{more_errors_row}</tbody>
                </table>
            </div>
            <div style="padding:12px 24px;font-size:12px;color:#999;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 6px 6px;">
                Automated message from Odoo &middot; BigSeller Import
            </div>
        </div>
        """.format(
            status_color=status_color,
            date=fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total=summary['total_rows'],
            created=summary['created'],
            updated=summary['updated'],
            cancelled=summary['cancelled'],
            skipped=summary['skipped'],
            unique=len(return_sale_ids),
            status_rows=status_rows,
            market_rows=market_rows,
            error_rows=error_rows,
            more_errors_row=more_errors_row,
        )

        subject = ('[BigSeller] Import Report — %d created, %d updated, '
                   '%d errors') % (
            summary['created'],
            summary['updated'],
            len(summary['errors']),
        )

        mail = self.env['mail.mail'].sudo().create({
            'subject':     subject,
            'body_html':   body_html,
            'email_to':    recipient,
            'email_from':  self.env.company.email or 'noreply@company.com',
            'auto_delete': True,
        })
        mail.send()
