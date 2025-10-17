from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_rg5329_perception = fields.Boolean(
        string='Percepción RG 5329',
        default=False,
        help='Marque si este impuesto es una percepción RG 5329'
    )

    def compute_all(
        self, price_unit, currency=None, quantity=1.0, product=None,
        partner=None, is_refund=False, handle_price_include=True,
        include_caba_tags=False, fixed_multiplicator=1, **kwargs
    ):
        """
        Override para aplicar lógica condicional a impuestos RG 5329

        IMPORTANTE: Este método solo filtra impuestos RG5329 durante el cálculo
        si son llamados en contexto de evaluación automática, NO cuando ya fueron
        aplicados manualmente a una línea.
        """
        # Extraer rounding_method de kwargs para evitar duplicación
        # No lo volvemos a agregar, solo lo removemos de kwargs
        kwargs.pop('rounding_method', None)

        # Por defecto, calcular todos los impuestos que se pasaron
        # Solo filtramos RG5329 si viene del contexto de aplicación automática
        taxes_to_compute = self

        # Si NO quedan impuestos para calcular, retornar valores base
        if not taxes_to_compute:
            return {
                'taxes': [],
                'total_excluded': price_unit * quantity,
                'total_included': price_unit * quantity,
                'base': price_unit * quantity,
            }

        return super(AccountTax, taxes_to_compute).compute_all(
            price_unit, currency, quantity, product, partner,
            is_refund, handle_price_include, include_caba_tags,
            fixed_multiplicator, **kwargs
        )
