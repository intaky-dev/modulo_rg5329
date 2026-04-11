from odoo import models, fields


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_rg5329_perception = fields.Boolean(
        string='Percepción RG 5329',
        default=False,
        help='Marque si este impuesto es una percepción RG 5329'
    )
