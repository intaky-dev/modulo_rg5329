from odoo import models, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.onchange('invoice_line_ids')
    def _apply_rg5329_tax(self):
        tax = self.env.ref('rg5329_tax_module.tax_rg5329_pais_25', raise_if_not_found=False)
        if not tax:
            return

        # Calcular el total de líneas alcanzadas por RG 5329
        rg_total = sum(
            line.price_subtotal
            for line in self.invoice_line_ids
            if line.product_id.apply_rg5329
        )

        for line in self.invoice_line_ids:
            if line.product_id.apply_rg5329 and rg_total > 100000:
                if tax not in line.tax_ids:
                    line.tax_ids += tax
            else:
                if tax in line.tax_ids:
                    line.tax_ids -= tax

