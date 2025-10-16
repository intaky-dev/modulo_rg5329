/** @odoo-module **/

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

// Patch the Order model to include RG5329 display logic only
patch(Order.prototype, {
    
    /**
     * Calculate RG5329 information for display purposes only
     * Actual tax calculations are handled server-side during order creation
     */
    getRG5329Info() {
        // Skip if partner is exempt
        if (this.get_partner() && this.get_partner().rg5329_exempt) {
            return {
                applicable: false,
                reason: 'Cliente exento de RG5329'
            };
        }

        // Calculate subtotal of RG5329 products
        let rg5329_subtotal = 0.0;
        const rg5329_lines = [];
        
        for (const line of this.get_orderlines()) {
            if (line.product.apply_rg5329) {
                rg5329_subtotal += line.get_price_without_tax();
                rg5329_lines.push(line);
            }
        }

        if (rg5329_lines.length === 0) {
            return {
                applicable: false,
                reason: 'Sin productos RG5329'
            };
        }

        if (rg5329_subtotal < 100000) {
            return {
                applicable: false,
                reason: `Subtotal RG5329: $${rg5329_subtotal.toFixed(2)} (mínimo: $100.000)`,
                subtotal: rg5329_subtotal
            };
        }

        // Calculate expected RG5329 taxes
        let tax_21_amount = 0;
        let tax_105_amount = 0;
        
        for (const line of rg5329_lines) {
            const lineSubtotal = line.get_price_without_tax();
            
            // Check if line has 21% or 10.5% IVA
            for (const tax of line.get_taxes()) {
                if (tax.amount === 21.0) {
                    tax_21_amount += lineSubtotal * 0.03; // 3% RG5329
                } else if (tax.amount === 10.5) {
                    tax_105_amount += lineSubtotal * 0.015; // 1.5% RG5329
                }
            }
        }

        return {
            applicable: true,
            subtotal: rg5329_subtotal,
            tax_21_amount: tax_21_amount,
            tax_105_amount: tax_105_amount,
            total_rg5329_tax: tax_21_amount + tax_105_amount,
            lines_count: rg5329_lines.length
        };
    }
});

// Note: RG5329 taxes are automatically calculated and applied server-side
// during order creation in create_from_ui method. No client-side tax 
// modifications are needed, preventing "posted journal item" errors.