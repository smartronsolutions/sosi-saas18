from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def create_saas_order(self, data):
        vals = self.sudo()._prepare_saas_order_vals(data)
        order = self.env['sale.order'].sudo().create(vals)
        # order.action_quotation_send()
        return order

    def _prepare_saas_order_vals(self, data):
        pricelist = data.get('pricelist')
        subscription_type = data.get('subscription_type', 'yearly')
        partner = data.get('partner')
        sub_domain = data.get('sub_domain')
        domain_id = int(data.get('domain_id')) if data.get('domain_id') else False
        users_count = int(data.get('users_count', 1))
        plan_product_id = data.get('plan_product_id')
        plan_name = data.get('plan_name') or data.get('plan')
        app_ids = data.get('app_ids', [])
        buy_now_from_pricing = data.get('buy_now_from_pricing', False)
        self.ensure_one()

        order_vals = self._prepare_sale_order_values(partner_sudo=partner)
        order_vals.update({
            'subscription_type': subscription_type,
            'is_saas_order': True,
            'subdomain': sub_domain,
            'based_domain_id': domain_id,
            'buy_now_from_pricing': True if buy_now_from_pricing == 'on' else False,
        })
        order_line_vals = []

        is_annual = (subscription_type == 'yearly')
        multiplier = (12 * 0.85) if is_annual else 1.0  # 15% discount for annual!

        Product = self.env['product.product'].sudo()

        # 1. Plan product line (Essential / Growth)
        plan_product = False
        if plan_product_id:
            plan_product = Product.browse(int(plan_product_id))
        if (not plan_product or not plan_product.exists()) and plan_name:
            plan_product = Product.search([('default_code', '=ilike', plan_name), ('active', '=', True)], limit=1)
            if not plan_product:
                plan_product = Product.search([('name', '=ilike', plan_name), ('active', '=', True)], limit=1)
            if not plan_product:
                try:
                    plan_product = self.sudo().env.ref(f's_odoo_saas_master.product_saas_plan_{plan_name.lower()}')
                except Exception:
                    pass

        if plan_product and plan_product.exists():
            plan_base_price = float(plan_product.list_price or 0.0)
            plan_unit_price = round(plan_base_price * multiplier, 2)
            order_line_vals.append((0, 0, {
                'product_id': plan_product.id,
                'name': f"{plan_product.name} ({'Annual - 15% OFF' if is_annual else 'Monthly'})",
                'product_uom_qty': 1,
                'product_uom': plan_product.uom_id.id,
                'price_unit': plan_unit_price,
                'tax_id': [(6, 0, plan_product.taxes_id.ids)],
            }))

        # 2. Users line (SaaS User)
        user_product = False
        try:
            user_product = self.sudo().env.ref('s_odoo_saas_master.product_saas_user')
        except Exception:
            pass
        if not user_product or not user_product.exists():
            user_product = Product.search([('default_code', '=ilike', 'saas_user'), ('active', '=', True)], limit=1)
        if not user_product or not user_product.exists():
            user_product = Product.search([('is_saas_user', '=', True), ('active', '=', True)], limit=1)
        if not user_product or not user_product.exists():
            user_product = Product.search([('name', 'ilike', 'SaaS User'), ('active', '=', True)], limit=1)

        if user_product and user_product.exists():
            user_base_price = float(user_product.list_price or 100.0)
            user_unit_price = round(user_base_price * multiplier, 2)
            order_line_vals.append((0, 0, {
                'product_id': user_product.id,
                'name': f"{user_product.name} ({'Annual - 15% OFF' if is_annual else 'Monthly'})",
                'product_uom_qty': users_count,
                'product_uom': user_product.uom_id.id,
                'price_unit': user_unit_price,
                'tax_id': [(6, 0, user_product.taxes_id.ids)],
            }))

        # 3. Apps lines
        for app_id in app_ids:
            app_product = Product.browse(app_id)
            if app_product and app_product.exists():
                app_base_price = float(app_product.list_price or 0.0)
                app_unit_price = round(app_base_price * multiplier, 2)
                order_line_vals.append((0, 0, {
                    'product_id': app_id,
                    'product_uom_qty': 1,
                    'product_uom': app_product.uom_id.id,
                    'price_unit': app_unit_price,
                    'tax_id': [(6, 0, app_product.taxes_id.ids)],
                }))

        order_vals['order_line'] = order_line_vals
        return order_vals
