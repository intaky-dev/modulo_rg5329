from odoo import models, fields, api, _

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    rg5329_perception_amount = fields.Monetary(
        string='Total Percepción RG 5329',
        compute='_compute_rg5329_perception',
        store=True
    )
    
    rg5329_base_amount = fields.Monetary(
        string='Base RG 5329',
        compute='_compute_rg5329_perception',
        store=True
    )
    
    @api.depends('invoice_line_ids', 'invoice_line_ids.price_subtotal')
    def _compute_rg5329_perception(self):
        for move in self:
            if move.move_type not in ['out_invoice', 'out_refund'] or move.partner_id.rg5329_exempt:
                move.rg5329_perception_amount = 0
                move.rg5329_base_amount = 0
                continue
                
            base_amount = 0
            perception_amount = 0
            
            # Calcular base imponible para productos RG 5329
            for line in move.invoice_line_ids:
                if line.product_id and line.product_id.apply_rg5329:
                    base_amount += line.price_subtotal
            
            move.rg5329_base_amount = base_amount
            
            # Solo aplicar si supera $3000
            if base_amount >= 3000:
                for line in move.invoice_line_ids:
                    if line.product_id and line.product_id.apply_rg5329:
                        # Determinar alícuota según IVA del producto
                        iva_rate = move._get_line_iva_rate(line)
                        if iva_rate == 21.0:
                            perception_rate = 3.0  # 3%
                        elif iva_rate == 10.5:
                            perception_rate = 1.5  # 1,5%
                        else:
                            perception_rate = 0.0
                        
                        if perception_rate > 0:
                            line_perception = line.price_subtotal * (perception_rate / 100)
                            perception_amount += line_perception
            
            move.rg5329_perception_amount = perception_amount
    
    def _get_line_iva_rate(self, line):
        """Obtiene la alícuota de IVA de una línea"""
        for tax in line.tax_ids:
            if tax.type_tax_use == 'sale' and tax.amount in [21.0, 10.5]:
                return tax.amount
        return 0.0
    
    def action_post(self):
        """Al confirmar la factura, crear las líneas de percepción"""
        res = super().action_post()
        for move in self:
            if move.rg5329_perception_amount > 0:
                move._create_rg5329_perception_lines()
        return res
    
    def _create_rg5329_perception_lines(self):
        """Crea las líneas de percepción RG 5329"""
        existing_lines = self.line_ids.filtered(lambda l: l.name and 'RG 5329' in l.name)
        existing_lines.unlink()
        
        if self.rg5329_perception_amount <= 0:
            return
        
        tax_3_percent = self.env['account.tax'].search([
            ('name', 'ilike', 'RG 5329'),
            ('amount', '=', 3.0),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        tax_1_5_percent = self.env['account.tax'].search([
            ('name', 'ilike', 'RG 5329'),
            ('amount', '=', 1.5),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        perception_3_amount = 0
        perception_1_5_amount = 0
        
        # Calcular percepciones por separado
        for line in self.invoice_line_ids:
            if line.product_id and line.product_id.apply_rg5329:
                iva_rate = self._get_line_iva_rate(line)
                if iva_rate == 21.0:
                    perception_3_amount += line.price_subtotal * 0.03
                elif iva_rate == 10.5:
                    perception_1_5_amount += line.price_subtotal * 0.015
        
        # Crear línea para percepción 3% si corresponde
        if perception_3_amount > 0 and tax_3_percent:
            self._create_perception_line(tax_3_percent, perception_3_amount, '3% (IVA 21%)')
        
        # Crear línea para percepción 1,5% si corresponde  
        if perception_1_5_amount > 0 and tax_1_5_percent:
            self._create_perception_line(tax_1_5_percent, perception_1_5_amount, '1,5% (IVA 10,5%)')
    
    def _create_perception_line(self, tax, amount, description):
        """Crea una línea de percepción específica"""
        # Obtener CUIT del cliente
        partner_cuit = self.partner_id.vat or 'Sin CUIT'
        if partner_cuit and not partner_cuit.startswith('Sin'):
            partner_cuit = f"CUIT: {partner_cuit}"
        
        # Descripción detallada con impuesto y CUIT
        detailed_name = f'Percepción RG 5329 - {description} - {partner_cuit} - {self.partner_id.name}'
        
        self.env['account.move.line'].create({
            'move_id': self.id,
            'name': detailed_name,
            'account_id': tax.account_id.id,
            'debit': amount if self.move_type == 'out_invoice' else 0,
            'credit': amount if self.move_type == 'out_refund' else 0,
            'partner_id': self.partner_id.id,
        })
        
        # Línea de contrapartida
        counterpart_account = self.partner_id.property_account_receivable_id
        self.env['account.move.line'].create({
            'move_id': self.id,
            'name': detailed_name,
            'account_id': counterpart_account.id,
            'debit': amount if self.move_type == 'out_refund' else 0,
            'credit': amount if self.move_type == 'out_invoice' else 0,
            'partner_id': self.partner_id.id,
        })
