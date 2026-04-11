from odoo import models
import logging

_logger = logging.getLogger(__name__)

RG5329_MIN_TOTAL = 10_000_000


class Rg5329OrderMixin(models.AbstractModel):
    _name = 'rg5329.order.mixin'
    _description = 'RG 5329 - shared per-line tax logic for sale and purchase orders'

    def _rg5329_line_tax_field(self):
        """Name of the Many2many tax field on order lines. Override per model."""
        raise NotImplementedError

    def _apply_rg5329_to_lines(self, rg5329_tax, total):
        """
        Add or remove rg5329_tax on each eligible order line based on total.

        Shared between SaleOrder and PurchaseOrder. Each model keeps its own
        _apply_rg5329_logic() for total calculation (sale uses amount_untaxed,
        purchase must subtract the RG5329 amount to avoid circular recursion).
        """
        tax_field = self._rg5329_line_tax_field()

        for line in self.order_line:
            if not (line.product_id and line.product_id.apply_rg5329):
                continue

            current_taxes = getattr(line, tax_field)

            if not (self.partner_id and self.partner_id._is_rg5329_eligible()):
                if rg5329_tax.id in current_taxes.ids:
                    new_taxes = current_taxes.filtered(lambda t: t.id != rg5329_tax.id)
                    line.with_context(skip_onchange=True).write(
                        {tax_field: [(6, 0, new_taxes.ids)]}
                    )
                    _logger.info("RG5329: Removed tax - partner not eligible")
                continue

            has_tax = rg5329_tax.id in current_taxes.ids

            if total >= RG5329_MIN_TOTAL:
                if not has_tax:
                    new_ids = list(current_taxes.ids) + [rg5329_tax.id]
                    line.with_context(skip_onchange=True).write(
                        {tax_field: [(6, 0, new_ids)]}
                    )
                    _logger.info("RG5329: ✅ ADDED tax - total $%s >= $10M", total)
                    self._force_ui_refresh()
            else:
                if has_tax:
                    new_ids = [t for t in current_taxes.ids if t != rg5329_tax.id]
                    line.with_context(skip_onchange=True).write(
                        {tax_field: [(6, 0, new_ids)]}
                    )
                    _logger.info("RG5329: ❌ REMOVED tax - total $%s < $10M", total)
                    self._force_ui_refresh()
