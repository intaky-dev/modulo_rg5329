from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = ['sale.order', 'rg5329.order.mixin']

    def _rg5329_line_tax_field(self):
        return 'tax_id'

    def apply_rg5329_logic_manual(self):
        """Public method to manually trigger RG5329 logic"""
        self._apply_rg5329_logic()
        return True

    def apply_rg5329_via_js(self):
        """Public method for JavaScript to trigger RG5329 logic"""
        try:
            _logger.debug("RG5329 JS: JavaScript trigger called for order %s", self.name)
            self._apply_rg5329_logic()
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._compute_amounts()
            return {
                'success': True,
                'message': 'RG5329 logic applied successfully',
                'new_total': self.amount_total
            }
        except Exception as e:
            _logger.error("RG5329 JS: Error in JavaScript trigger: %s", str(e))
            return {'success': False, 'message': str(e)}

    def apply_rg5329_manual_button(self):
        """Manual button to apply RG5329 tax"""
        try:
            _logger.info("RG5329 BUTTON: Manual button clicked for order %s", self.name)
            self._apply_rg5329_logic()
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._compute_amounts()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Tax Applied',
                    'message': f'RG5329 tax has been applied to order {self.name}. New total: ${self.amount_total:,.2f}',
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

    def _apply_rg5329_logic(self):
        """
        Apply RG5329 perception tax to sale order lines.
        Eligibility and per-line add/remove logic delegated to rg5329.order.mixin.
        """
        if self.state not in ['draft', 'sent'] or self.env.context.get('applying_rg5329'):
            return True

        self.with_context(applying_rg5329=True)._compute_amounts()
        total = self.amount_untaxed or 0
        _logger.debug("RG5329: Processing sale order %s - total $%s", self.name or 'New', total)

        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'sale'),
        ], limit=1)

        if not rg5329_tax:
            _logger.warning("RG5329: No RG5329 sale tax found!")
            return False

        self._apply_rg5329_to_lines(rg5329_tax, total)
        return True

    def _force_ui_refresh(self):
        """Force UI refresh after tax changes"""
        try:
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._compute_amounts()
            if hasattr(self.env['bus.bus'], '_sendone'):
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id,
                    'sale_order/rg5329_updated',
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

    def _compute_amounts(self):
        """Override to trigger RG5329 logic after totals are calculated"""
        result = super()._compute_amounts()

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


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_uom_qty', 'price_unit', 'product_id')
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

        critical_fields = ['product_uom_qty', 'price_unit', 'product_id']
        if (not self.env.context.get('applying_rg5329') and
                not self.env.context.get('skip_onchange') and
                any(field in vals for field in critical_fields) and
                'tax_id' not in vals):

            orders_to_recalc = {
                line.order_id.id for line in self
                if line.order_id and line.order_id.state in ['draft', 'sent']
            }
            for order_id in orders_to_recalc:
                order = self.env['sale.order'].browse(order_id)
                _logger.debug("RG5329: Line write triggered for order %s", order.name)
                order.with_context(skip_onchange=True)._apply_rg5329_logic()

        return result
