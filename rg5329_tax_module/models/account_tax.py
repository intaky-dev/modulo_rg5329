from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_rg5329_perception = fields.Boolean(
        string='RG 5329 Perception',
        default=False,
        help='Check if this tax is an RG 5329 perception'
    )
    
    rg5329_perception_type = fields.Selection([
        ('3_percent', '3% - Products with 21% VAT'),
        ('1_5_percent', '1.5% - Products with 10.5% VAT'),
    ], string='RG 5329 Perception Type',
       help='Type of RG 5329 perception based on VAT rate')
    
    rg5329_product_categories = fields.Many2many(
        'product.category',
        'rg5329_tax_product_category_rel',
        'tax_id',
        'category_id',
        string='RG 5329 Product Categories',
        help='Product categories subject to this perception'
    )