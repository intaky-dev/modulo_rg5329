from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    apply_rg5329 = fields.Boolean(
        string='Aplicar Percepción RG 5329',
        default=False,
        help='Marque si este producto está sujeto a la percepción RG 5329'
    )
    
    rg5329_perception_rate = fields.Selection([
        ('3_percent', '3% - Productos con IVA 21%'),
        ('1_5_percent', '1,5% - Productos con IVA 10,5%'),
    ], string='Tasa de Percepción RG 5329',
       help='Tasa de percepción basada en la categoría de IVA')


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