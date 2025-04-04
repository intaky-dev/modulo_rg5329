from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    apply_rg5329 = fields.Boolean(string='Aplicar Percepción RG 5329')
