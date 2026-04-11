from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'rg5329.order.mixin']

    def _rg5329_line_tax_field(self):
        return 'taxes_id'

    def apply_rg5329_logic_manual(self):
        """Public method to manually trigger RG5329 logic"""
        self._apply_rg5329_logic()
        return True

    def apply_rg5329_manual_button(self):
        """Manual button to apply RG5329 tax"""
        try:
            _logger.info("RG5329 BUTTON: Manual button clicked for purchase order %s", self.name)
            self._apply_rg5329_logic()
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._amount_all()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Tax Applied',
                    'message': f'RG5329 tax has been applied to purchase order {self.name}. New total: ${self.amount_total:,.2f}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error("RG5329 BUTTON: Error in manual button: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Error',
                    'message': f'Error applying RG5329 tax: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def button_confirm(self):
        """Override to ensure RG5329 taxes are applied and preserved on confirmation"""
        for order in self:
            if not self.env.context.get('skip_rg5329_confirm'):
                _logger.info("RG5329: Applying logic before confirming order %s", order.name)
                if order.state in ['draft', 'sent']:
                    order._apply_rg5329_logic()
                    order._amount_all()
                    order._store_rg5329_taxes_before_confirm()

        result = super().button_confirm()

        for order in self:
            if not self.env.context.get('skip_rg5329_confirm'):
                order._restore_rg5329_taxes_after_confirm()

        return result

    def _store_rg5329_taxes_before_confirm(self):
        """Store which lines have RG5329 taxes before confirmation"""
        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase'),
        ], limit=1)

        if not rg5329_tax:
            return

        lines_with_rg5329 = [
            line.id for line in self.order_line
            if rg5329_tax.id in line.taxes_id.ids
        ]
        self.env.context = dict(self.env.context, rg5329_lines_before_confirm=lines_with_rg5329)
        _logger.debug("RG5329 STORE: Stored %d lines with RG5329 tax", len(lines_with_rg5329))

    def _restore_rg5329_taxes_after_confirm(self):
        """Restore RG5329 taxes after confirmation if they were removed"""
        lines_with_rg5329 = self.env.context.get('rg5329_lines_before_confirm', [])
        if not lines_with_rg5329:
            _logger.debug("RG5329 RESTORE: No lines to restore")
            return

        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase'),
        ], limit=1)

        if not rg5329_tax:
            _logger.warning("RG5329 RESTORE: RG5329 tax not found!")
            return

        restored_count = 0
        for line in self.order_line:
            if line.id in lines_with_rg5329 and rg5329_tax.id not in line.taxes_id.ids:
                _logger.warning("RG5329 RESTORE: Tax missing from line %s - RESTORING", line.id)
                current_tax_ids = list(line.taxes_id.ids) + [rg5329_tax.id]
                line.write({'taxes_id': [(6, 0, current_tax_ids)]})
                restored_count += 1

        if restored_count > 0:
            _logger.info("RG5329 RESTORE: ✅ Restored RG5329 tax to %d lines", restored_count)
            self._amount_all()
        else:
            _logger.debug("RG5329 RESTORE: All taxes preserved correctly")

    def _apply_rg5329_logic(self):
        """
        Apply RG5329 perception tax to purchase order lines.
        Total is calculated as amount_total minus existing RG5329 tax (avoids circular recursion).
        Eligibility and per-line add/remove logic delegated to rg5329.order.mixin.
        """
        if self.state not in ['draft', 'sent'] or self.env.context.get('applying_rg5329'):
            return True

        self.with_context(applying_rg5329=True)._amount_all()

        # Subtract existing RG5329 amount to avoid circular recursion
        rg5329_tax_amount = sum(
            tax.compute_all(
                line.price_unit, self.currency_id,
                line.product_qty, line.product_id, self.partner_id
            )['total_included'] -
            tax.compute_all(
                line.price_unit, self.currency_id,
                line.product_qty, line.product_id, self.partner_id
            )['total_excluded']
            for line in self.order_line
            for tax in line.taxes_id
            if tax.is_rg5329_perception
        )
        total = (self.amount_total or 0) - rg5329_tax_amount
        _logger.debug("RG5329: Processing purchase order %s - total $%s (excl. RG5329)",
                      self.name or 'New', total)

        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase'),
        ], limit=1)

        if not rg5329_tax:
            _logger.warning("RG5329: No RG5329 purchase tax found!")
            return False

        self._apply_rg5329_to_lines(rg5329_tax, total)
        return True

    def _force_ui_refresh(self):
        """Force UI refresh after tax changes"""
        try:
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._amount_all()
            if hasattr(self.env['bus.bus'], '_sendone'):
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id,
                    'purchase_order/rg5329_updated',
                    {'order_id': self.id}
                )
            _logger.debug("RG5329: UI refresh triggered")
        except Exception as e:
            _logger.error("RG5329: Error forcing UI refresh: %s", str(e))

    @api.onchange('partner_id')
    def _onchange_partner_rg5329_unified(self):
        """Trigger RG5329 recalculation when partner changes"""
        if self.partner_id and not self.env.context.get('skip_onchange'):
            _logger.debug("RG5329: Partner changed, triggering logic...")
            self._apply_rg5329_logic()

    def _amount_all(self):
        """Override to trigger RG5329 logic after totals are calculated"""
        result = super()._amount_all()

        if (not self.env.context.get('applying_rg5329') and
                not self.env.context.get('skip_rg5329_auto')):
            for order in self:
                if order.state in ['draft', 'sent']:
                    has_rg5329_products = any(
                        line.product_id and line.product_id.apply_rg5329
                        for line in order.order_line
                    )
                    if has_rg5329_products:
                        _logger.debug("RG5329: Amounts computed, re-checking...")
                        order.with_context(skip_rg5329_auto=True)._apply_rg5329_logic()

        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _get_stock_move_price_unit(self):
        """
        Override to ensure RG5329 taxes are present during stock move price calculation.
        """
        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase'),
        ], limit=1)

        if self.order_id and rg5329_tax:
            rg5329_tax_amount = sum(
                tax.compute_all(
                    line.price_unit, self.order_id.currency_id,
                    line.product_qty, line.product_id, self.order_id.partner_id
                )['total_included'] -
                tax.compute_all(
                    line.price_unit, self.order_id.currency_id,
                    line.product_qty, line.product_id, self.order_id.partner_id
                )['total_excluded']
                for line in self.order_id.order_line
                for tax in line.taxes_id
                if tax.is_rg5329_perception
            )
            order_total = (self.order_id.amount_total or 0) - rg5329_tax_amount
        else:
            order_total = 0

        should_have_rg5329 = (
            rg5329_tax and
            self.product_id and
            self.product_id.apply_rg5329 and
            self.order_id and
            order_total >= 10_000_000 and
            self.order_id.partner_id and
            self.order_id.partner_id._is_rg5329_eligible()
        )

        if should_have_rg5329 and rg5329_tax.id not in self.taxes_id.ids:
            _logger.warning("RG5329: Line missing RG5329 tax during stock move - ADDING IT")
            self.write({'taxes_id': [(6, 0, list(self.taxes_id.ids) + [rg5329_tax.id])]})

        _logger.debug("RG5329: Stock move price unit for %s, taxes: %s",
                      self.product_id.name if self.product_id else 'No product',
                      [t.name for t in self.taxes_id])

        return super()._get_stock_move_price_unit()

    @api.onchange('product_qty', 'price_unit', 'product_id')
    def _onchange_rg5329_unified(self):
        """Trigger RG5329 recalculation when line values change"""
        if (self.order_id and
                not self.env.context.get('applying_rg5329') and
                not self.env.context.get('skip_onchange')):
            _logger.debug("RG5329: Line changed, triggering logic...")
            self.order_id._apply_rg5329_logic()

    def write(self, vals):
        """Override write to trigger RG5329 recalculation when line changes"""
        result = super().write(vals)

        critical_fields = ['product_qty', 'price_unit', 'product_id']
        if (not self.env.context.get('applying_rg5329') and
                not self.env.context.get('skip_onchange') and
                any(field in vals for field in critical_fields) and
                'taxes_id' not in vals):

            orders_to_recalc = {
                line.order_id.id for line in self
                if line.order_id and line.order_id.state in ['draft', 'sent']
            }
            for order_id in orders_to_recalc:
                order = self.env['purchase.order'].browse(order_id)
                _logger.debug("RG5329: Line write triggered for purchase order %s", order.name)
                order.with_context(skip_onchange=True)._apply_rg5329_logic()

        return result
