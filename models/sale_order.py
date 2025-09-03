from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def apply_rg5329_logic_manual(self):
        """Public method to manually trigger RG5329 logic"""
        self._apply_rg5329_logic()
        return True
    
    def apply_rg5329_via_js(self):
        """Public method for JavaScript to trigger RG5329 logic"""
        try:
            _logger.info("RG5329 JS: JavaScript trigger called for order %s", self.name)
            self._apply_rg5329_logic()
            
            # Force UI refresh by invalidating cache
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._compute_amounts()
            
            # Return success response
            return {
                'success': True,
                'message': 'RG5329 logic applied successfully',
                'new_total': self.amount_total
            }
        except Exception as e:
            _logger.error("RG5329 JS: Error in JavaScript trigger: %s", str(e))
            return {
                'success': False,
                'message': str(e)
            }
    
    def apply_rg5329_manual_button(self):
        """Manual button to apply RG5329 tax - Reliable UI method"""
        try:
            _logger.info("RG5329 BUTTON: Manual button clicked for order %s", self.name)
            
            # Apply the logic
            self._apply_rg5329_logic()
            
            # Force UI refresh
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._compute_amounts()
            
            # Show success message to user
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Tax Applied',
                    'message': f'RG5329 tax has been applied to order {self.name}. New total: ${self.amount_total:,.2f}',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error("RG5329 BUTTON: Error in manual button: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Error',
                    'message': f'Error applying RG5329 tax: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def _apply_rg5329_logic(self):
        """
        UNIFIED RG5329 Logic - Single source of truth
        Applies RG5329 tax automatically based on:
        1. Customer is IVA Responsable Inscripto (code '1')
        2. Product has apply_rg5329 = True
        3. Order total >= $100,000
        """
        if self.state not in ['draft', 'sent'] or self.env.context.get('applying_rg5329'):
            return True
        
        # Force recalculation of totals first
        self.with_context(applying_rg5329=True)._compute_amounts()
        total = self.amount_untaxed or 0
        _logger.info("=== RG5329 UNIFIED: Processing order %s with total $%s ===", self.name or 'New', total)
        
        # Find RG5329 tax
        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'sale')
        ], limit=1)
        
        if not rg5329_tax:
            _logger.warning("RG5329 UNIFIED: No RG5329 tax found!")
            return False
        
        _logger.info("RG5329 UNIFIED: Found RG5329 tax: %s (ID: %s)", rg5329_tax.name, rg5329_tax.id)
        
        # Debug order line info
        _logger.info("RG5329 DEBUG: Order has %d lines", len(self.order_line))
        _logger.info("RG5329 DEBUG: Order line IDs: %s", [line.id for line in self.order_line])
        
        # Process all lines at once
        line_count = 0
        for line in self.order_line:
            line_count += 1
            _logger.info("RG5329 DEBUG: Processing line with product: %s", 
                        line.product_id.name if line.product_id else 'No product')
            
            # Only process products marked for RG5329
            if not (line.product_id and line.product_id.apply_rg5329):
                _logger.info("RG5329 DEBUG: Skipping line - product not marked for RG5329")
                continue
                
            _logger.info("RG5329 DEBUG: Line has RG5329 product, checking customer conditions...")
                
            # Skip if customer is exempt
            if self.partner_id and self.partner_id.rg5329_exempt:
                _logger.info("RG5329 DEBUG: Customer is exempt")
                # Remove tax if customer is exempt
                if rg5329_tax.id in line.tax_id.ids:
                    new_taxes = line.tax_id.filtered(lambda t: t.id != rg5329_tax.id)
                    line.write({'tax_id': [(6, 0, new_taxes.ids)]})
                    _logger.info("RG5329 UNIFIED: Removed tax - customer exempt")
                continue
            
            _logger.info("RG5329 DEBUG: Customer not exempt, checking eligibility...")
            
            # Check if customer is eligible (only Responsable Inscripto)
            if not self._is_customer_eligible_for_rg5329():
                _logger.info("RG5329 DEBUG: Customer not eligible for RG5329")
                # Remove tax if customer not eligible
                if rg5329_tax.id in line.tax_id.ids:
                    new_taxes = line.tax_id.filtered(lambda t: t.id != rg5329_tax.id)
                    line.write({'tax_id': [(6, 0, new_taxes.ids)]})
                    _logger.info("RG5329 UNIFIED: Removed tax - customer not eligible")
                continue
            
            _logger.info("RG5329 DEBUG: Customer eligible! Proceeding with tax logic...")
            
            has_tax = rg5329_tax.id in line.tax_id.ids
            
            if total >= 100000:
                # ADD tax if not present
                if not has_tax:
                    current_tax_ids = list(line.tax_id.ids)  # Convert to list to avoid issues
                    if rg5329_tax.id not in current_tax_ids:  # Double check
                        current_tax_ids.append(rg5329_tax.id)
                        line.with_context(skip_onchange=True).write({'tax_id': [(6, 0, current_tax_ids)]})
                        _logger.info("RG5329 UNIFIED: ✅ ADDED tax - total $%s >= $100k", total)
                        
                        # Force UI refresh
                        self._force_ui_refresh()
                else:
                    _logger.info("RG5329 UNIFIED: ✅ Tax already present - total $%s >= $100k", total)
            else:
                # REMOVE tax if present  
                if has_tax:
                    current_tax_ids = [t_id for t_id in line.tax_id.ids if t_id != rg5329_tax.id]
                    line.with_context(skip_onchange=True).write({'tax_id': [(6, 0, current_tax_ids)]})
                    _logger.info("RG5329 UNIFIED: ❌ REMOVED tax - total $%s < $100k", total)
                    
                    # Force UI refresh
                    self._force_ui_refresh()
                else:
                    _logger.info("RG5329 UNIFIED: ❌ Tax already not present - total $%s < $100k", total)
        
        _logger.info("RG5329 DEBUG: Processed %d lines total", line_count)
        return True
    
    def _is_customer_eligible_for_rg5329(self):
        """
        Check if customer is eligible for RG 5329
        Only applies to IVA Responsable Inscripto (code '1')
        """
        try:
            partner = self.partner_id
            
            if not hasattr(partner, 'l10n_ar_afip_responsibility_type_id'):
                _logger.warning("RG5329 UNIFIED: No AFIP responsibility field found")
                return False
            
            if not partner.l10n_ar_afip_responsibility_type_id:
                _logger.info("RG5329 UNIFIED: Partner %s - no fiscal responsibility configured", partner.name)
                return False
            
            responsibility_code = partner.l10n_ar_afip_responsibility_type_id.code
            is_eligible = responsibility_code == '1'  # IVA Responsable Inscripto
            
            _logger.info("RG5329 UNIFIED: Partner %s - code %s - eligible: %s", 
                        partner.name, responsibility_code, is_eligible)
            
            return is_eligible
            
        except Exception as e:
            _logger.error("RG5329 UNIFIED: Error checking eligibility: %s", str(e))
            return False
    
    def _force_ui_refresh(self):
        """Force UI refresh after tax changes"""
        try:
            # Invalidate computed fields cache
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            
            # Force recomputation
            self._compute_amounts()
            
            # Notify UI of changes
            if hasattr(self.env['bus.bus'], '_sendone'):
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id, 
                    'sale_order/rg5329_updated', 
                    {'order_id': self.id}
                )
            
            _logger.info("RG5329 UNIFIED: UI refresh triggered")
            
        except Exception as e:
            _logger.error("RG5329 UNIFIED: Error forcing UI refresh: %s", str(e))
    
    @api.onchange('partner_id')
    def _onchange_partner_rg5329_unified(self):
        """Trigger RG5329 recalculation when partner changes"""
        if self.partner_id and not self.env.context.get('skip_onchange'):
            _logger.info("RG5329 UNIFIED: Partner changed, triggering logic...")
            self._apply_rg5329_logic()
    
    def _compute_amounts(self):
        """Override _compute_amounts to trigger RG5329 logic after totals are calculated"""
        result = super()._compute_amounts()
        
        # Trigger RG5329 logic after amounts are computed (but avoid infinite loops)
        if (not self.env.context.get('applying_rg5329') and 
            not self.env.context.get('skip_rg5329_auto')):
            
            for order in self:
                if order.state in ['draft', 'sent']:
                    # Only trigger if there are RG5329 products
                    has_rg5329_products = any(
                        line.product_id and line.product_id.apply_rg5329 
                        for line in order.order_line
                    )
                    if has_rg5329_products:
                        _logger.info("RG5329 UNIFIED: Amounts computed, checking RG5329 logic...")
                        order.with_context(skip_rg5329_auto=True)._apply_rg5329_logic()
        
        return result

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    @api.onchange('product_uom_qty', 'price_unit', 'product_id')
    def _onchange_rg5329_unified(self):
        """Trigger RG5329 recalculation when line values change"""
        if (self.order_id and 
            not self.env.context.get('applying_rg5329') and
            not self.env.context.get('skip_onchange')):
            _logger.info("RG5329 UNIFIED: Line changed, triggering logic...")
            self.order_id._apply_rg5329_logic()
    
    def write(self, vals):
        """Override write to trigger RG5329 recalculation when line changes"""
        result = super().write(vals)
        
        # Only trigger for critical changes and avoid loops
        critical_fields = ['product_uom_qty', 'price_unit', 'product_id']
        if (not self.env.context.get('applying_rg5329') and 
            not self.env.context.get('skip_onchange') and
            any(field in vals for field in critical_fields) and
            'tax_id' not in vals):  # Don't trigger if we're updating taxes
            
            orders_to_recalc = set()
            for line in self:
                if line.order_id and line.order_id.state in ['draft', 'sent']:
                    orders_to_recalc.add(line.order_id.id)
            
            # Trigger for all affected orders with context to prevent loops
            for order_id in orders_to_recalc:
                order = self.env['sale.order'].browse(order_id)
                _logger.info("RG5329 UNIFIED: Line write triggered for order %s", order.name)
                order.with_context(skip_onchange=True)._apply_rg5329_logic()
                
        return result