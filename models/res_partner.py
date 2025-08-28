from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    rg5329_exempt = fields.Boolean(
        string='Exento RG 5329',
        help='Indica si el cliente está exento del régimen de percepción RG 5329',
        default=False
    )