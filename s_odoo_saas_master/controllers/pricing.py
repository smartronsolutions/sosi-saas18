import requests
import time
from odoo import http, _
from odoo.http import request
from odoo.tools import groupby

from odoo.addons.website_sale.controllers.main import WebsiteSale

import logging
_logger = logging.getLogger(__name__)


class Pricing(http.Controller):

    def _get_pricelist_context(self):
        pricelist_context = dict(request.env.context)
        if not pricelist_context.get('pricelist'):
            pricelist = request.website._get_current_pricelist()
            pricelist_context['pricelist'] = pricelist.id
        else:
            pricelist = request.env['product.pricelist'].browse(pricelist_context['pricelist'])
        if not pricelist:
            pricelist = request.env['product.pricelist'].search([('company_id', '=', request.website.company_id.id)], limit=1)

        return pricelist_context, pricelist, request.env['product.pricelist'].search([])

    def _format_price(self, val):
        if val is None:
            return '0'
        val = float(val)
        if val.is_integer():
            return f"{int(val):,}"
        return f"{val:,.2f}"

    def _get_plan_product(self, plan_name):
        Product = request.env['product.product'].sudo()
        prod = Product.search([('default_code', '=ilike', plan_name), ('active', '=', True)], limit=1)
        if not prod:
            prod = Product.search([('name', '=ilike', plan_name), ('active', '=', True)], limit=1)
        if not prod:
            try:
                prod = request.env.ref(f's_odoo_saas_master.product_saas_plan_{plan_name.lower()}').sudo()
            except Exception:
                pass
        return prod

    def _get_user_product(self):
        Product = request.env['product.product'].sudo()
        prod = Product.search([('default_code', '=ilike', 'saas_user'), ('active', '=', True)], limit=1)
        if not prod:
            prod = Product.search([('is_saas_user', '=', True), ('active', '=', True)], limit=1)
        if not prod:
            try:
                prod = request.env.ref('s_odoo_saas_master.product_saas_user').sudo()
            except Exception:
                pass
        if not prod:
            prod = Product.search([('name', 'ilike', 'SaaS User'), ('active', '=', True)], limit=1)
        return prod

    @http.route([
        '''/pricing''',
        '''/saas/pricing''',
        '''/my/saas/pricing'''
    ], type='http', auth="public", website=True)
    def pricing(self, **post):
        pricelist_context, pricelist, pricelists = self._get_pricelist_context()
        partner = request.env.user.partner_id
        request.update_context(pricelist=pricelist.id, partner=partner)

        domains = request.env['saas.based.domain'].sudo().search([])
        ProductObj = request.env['product.product'].sudo()

        # Dynamic Plan products lookup (Essential / Growth)
        essential_product = self._get_plan_product('Essential')
        essential_monthly_price = float(essential_product.list_price) if (essential_product and essential_product.list_price) else 14900.0
        essential_annual_price = round(essential_monthly_price * 12 * 0.85, 2)

        growth_product = self._get_plan_product('Growth')
        growth_monthly_price = float(growth_product.list_price) if (growth_product and growth_product.list_price) else 39900.0
        growth_annual_price = round(growth_monthly_price * 12 * 0.85, 2)

        # Dynamic User product lookup
        user_product = self._get_user_product()
        user_monthly_price = float(user_product.list_price) if (user_product and user_product.list_price) else 100.0
        user_annual_price = round(user_monthly_price * 12 * 0.85, 2)
        user_annual_per_month = round(user_monthly_price * 0.85, 2)

        essential_monthly_fmt = self._format_price(essential_monthly_price)
        essential_annual_fmt = self._format_price(essential_annual_price)
        growth_monthly_fmt = self._format_price(growth_monthly_price)
        growth_annual_fmt = self._format_price(growth_annual_price)
        user_monthly_fmt = self._format_price(user_monthly_price)
        user_annual_fmt = self._format_price(user_annual_price)
        user_annual_per_month_fmt = self._format_price(user_annual_per_month)

        data = {
            'user': {},
            'categs': []
        }
        
        data['user'].update({
            'id': user_product.id if user_product else False,
            'monthly_price': user_monthly_price,
            'yearly_price': user_annual_price,
        })
        all_products = ProductObj.search([
            ('is_published', '=', True),
            ('can_be_user_app', '=', True),
            ('is_saas_user', '=', False),
        ], order='website_sequence, id')
        for cate, products in groupby(all_products, key=lambda p: p.ecom_category_id):
            if not products or len(products) == 0:
                continue
            app_list = []
            for product in products:
                app_monthly_price = pricelist.with_context(subscription_type='monthly')._get_product_price(product, 1)
                app_list.append({
                    'id': product.id,
                    'name': product.name,
                    'tech_name': product.technical_name,
                    'image': request.website.image_url(product, 'image_256'),
                    'monthly_price': app_monthly_price,
                    'yearly_price': app_monthly_price * 12,
                })
            data['categs'].append({
                'id': cate.id,
                'name': cate.name,
                'apps': app_list
            })

        values = {
            'page_name': 'saas_pricing',
            'partner': partner,
            'domains': domains,
            'pricelist': pricelist,
            'pricelists': pricelists,
            'data': data,
            'currency_symbol': pricelist.currency_id.symbol or 'XPF',
            # Plans
            'essential_product': essential_product,
            'essential_monthly_price': essential_monthly_price,
            'essential_annual_price': essential_annual_price,
            'essential_monthly_price_formatted': essential_monthly_fmt,
            'essential_annual_price_formatted': essential_annual_fmt,
            'growth_product': growth_product,
            'growth_monthly_price': growth_monthly_price,
            'growth_annual_price': growth_annual_price,
            'growth_monthly_price_formatted': growth_monthly_fmt,
            'growth_annual_price_formatted': growth_annual_fmt,
            # Users
            'user_product': user_product,
            'user_product_id': user_product.id if user_product else False,
            'user_monthly_price': user_monthly_price,
            'user_annual_price': user_annual_price,
            'user_annual_per_month': user_annual_per_month,
            'user_monthly_price_formatted': user_monthly_fmt,
            'user_annual_price_formatted': user_annual_fmt,
            'user_annual_per_month_formatted': user_annual_per_month_fmt,
        }
        return request.render("s_odoo_saas_master.portal_pricing_page", values)

    @http.route(['/pricing/get-saas-pricelist'], type='json', auth='public')
    def get_saas_pricelist(self, pricelist_id):
        products = request.env['product.product'].sudo().search([('is_published', '=', True)])
        products |= request.env.ref('s_odoo_saas_master.product_saas_user').sudo()
        pricelist = request.env['product.pricelist'].sudo().browse(pricelist_id)
        qty = [1] * len(products)
        
        monthly_pricelist = pricelist.with_context(subscription_type='monthly')._get_products_price(products, qty)
        monthly_pricelist = {k: float(v or 0) for k, v in monthly_pricelist.items()}
        
        # Recalculate yearly as 12x monthly
        yearly_pricelist_calculated = {k: v * 12 for k, v in monthly_pricelist.items()}
        
        return {
            'monthly_pricelist': monthly_pricelist,
            'yearly_pricelist': yearly_pricelist_calculated,
            'currency': {
                'id': pricelist.currency_id.id,
                'symbol': pricelist.currency_id.symbol or 'XPF',
                'decimal_places': pricelist.currency_id.decimal_places or 2,
                'position': pricelist.currency_id.position or 'after',
            },
        }

    @http.route(['/pricing/get-required-apps'], type='json', auth='public')
    def get_required_apps(self, app_id):
        product = request.env['product.product'].sudo().browse(app_id)
        return product.get_required_products()

    @http.route(['/pricing/get-dependent-apps'], type='json', auth='public')
    def get_dependent_apps(self, app_id):
        product = request.env['product.product'].sudo().browse(app_id)
        return product.get_dependent_products()

    @http.route(['/pricing/check-domain'], type='json', auth='public')
    def check_saas_domain(self, sub_domain, domain_id):
        instance = request.env['saas.odoo.instance'].sudo().search([
            ('name', '=', sub_domain),
            ('based_domain_id', '=', domain_id),
        ], limit=1)
        if instance:
            error = _("Your sub-domain has already been taken. Please choose another one.")
            return {
                'success': False,
                'error': error,
            }
        return {'success': True}

    @http.route(['/pricing/check-trial'], type='json', auth='user', website=True)
    def check_trial(self):
        if request.env.user.partner_id.trial_instance_count >= request.website.company_id.limit_trial:
            return False
        return True

    @http.route(['/pricing/checkout'], type='http', methods=['POST'], auth="public", website=True)
    def checkout(self, **post):
        pricelist = request.website._get_current_pricelist()
        num_users = int(post.pop('num_users', 1))
        subscription_type = post.pop('price_by', 'yearly')
        plan_name = post.pop('plan', 'Essential')
        plan_product_id = post.pop('plan_product_id', False)

        if not plan_product_id:
            plan_product = self._get_plan_product(plan_name)
            if plan_product:
                plan_product_id = plan_product.id
        else:
            try:
                plan_product_id = int(plan_product_id)
            except (ValueError, TypeError):
                plan_product = self._get_plan_product(plan_name)
                plan_product_id = plan_product.id if plan_product else False

        app_ids = []
        for key, val in post.items():
            if key.startswith('app_') and val == 'on':
                app_id = int(key[4:])
                app_ids.append(app_id)
        
        post['partner'] = request.env.user.partner_id
        post['domain_id'] = post.get('domain')
        post['users_count'] = num_users
        post['plan_name'] = plan_name
        post['plan_product_id'] = plan_product_id
        post['app_ids'] = app_ids
        post['subscription_type'] = subscription_type
        post['pricelist'] = pricelist
        
        # Create order (Plan line and User line are created with exact discounted prices)
        order = request.website.create_saas_order(post)
                
        request.session['sale_order_id'] = order.id
        return request.redirect('/shop/checkout?express=1')

    @http.route('/saas/instance/create-trial', type='json', auth='user')
    def instance_create(self, instance_vals, **kwargs):
        base_domain_id = instance_vals['base_domain_id']
        base_domain = request.env['saas.based.domain'].sudo().browse(base_domain_id)

        default_app_ids = instance_vals['default_app_ids']        
        app_ids = []
        for app_id in default_app_ids:
            if isinstance(app_id, str) and app_id.startswith('app_'):
                app_ids.append(int(app_id[4:]))
            else:
                app_ids.append(int(app_id))
                
        apps = request.env['product.product'].sudo().browse(app_ids)
        default_modules = apps.mapped('technical_name')

        instance_vals['base_domain'] = base_domain
        instance_vals['default_modules'] = default_modules
        instance_vals['partner'] = request.env.user.partner_id
        instance_vals['trial'] = True
        instance_vals = request.env['saas.odoo.instance'].sudo()._prepare_instance_val_to_create(instance_vals)
        instance = request.env['saas.odoo.instance'].sudo().create(instance_vals)
        instance.action_deploy()
        return {'id': instance.id}


