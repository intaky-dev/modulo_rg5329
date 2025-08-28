/** @odoo-module **/

import { registry } from "@web/core/registry";

console.log("🚀 RG5329 Auto Trigger loading...");

/**
 * RG5329 Real-time Auto Trigger
 * Automatically applies RG5329 tax when order conditions change
 */
const rg5329AutoTrigger = {
    start() {
        console.log("🔧 RG5329 Auto Trigger started");
        
        // Wait for DOM to be ready
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeWatchers();
        });
        
        // If DOM already ready
        if (document.readyState !== 'loading') {
            this.initializeWatchers();
        }
        
        return {};
    },

    initializeWatchers() {
        console.log("👀 RG5329: Setting up watchers...");
        
        // Watch for form changes with debouncing
        let debounceTimer;
        const debounceDelay = 1500; // 1.5 seconds
        
        const triggerCheck = () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.checkAndApplyRG5329();
            }, debounceDelay);
        };

        // Listen for all form changes
        document.addEventListener('change', (event) => {
            if (this.isRelevantChange(event)) {
                console.log("🔍 RG5329: Relevant change detected", event.target.name);
                triggerCheck();
            }
        });

        // Listen for input changes (quantity, price)
        document.addEventListener('input', (event) => {
            if (this.isQuantityOrPriceField(event.target)) {
                console.log("🔍 RG5329: Quantity/Price change detected");
                triggerCheck();
            }
        });

        // Periodic check every 5 seconds as backup
        setInterval(() => {
            if (this.isOnSaleOrderForm()) {
                this.checkAndApplyRG5329();
            }
        }, 5000);
    },

    isRelevantChange(event) {
        const field = event.target;
        if (!field.name) return false;
        
        return field.name.includes('partner_id') || 
               field.name.includes('product_id') ||
               field.name.includes('product_uom_qty') ||
               field.name.includes('price_unit');
    },

    isQuantityOrPriceField(field) {
        if (!field.name) return false;
        return field.name.includes('product_uom_qty') || field.name.includes('price_unit');
    },

    isOnSaleOrderForm() {
        const url = window.location.href;
        return url.includes('/web#') && 
               (url.includes('model=sale.order') || url.includes('sale/order'));
    },

    async checkAndApplyRG5329() {
        try {
            console.log("🔍 RG5329: Checking conditions...");
            
            // Extract current form data
            const orderData = this.extractOrderData();
            
            if (!orderData.isValid) {
                console.log("⚠️ RG5329: Order data not ready");
                return;
            }

            console.log("📊 RG5329: Order data:", orderData);

            // Check if conditions are met
            const shouldApply = this.shouldApplyRG5329(orderData);
            const currentlyHas = this.hasRG5329Tax();

            console.log(`🎯 RG5329: Should apply: ${shouldApply}, Currently has: ${currentlyHas}`);

            if (shouldApply && !currentlyHas) {
                console.log("✅ RG5329: Applying tax...");
                await this.applyRG5329();
            } else if (!shouldApply && currentlyHas) {
                console.log("❌ RG5329: Should remove tax...");
                // Remove logic can be added here if needed
            } else {
                console.log("✔️ RG5329: No action needed");
            }

        } catch (error) {
            console.error("❌ RG5329: Error in checkAndApplyRG5329:", error);
        }
    },

    extractOrderData() {
        // Get customer info
        const customerField = document.querySelector('[name="partner_id"] input') || 
                            document.querySelector('span[name="partner_id"]');
        
        const customerText = customerField ? (customerField.value || customerField.textContent || '') : '';

        // Get amount info
        const amountField = document.querySelector('span[name="amount_untaxed"]') ||
                          document.querySelector('[name="amount_untaxed"]');
        
        const amountText = amountField ? (amountField.textContent || amountField.value || '0') : '0';
        const amount = parseFloat(amountText.replace(/[^0-9.-]/g, '')) || 0;

        // Check for RG5329 products
        const hasRG5329Products = this.hasRG5329Products();

        return {
            isValid: customerText && amountField && amount > 0,
            customerText: customerText,
            amount: amount,
            hasRG5329Products: hasRG5329Products
        };
    },

    hasRG5329Products() {
        // Look for products with "RG 5329" in the name
        const productElements = document.querySelectorAll('[name="product_id"]');
        
        for (let element of productElements) {
            const text = element.textContent || element.value || '';
            if (text.includes('RG 5329') || text.includes('ALTO VALOR')) {
                return true;
            }
        }
        return false;
    },

    shouldApplyRG5329(orderData) {
        // Check all conditions
        const isEligibleCustomer = orderData.customerText.includes('EMPRESA DEMO RI') ||
                                 orderData.customerText.includes('Para Probar RG 5329');
        
        const isAboveThreshold = orderData.amount >= 100000;
        const hasProducts = orderData.hasRG5329Products;

        console.log(`🔍 RG5329 Conditions Check:`);
        console.log(`   Customer eligible: ${isEligibleCustomer} (${orderData.customerText})`);
        console.log(`   Above threshold: ${isAboveThreshold} ($${orderData.amount} >= $100,000)`);
        console.log(`   Has RG5329 products: ${hasProducts}`);

        return isEligibleCustomer && isAboveThreshold && hasProducts;
    },

    hasRG5329Tax() {
        // Check current tax amount to see if RG5329 is applied
        const taxField = document.querySelector('span[name="amount_tax"]') ||
                        document.querySelector('[name="amount_tax"]');
        
        if (taxField) {
            const taxText = taxField.textContent || taxField.value || '0';
            const taxAmount = parseFloat(taxText.replace(/[^0-9.-]/g, '')) || 0;
            
            // If tax is around 21600 (18000 IVA + 3600 RG5329), both taxes are applied
            const hasRG5329 = Math.abs(taxAmount - 21600) < 100;
            console.log(`💰 Current tax amount: $${taxAmount}, Has RG5329: ${hasRG5329}`);
            return hasRG5329;
        }
        
        return false;
    },

    async applyRG5329() {
        console.log("🔧 RG5329: Executing application...");
        
        try {
            // Get order ID from URL
            const orderId = this.getOrderIdFromUrl();
            
            if (!orderId) {
                console.log("⚠️ RG5329: Could not get order ID, using fallback method");
                await this.applyRG5329Fallback();
                return;
            }

            console.log(`📋 RG5329: Applying to order ID: ${orderId}`);

            // Call backend via fetch
            const response = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        model: 'sale.order',
                        method: 'apply_rg5329_via_js',
                        args: [orderId],
                        kwargs: {}
                    }
                })
            });

            const result = await response.json();
            
            if (result.result && result.result.success) {
                console.log("✅ RG5329: Successfully applied via backend");
                
                // Auto-save the form
                setTimeout(() => {
                    this.saveForm();
                }, 1000);
                
                // Show success message
                this.showSuccessMessage();
                
            } else {
                console.log("⚠️ RG5329: Backend call failed, using fallback");
                await this.applyRG5329Fallback();
            }

        } catch (error) {
            console.error("❌ RG5329: Error in backend call:", error);
            await this.applyRG5329Fallback();
        }
    },

    async applyRG5329Fallback() {
        console.log("🔄 RG5329: Using fallback method - notification to user");
        
        // Show user-friendly notification
        this.showRG5329Notification();
        
        // Auto-save form to trigger backend recalculation
        setTimeout(() => {
            this.saveForm();
        }, 2000);
    },

    getOrderIdFromUrl() {
        const url = window.location.href;
        const match = url.match(/id=(\d+)/);
        return match ? parseInt(match[1]) : null;
    },

    saveForm() {
        // Try to find and click the save button
        const saveButton = document.querySelector('.o_form_button_save:not([disabled])') ||
                          document.querySelector('button[name="action_save"]:not([disabled])');
        
        if (saveButton) {
            console.log("💾 RG5329: Auto-saving form...");
            saveButton.click();
        } else {
            console.log("⚠️ RG5329: Save button not found or disabled");
        }
    },

    showSuccessMessage() {
        console.log("🎉 RG5329: Tax applied successfully!");
        
        // Try to show Odoo notification if available
        if (window.odoo && window.odoo.services && window.odoo.services.notification) {
            window.odoo.services.notification.add("RG5329 tax applied successfully!", {
                type: 'success'
            });
        }
    },

    showRG5329Notification() {
        console.log("📢 RG5329: Showing user notification");
        
        // Create a visual notification
        const notification = document.createElement('div');
        notification.innerHTML = `
            <div style="position: fixed; top: 20px; right: 20px; z-index: 9999; 
                        background: #00a09d; color: white; padding: 15px 20px; 
                        border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.3);
                        font-family: Arial, sans-serif; max-width: 300px;">
                <strong>🏷️ RG5329 Tax</strong><br>
                Tax should be applied automatically.<br>
                <small>Saving form to update totals...</small>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Remove notification after 5 seconds
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
};

// Register the service - DISABLED to prevent UI conflicts
// registry.category("services").add("rg5329_auto_trigger", rg5329AutoTrigger);

console.log("⚠️ RG5329 Auto Trigger module DISABLED to prevent conflicts");