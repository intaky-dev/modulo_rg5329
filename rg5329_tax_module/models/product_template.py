from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    apply_rg5329 = fields.Boolean(
        string='Apply RG 5329 Perception',
        default=False,
        help='Check if this product is subject to RG 5329 perception'
    )
    
    rg5329_perception_rate = fields.Selection([
        ('3_percent', '3% - Products with 21% VAT'),
        ('1_5_percent', '1.5% - Products with 10.5% VAT'),
    ], string='RG 5329 Perception Rate',
       help='Perception rate based on VAT category')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    apply_rg5329 = fields.Boolean(
        related='product_tmpl_id.apply_rg5329',
        readonly=False,
        store=True
    )
    
    rg5329_perception_rate = fields.Selection(
        related='product_tmpl_id.rg5329_perception_rate',
        readonly=False,
        store=True
    )