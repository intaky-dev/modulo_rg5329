# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def create(self, vals_list):
        """Override create to apply RG5329 logic before order creation"""
        _logger.info(f"RG5329 POS: create called")
        
        # If it's a single vals dict, convert to list
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        
        # Process each order for RG5329
        processed_vals_list = []
        for vals in vals_list:
            processed_vals = self._process_rg5329_in_create_vals(vals)
            processed_vals_list.append(processed_vals)
        
        # Create orders with RG5329 taxes already included
        if len(processed_vals_list) == 1 and isinstance(vals_list, dict):
            result = super().create(processed_vals_list[0])
        else:
            result = super().create(processed_vals_list)
        
        # Force recalculation of taxes and amounts after creation
        for order in result:
            if self._order_has_rg5329_products(order):
                _logger.info(f"RG5329 POS: Forcing tax recalculation for order {order.id}")
                
                # Debug: Show current tax status
                for line in order.lines:
                    if line.product_id and line.product_id.apply_rg5329:
                        tax_names = [f"{tax.name} ({tax.amount}%)" for tax in line.tax_ids]
                        _logger.info(f"RG5329 POS: Line {line.product_id.name} - Taxes: {tax_names}")
                        subtotal = getattr(line, 'price_subtotal', 0)
                        total_incl = getattr(line, 'price_subtotal_incl', 0)
                        tax_amount = total_incl - subtotal
                        _logger.info(f"RG5329 POS: Line amounts BEFORE recalc - Subtotal: {subtotal}, Tax: {tax_amount}, Total: {total_incl}")
                
                # Force recomputation of line amounts and taxes
                for line in order.lines:
                    line._compute_amount_line_all()
                
                # POS orders don't have _compute_amount_all, use manual calculation
                order._amount_all()
                
                # Debug: Show amounts after recalculation
                for line in order.lines:
                    if line.product_id and line.product_id.apply_rg5329:
                        subtotal = getattr(line, 'price_subtotal', 0)
                        total_incl = getattr(line, 'price_subtotal_incl', 0)
                        tax_amount = total_incl - subtotal
                        _logger.info(f"RG5329 POS: Line amounts AFTER recalc - Subtotal: {subtotal}, Tax: {tax_amount}, Total: {total_incl}")
                
                _logger.info(f"RG5329 POS: Order {order.id} total amounts - Untaxed: {order.amount_untaxed}, Tax: {order.amount_tax}, Total: {order.amount_total}")
        
        _logger.info(f"RG5329 POS: Order(s) created successfully")
        return result
    
    def _order_has_rg5329_products(self, order):
        """Check if order has any RG5329 products"""
        for line in order.lines:
            if line.product_id and line.product_id.apply_rg5329:
                return True
        return False

    @api.model
    def _process_order(self, order, existing_order):
        """Override to apply RG5329 logic when processing POS orders"""
        _logger.info(f"RG5329 POS: _process_order called")
        
        # Apply RG5329 logic BEFORE processing the order
        self._process_rg5329_taxes_in_order_data(order)
        
        # Call original method
        result = super()._process_order(order, existing_order)
        
        _logger.info(f"RG5329 POS: Order processed successfully")
        return result
    
    def _process_rg5329_in_create_vals(self, vals):
        """Process vals for create method to add RG5329 taxes"""
        try:
            _logger.info("RG5329 POS: Processing create vals")
            
            # Skip if no partner or partner is exempt
            partner_id = vals.get('partner_id')
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                if partner.rg5329_exempt:
                    _logger.info(f"RG5329 POS: Partner {partner.name} is exempt, skipping")
                    return vals
            
            # Process order lines if present
            lines = vals.get('lines', [])
            if lines:
                # Calculate RG5329 subtotal
                rg5329_subtotal = 0.0
                for line_data in lines:
                    # Handle line format: (0, 0, line_vals) or direct line_vals
                    line_vals = line_data
                    if isinstance(line_data, (list, tuple)) and len(line_data) >= 3:
                        line_vals = line_data[2]
                    
                    product_id = line_vals.get('product_id')
                    if product_id:
                        product = self.env['product.product'].browse(product_id)
                        if product.apply_rg5329:
                            qty = line_vals.get('qty', 0)
                            price_unit = line_vals.get('price_unit', 0)
                            rg5329_subtotal += qty * price_unit
                
                _logger.info(f"RG5329 POS: RG5329 subtotal in create: ${rg5329_subtotal}")
                
                # Apply RG5329 taxes if threshold is met
                if rg5329_subtotal >= 100000:
                    self._add_rg5329_taxes_to_create_lines(lines)
            
        except Exception as e:
            _logger.error(f"RG5329 POS: Error in _process_rg5329_in_create_vals: {e}")
            import traceback
            _logger.error(f"RG5329 POS: Traceback: {traceback.format_exc()}")
        
        return vals
    
    def _add_rg5329_taxes_to_create_lines(self, lines):
        """Add RG5329 taxes to lines in create vals format"""
        try:
            # Get RG5329 taxes
            rg5329_tax_21 = self.env['account.tax'].search([
                ('name', '=', 'Percepción IVA RG 5329 - 3%')
            ], limit=1)
            
            rg5329_tax_105 = self.env['account.tax'].search([
                ('name', '=', 'Percepción IVA RG 5329 - 1,5%')
            ], limit=1)
            
            for line_data in lines:
                # Handle line format: (0, 0, line_vals) or direct line_vals
                line_vals = line_data
                if isinstance(line_data, (list, tuple)) and len(line_data) >= 3:
                    line_vals = line_data[2]
                
                product_id = line_vals.get('product_id')
                if product_id:
                    product = self.env['product.product'].browse(product_id)
                    if product.apply_rg5329:
                        # Get current tax_ids
                        current_tax_ids_raw = line_vals.get('tax_ids', [])
                        current_tax_ids = []
                        if isinstance(current_tax_ids_raw, list) and current_tax_ids_raw:
                            for cmd in current_tax_ids_raw:
                                if isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
                                    if cmd[0] == 6 and len(cmd) > 2:
                                        # Format: [6, 0, [tax_ids]] - replace all
                                        current_tax_ids.extend(cmd[2] if cmd[2] else [])
                                    elif cmd[0] == 4:
                                        # Format: [4, tax_id] - link existing
                                        current_tax_ids.append(cmd[1])
                                elif isinstance(cmd, int):
                                    # Direct ID
                                    current_tax_ids.append(cmd)
                        
                        # Determine which RG5329 tax to add
                        existing_taxes = self.env['account.tax'].browse(current_tax_ids) if current_tax_ids else self.env['account.tax']
                        rg5329_tax_to_add = None
                        
                        try:
                            for tax in existing_taxes:
                                if abs(tax.amount - 21.0) < 0.01:
                                    rg5329_tax_to_add = rg5329_tax_21
                                    break
                                elif abs(tax.amount - 10.5) < 0.01:
                                    rg5329_tax_to_add = rg5329_tax_105
                                    break
                                elif abs(tax.amount - 15.0) < 0.01:
                                    # Temporal: Support 15% tax for testing (use 3% RG5329)
                                    rg5329_tax_to_add = rg5329_tax_21
                                    _logger.info("RG5329 POS: Using 15% tax with 3% RG5329 (temporal for testing)")
                                    break
                        except (TypeError, ValueError) as e:
                            _logger.error(f"RG5329 POS: Error iterating taxes: {e}, current_tax_ids: {current_tax_ids}")
                            # Try alternative approach
                            for tax_id in current_tax_ids:
                                if isinstance(tax_id, int):
                                    tax = self.env['account.tax'].browse(tax_id)
                                    if tax.exists() and abs(tax.amount - 21.0) < 0.01:
                                        rg5329_tax_to_add = rg5329_tax_21
                                        break
                                    elif tax.exists() and abs(tax.amount - 10.5) < 0.01:
                                        rg5329_tax_to_add = rg5329_tax_105
                                        break
                                    elif tax.exists() and abs(tax.amount - 15.0) < 0.01:
                                        # Temporal: Support 15% tax for testing
                                        rg5329_tax_to_add = rg5329_tax_21
                                        break
                        
                        # Add RG5329 tax if found and not already present
                        if rg5329_tax_to_add and rg5329_tax_to_add.id not in current_tax_ids:
                            new_tax_ids = current_tax_ids + [rg5329_tax_to_add.id]
                            line_vals['tax_ids'] = [(6, 0, new_tax_ids)]
                            _logger.info(f"RG5329 POS: Added {rg5329_tax_to_add.name} to {product.name} in create")
            
        except Exception as e:
            _logger.error(f"RG5329 POS: Error in _add_rg5329_taxes_to_create_lines: {e}")
            import traceback
            _logger.error(f"RG5329 POS: Traceback: {traceback.format_exc()}")

    def _process_rg5329_taxes_in_order_data(self, order_data):
        """Process order data from UI to include RG5329 taxes before creation"""
        try:
            _logger.info(f"RG5329 POS: Processing order data")
            
            # Skip if no partner or partner is exempt
            partner_id = order_data.get('partner_id')
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                if partner.rg5329_exempt:
                    _logger.info(f"RG5329 POS: Partner {partner.name} is exempt, skipping")
                    return order_data
            else:
                _logger.info("RG5329 POS: No partner specified")

            # Calculate RG5329 subtotal from order lines
            rg5329_subtotal = 0.0
            lines_data = order_data.get('lines', [])
            _logger.info(f"RG5329 POS: Found {len(lines_data)} lines to process")
            
            # First pass: calculate subtotal
            for line_data in lines_data:
                # Handle both UI format [0, 0, line_dict] and direct line_dict format
                line_dict = line_data
                if isinstance(line_data, (list, tuple)) and len(line_data) >= 3:
                    line_dict = line_data[2]
                
                product_id = line_dict.get('product_id')
                
                if product_id:
                    product = self.env['product.product'].browse(product_id)
                    if product.apply_rg5329:
                        qty = line_dict.get('qty', 0)
                        price_unit = line_dict.get('price_unit', 0)
                        line_total = qty * price_unit
                        rg5329_subtotal += line_total
                        _logger.info(f"RG5329 POS: Product {product.name} contributes ${line_total}")

            _logger.info(f"RG5329 POS: Total RG5329 subtotal: ${rg5329_subtotal}")

            # Only apply if subtotal >= $100,000
            if rg5329_subtotal < 100000:
                _logger.info(f"RG5329 POS: Subtotal ${rg5329_subtotal} below $100,000 threshold, skipping")
                return order_data

            # Get RG5329 taxes
            rg5329_tax_21 = self.env['account.tax'].search([
                ('name', '=', 'Percepción IVA RG 5329 - 3%')
            ], limit=1)
            
            rg5329_tax_105 = self.env['account.tax'].search([
                ('name', '=', 'Percepción IVA RG 5329 - 1,5%')
            ], limit=1)

            _logger.info(f"RG5329 POS: Found taxes - 21%: {rg5329_tax_21.name if rg5329_tax_21 else 'None'}, 10.5%: {rg5329_tax_105.name if rg5329_tax_105 else 'None'}")

            # Second pass: add taxes to lines
            lines_modified = 0
            for line_data in lines_data:
                # Handle both UI format [0, 0, line_dict] and direct line_dict format
                line_dict = line_data
                if isinstance(line_data, (list, tuple)) and len(line_data) >= 3:
                    line_dict = line_data[2]
                
                product_id = line_dict.get('product_id')
                
                if product_id:
                    product = self.env['product.product'].browse(product_id)
                    if product.apply_rg5329:
                        if self._add_rg5329_tax_to_line_data(line_dict, product, rg5329_tax_21, rg5329_tax_105):
                            lines_modified += 1

            _logger.info(f"RG5329 POS: Modified {lines_modified} lines with RG5329 taxes")
            
        except Exception as e:
            _logger.error(f"RG5329 POS: Error processing UI data: {e}")
            import traceback
            _logger.error(f"RG5329 POS: Traceback: {traceback.format_exc()}")
        
        return order_data

    def _add_rg5329_tax_to_line_data(self, line_dict, product, rg5329_tax_21, rg5329_tax_105):
        """Add RG5329 tax to line data based on existing taxes"""
        try:
            _logger.info(f"RG5329 POS: Processing taxes for product {product.name}")
            
            tax_ids = line_dict.get('tax_ids', [])
            _logger.info(f"RG5329 POS: Original tax_ids format: {tax_ids}")
            
            # Convert tax_ids to list of IDs if needed
            original_tax_ids = []
            if isinstance(tax_ids, list) and tax_ids:
                for cmd in tax_ids:
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
                        if cmd[0] == 6 and len(cmd) > 2:
                            # Format: [6, 0, [tax_ids]] - replace all
                            original_tax_ids.extend(cmd[2] if cmd[2] else [])
                        elif cmd[0] == 4:
                            # Format: [4, tax_id] - link existing
                            original_tax_ids.append(cmd[1])
                    elif isinstance(cmd, int):
                        # Direct ID
                        original_tax_ids.append(cmd)
            
            _logger.info(f"RG5329 POS: Converted tax_ids: {original_tax_ids}")

            # Get existing taxes to determine which RG5329 tax to apply
            existing_taxes = self.env['account.tax'].browse(original_tax_ids) if original_tax_ids else self.env['account.tax']
            _logger.info(f"RG5329 POS: Original tax IDs: {original_tax_ids}")
            
            rg5329_tax_to_add = None
            
            try:
                tax_info = [f'{t.name} ({t.amount}%)' for t in existing_taxes]
                _logger.info(f"RG5329 POS: Existing taxes: {tax_info}")
                
                for tax in existing_taxes:
                    _logger.info(f"RG5329 POS: Checking tax {tax.name} with amount {tax.amount}")
                    if abs(tax.amount - 21.0) < 0.01:  # Use tolerance for floating point comparison
                        rg5329_tax_to_add = rg5329_tax_21
                        _logger.info(f"RG5329 POS: Will add 21% RG5329 tax: {rg5329_tax_21.name if rg5329_tax_21 else 'None'}")
                        break
                    elif abs(tax.amount - 10.5) < 0.01:
                        rg5329_tax_to_add = rg5329_tax_105
                        _logger.info(f"RG5329 POS: Will add 10.5% RG5329 tax: {rg5329_tax_105.name if rg5329_tax_105 else 'None'}")
                        break
                    elif abs(tax.amount - 15.0) < 0.01:
                        # Temporal: Support 15% tax for testing (use 3% RG5329)
                        rg5329_tax_to_add = rg5329_tax_21
                        _logger.info("RG5329 POS: Using 15% tax with 3% RG5329 (temporal for testing)")
                        break
            except (TypeError, ValueError) as e:
                _logger.error(f"RG5329 POS: Error processing taxes: {e}, original_tax_ids: {original_tax_ids}")
                # Try alternative approach
                for tax_id in original_tax_ids:
                    if isinstance(tax_id, int):
                        tax = self.env['account.tax'].browse(tax_id)
                        if tax.exists():
                            _logger.info(f"RG5329 POS: Checking tax ID {tax_id}: {tax.name} ({tax.amount}%)")
                            if abs(tax.amount - 21.0) < 0.01:
                                rg5329_tax_to_add = rg5329_tax_21
                                break
                            elif abs(tax.amount - 10.5) < 0.01:
                                rg5329_tax_to_add = rg5329_tax_105
                                break
                            elif abs(tax.amount - 15.0) < 0.01:
                                # Temporal: Support 15% tax for testing
                                rg5329_tax_to_add = rg5329_tax_21
                                break

            # Add RG5329 tax if applicable and not already present
            if rg5329_tax_to_add and rg5329_tax_to_add.id not in original_tax_ids:
                new_tax_ids = original_tax_ids + [rg5329_tax_to_add.id]
                line_dict['tax_ids'] = [[6, False, new_tax_ids]]
                _logger.info(f"RG5329 POS: Successfully added {rg5329_tax_to_add.name} to {product.name}")
                _logger.info(f"RG5329 POS: Final tax_ids: {new_tax_ids}")
                return True
            else:
                if not rg5329_tax_to_add:
                    _logger.info(f"RG5329 POS: No matching RG5329 tax found for product {product.name}")
                else:
                    _logger.info(f"RG5329 POS: Tax {rg5329_tax_to_add.name} already present for product {product.name}")
                return False
                
        except Exception as e:
            _logger.error(f"RG5329 POS: Error adding tax to line data: {e}")
            import traceback
            _logger.error(f"RG5329 POS: Traceback: {traceback.format_exc()}")
            return False


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'
    
    @api.model
    def create(self, vals_list):
        """Override create to ensure RG5329 tax calculation"""
        # Create the lines normally
        result = super().create(vals_list)
        
        # Force tax recalculation for RG5329 products
        for line in result:
            if line.product_id and line.product_id.apply_rg5329:
                _logger.info(f"RG5329 POS: Forcing line tax recalculation for {line.product_id.name}")
                line._compute_amount_line_all()
        
        return result
    
    def _compute_amount_line_all(self):
        """Ensure proper tax calculation including RG5329 taxes"""
        result = super()._compute_amount_line_all()
        
        # Log tax information for debugging
        for line in self:
            if line.product_id and line.product_id.apply_rg5329:
                tax_names = [tax.name for tax in line.tax_ids]
                _logger.info(f"RG5329 POS: Line {line.product_id.name} has taxes: {tax_names}")
                # In POS order lines, use different field names
                total_incl = getattr(line, 'price_subtotal_incl', 0)
                subtotal = getattr(line, 'price_subtotal', 0)
                tax_amount = total_incl - subtotal
                _logger.info(f"RG5329 POS: Line amounts - Subtotal: {subtotal}, Tax: {tax_amount}, Total: {total_incl}")
        
        return result