NON_REQUIRED_FIELDS = ['street', 'city']


class SaasPayment(WebsiteSale):

    @http.route(['/shop/confirmation'], type='http')
    def shop_payment_confirmation(self, **post):
        sale_order_id = request.session.get('sale_last_order_id')
        if sale_order_id:
            order = request.env['sale.order'].sudo().browse(sale_order_id)
            if order.is_saas_order and order.instance_id:
                try:
                    if order.invoice_status == 'to invoice':
                        invoice = order._create_saas_invoice()
                        invoice._post()
                        invoice._auto_paid_saas_invoice()
                    return request.redirect('/my/saas/odoo-instance/%s' % order.instance_id.id)
                except Exception as ex:
                    order.instance_id._action_cancel()
                    order.instance_id.unlink()
                    _logger.exception(ex)

        return super(SaasPayment, self).shop_payment_confirmation(post=post)

    def _redirect_instance_url(self, instance):
        response = requests.get(instance.url)
        tried_count = 1
        while response.status_code != 200 and tried_count <= 15:
            time.sleep(2)
            response = requests.get(instance.url)
        return request.redirect(instance.url, local=False)

    def _get_country_related_render_values(self, kw, render_values):
        res = super(SaasPayment, self)._get_country_related_render_values(kw, render_values)
        order = render_values['website_sale_order']
        res['lang'] = order.partner_id.lang
        res['languages'] = request.env['res.lang'].get_installed()
        return res

    def _get_mandatory_fields_billing(self, country_id=False):
        req = super(SaasPayment, self)._get_mandatory_fields_billing(country_id)
        req = list(set(req) - set(NON_REQUIRED_FIELDS))
        return req

    def _get_mandatory_fields_shipping(self, country_id=False):
        req = super(SaasPayment, self)._get_mandatory_fields_shipping(country_id)
        req = list(set(req) - set(NON_REQUIRED_FIELDS))
        return req
