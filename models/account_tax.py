from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_rg5329_perception = fields.Boolean(
        string='Percepción RG 5329',
        default=False,
        help='Marque si este impuesto es una percepción RG 5329'
    )
    
    def compute_all(self, price_unit, currency=None, quantity=1.0, product=None, partner=None, is_refund=False, handle_price_include=True, include_caba_tags=False, fixed_multiplicator=1, **kwargs):
        """Override para aplicar lógica condicional a impuestos RG 5329"""
        # Filtrar impuestos RG 5329 si el producto no está marcado
        taxes_to_compute = self

        # Verificar si hay impuestos RG 5329 que deben ser excluidos
        if product and hasattr(product, 'apply_rg5329'):
            if not product.apply_rg5329:
                # Excluir impuestos RG 5329 si el producto no está marcado
                taxes_to_compute = self.filtered(lambda t: not t.is_rg5329_perception)
        else:
            # Si no hay producto o no tiene el campo, excluir todos los RG 5329
            taxes_to_compute = self.filtered(lambda t: not t.is_rg5329_perception)

        # Si no quedan impuestos para calcular, retornar valores base
        if not taxes_to_compute:
            return {
                'taxes': [],
                'total_excluded': price_unit * quantity,
                'total_included': price_unit * quantity,
                'base': price_unit * quantity,
            }

        return super(AccountTax, taxes_to_compute).compute_all(price_unit, currency, quantity, product, partner, is_refund, handle_price_include, include_caba_tags, fixed_multiplicator, **kwargs)
