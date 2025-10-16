from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    apply_rg5329 = fields.Boolean(
        string='Aplicar Percepción RG 5329',
        default=False,
        help='Marque si este producto está sujeto a la percepción RG 5329'
    )



class ProductProduct(models.Model):
    _inherit = 'product.product'

    apply_rg5329 = fields.Boolean(
        related='product_tmpl_id.apply_rg5329',
        readonly=False,
        store=True
    )
