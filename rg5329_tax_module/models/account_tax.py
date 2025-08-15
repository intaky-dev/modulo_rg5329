from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_rg5329_perception = fields.Boolean(
        string='Percepción RG 5329',
        default=False,
        help='Marque si este impuesto es una percepción RG 5329'
    )
    
    rg5329_perception_type = fields.Selection([
        ('3_percent', '3% - Productos con IVA 21%'),
        ('1_5_percent', '1,5% - Productos con IVA 10,5%'),
    ], string='Tipo de Percepción RG 5329',
       help='Tipo de percepción RG 5329 basada en la tasa de IVA')
    
    rg5329_product_categories = fields.Many2many(
        'product.category',
        'rg5329_tax_product_category_rel',
        'tax_id',
        'category_id',
        string='Categorías de Productos RG 5329',
        help='Categorías de productos sujetas a esta percepción'
    )