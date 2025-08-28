from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_rg5329_perception = fields.Boolean(
        string='Percepción RG 5329',
        default=False,
        help='Marque si este impuesto es una percepción RG 5329'
    )
    
    def compute_all(self, price_unit, currency=None, quantity=1.0, product=None, partner=None, is_refund=False, handle_price_include=True, include_caba_tags=False, fixed_multiplicator=1):
        """Override para aplicar lógica condicional a impuestos RG 5329"""
        # Si es un impuesto RG 5329, verificar condiciones antes de calcular
        if self.is_rg5329_perception:
            # Verificar si el producto está marcado para RG 5329
            if not (product and hasattr(product, 'apply_rg5329') and product.apply_rg5329):
                return {
                    'taxes': [],
                    'total_excluded': price_unit * quantity,
                    'total_included': price_unit * quantity,
                    'base': price_unit * quantity,
                }
        
        return super().compute_all(price_unit, currency, quantity, product, partner, is_refund, handle_price_include, include_caba_tags, fixed_multiplicator)
