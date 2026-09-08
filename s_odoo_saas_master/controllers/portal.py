from collections import OrderedDict
from datetime import datetime, date
import logging
import werkzeug.exceptions

from odoo import http, fields, _
from odoo.osv import expression
from odoo.exceptions import MissingError, UserError
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request, content_disposition

_logger = logging.getLogger(__name__)


class PortalInstance(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'instance_count' in counters:
            values['instance_count'] = request.env.user.partner_id.instance_count
        return values

    def _get_instance_searchbar_sortings(self):
        return {
            'date': {'label': _('Expiration Date'), 'order': 'expiration_date desc'},
            'state': {'label': _('Status'), 'order': 'state'},
        }

    def _get_instance_searchbar_filters(self):
        return {
            'all': {'label': _('All'), 'domain': []},
            'deploy': {'label': _('Deployed'), 'domain': [('state', '=', 'deploy')]},
            'suspend': {'label': _('Suspended'), 'domain': [('state', '=', 'suspend')]},
            'cancel': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancel')]},
        }

    def _get_instances_domain(self):
        return [('partner_id', '=', request.env.user.partner_id.id)]

    def _validate_instance(self, instance):
        user = request.env.user
        if not instance or not instance.exists():
            raise werkzeug.exceptions.NotFound()
        if not user._is_admin() and instance.partner_id.id != user.partner_id.id:
            raise werkzeug.exceptions.Forbidden(_("Access Denied"))

    # -------------------------------------------------------------------------
    # My Account Portal Override
    # -------------------------------------------------------------------------
    @http.route(['/my', '/my/home'], type='http', auth="user", website=True)
    def home(self, **kw):
        partner = request.env.user.partner_id
        instances = request.env['saas.odoo.instance'].sudo().search([
            ('partner_id', '=', partner.id)
        ], order='id desc')

        total_instances = len(instances)
        online_instances = len(instances.filtered(lambda i: i.operation_state == 'run' and i.state == 'deploy'))
        stopped_instances = len(instances.filtered(lambda i: i.operation_state == 'stop' or i.state == 'suspend'))
        total_users = sum(instances.mapped('active_user'))

        recent_backups = request.env['saas.odoo.instance.backup'].sudo().search([
            ('instance_id', 'in', instances.ids)
        ], order='datetime desc', limit=5)

        recent_messages = request.env['mail.message'].sudo().search([
            ('model', '=', 'saas.odoo.instance'),
            ('res_id', 'in', instances.ids),
        ], order='date desc', limit=6)

        earliest_expiry = False
        active_instances = instances.filtered(lambda i: i.expiration_date and i.state in ('deploy', 'suspend'))
        if active_instances:
            dates = active_instances.mapped('expiration_date')
            earliest_expiry = min(dates)
        
        days_left = None
        if earliest_expiry:
            days_left = (earliest_expiry - date.today()).days

        values = {
            'page_name': 'saas_dashboard',
            'partner': partner,
            'instances': instances,
            'total_instances': total_instances,
            'online_instances': online_instances,
            'stopped_instances': stopped_instances,
            'total_users': total_users,
            'earliest_expiry': earliest_expiry,
            'days_left': days_left,
            'recent_backups': recent_backups,
            'recent_messages': recent_messages,
            'today': date.today(),
        }
        return request.render("s_odoo_saas_master.portal_customer_dashboard", values)

    @http.route(['/my/saas/odoo-instances'], type='http', auth="user", website=True)
    def portal_my_instances(self, sortby=None, filterby=None, **kw):
        values = self._prepare_my_instances_values(sortby, filterby)
        return request.render("s_odoo_saas_master.portal_my_instances", values)

    @http.route(['/my/saas/odoo-instance/<int:instance_id>'], type='http', auth="user", website=True)
    def portal_my_instance_detail(self, instance_id, access_token=None, **kw):
        values = self._instance_get_page_view_values(instance_id, access_token, **kw)
        return request.render("s_odoo_saas_master.portal_instance_page", values)

    @http.route(['/my/saas/settings'], type='http', auth="user", website=True)
    def portal_saas_settings(self, **kw):
        partner = request.env.user.partner_id
        instances = request.env['saas.odoo.instance'].sudo().search([
            ('partner_id', '=', partner.id)
        ], order='id desc')
        values = {
            'page_name': 'saas_settings',
            'partner': partner,
            'instances': instances,
            'user': request.env.user,
        }
        return request.render("s_odoo_saas_master.portal_settings_page", values)

    @http.route(['/saas/pricing', '/my/saas/pricing'], type='http', auth="public", website=True)
    def portal_saas_pricing(self, **kw):
        domains = request.env['saas.based.domain'].sudo().search([])
        values = {
            'page_name': 'saas_pricing',
            'partner': request.env.user.partner_id if request.env.user and not request.env.user._is_public() else False,
            'domains': domains,
        }
        return request.render("s_odoo_saas_master.portal_pricing_page", values)

    def _prepare_my_instances_values(self, sortby, filterby, domain=None, url="/my/saas/odoo-instances"):
        values = self._prepare_portal_layout_values()
        domain = expression.AND([
            domain or [],
            self._get_instances_domain(),
        ])

        searchbar_sortings = self._get_instance_searchbar_sortings()
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        searchbar_filters = self._get_instance_searchbar_filters()
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        instances = request.env['saas.odoo.instance'].sudo().search(domain, order=order)

        values.update({
            'instances': instances,
            'page_name': 'instance',
            'default_url': url,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
            'today': date.today(),
        })

        return values

    def _instance_get_page_view_values(self, instance_id, access_token, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        managing_ip = ''
        if instance.pserver_id:
            try:
                managing_ip = instance.pserver_id._get_managing_ip()
            except Exception:
                managing_ip = '127.0.0.1'

        days_left = None
        if instance.expiration_date:
            days_left = (instance.expiration_date - date.today()).days

        recent_messages = request.env['mail.message'].sudo().search([
            ('model', '=', 'saas.odoo.instance'),
            ('res_id', '=', instance.id),
        ], order='date desc', limit=8)

        values = {
            'page_name': 'instance_detail',
            'instance': instance,
            'installed_apps': instance.installed_app_ids,
            'managing_ip': managing_ip,
            'days_left': days_left,
            'recent_messages': recent_messages,
            'today': date.today(),
        }
        return self._get_page_view_values(instance, access_token, values, 'my_instances_history', False, **kwargs)

    @http.route('/saas/instance/stop', type='json', auth='user')
    def instance_stop(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if instance.state != 'deploy':
            return False
        self._validate_instance(instance)
        instance.action_stop()
        return True

    @http.route('/saas/instance/deploy', type='json', auth='user')
    def instance_deploy(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if instance.state != 'draft' and not instance.buy_now_from_pricing:
            return False
        self._validate_instance(instance)
        instance.action_deploy()
        return True
    
    @http.route('/saas/instance/start', type='json', auth='user')
    def instance_start(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if instance.state != 'deploy':
            return False
        self._validate_instance(instance)
        instance.action_start()
        return True

    @http.route('/saas/instance/restart', type='json', auth='user')
    def instance_restart(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if instance.state != 'deploy':
            return False
        self._validate_instance(instance)
        instance.action_restart()
        return True

    @http.route('/saas/instance/create-backup', type='json', auth='user')
    def instance_create_backup(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        instance.action_backup()
        return True

    @http.route([
        '/my/instance/<int:instance_id>/download-backup',
        '/my/instance/<int:instance_id>/download-backup/<int:backup_id>'
    ], type='http', auth='user')
    def instance_download_backup(self, instance_id, backup_id=None, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        backup = False
        if not backup_id:
            backup = instance.backup_ids.sorted('datetime', reverse=True)[:1]
        else:
            backup = request.env['saas.odoo.instance.backup'].sudo().browse(backup_id) & instance.backup_ids
        if not backup:
            raise MissingError(_("Backup does not exist."))
        try:
            headers = [
                ('Content-Type', 'application/octet-stream; charset=binary'),
                ('Content-Disposition', content_disposition(backup.name)),
            ]
            with open(backup.file_path, mode='rb') as f:
                stream = f.read()
            response = request.make_response(stream, headers=headers)
            return response
        except Exception as e:
            error = "Download backup error: %s" % (str(e) or repr(e))
            _logger.exception(error)
            return self.portal_my_instance_detail(instance_id)

    @http.route(['/saas/instance/check-domain-name'], type='json', auth='user')
    def instance_check_domain_name(self, domain_name):
        instance_domain_name = request.env['saas.odoo.instance.domain.name'].sudo().search([
            ('name', '=', domain_name),
        ], limit=1)
        if instance_domain_name:
            error = _("Your domain name has already been taken. Please choose another one.")
            return {
                'success': False,
                'error': error,
            }
        return {'success': True}

    @http.route('/saas/instance/remove-domain-name', type='json', auth='user')
    def instance_remove_domain_name(self, domain_name_id, **kwargs):
        domain_name = request.env['saas.odoo.instance.domain.name'].sudo().browse(domain_name_id)
        self._validate_instance(domain_name.instance_id)
        domain_name.action_cancel()
        domain_name.unlink()
        return True

    @http.route('/saas/instance/add-domain-name', type='json', auth='user')
    def instance_add_domain_name(self, instance_id, domain_name, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        instance_domain_name = request.env['saas.odoo.instance.domain.name'].sudo().create({
            'instance_id': instance_id,
            'name': domain_name,
        })
        instance_domain_name.action_deploy()
        return True

    @http.route('/saas/instance/get-app-and-user', type='json', auth='user')
    def instance_get_app_and_user(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if instance.state != 'deploy':
            return False
        self._validate_instance(instance)
        instance.action_get_active_users()
        instance.action_get_installed_apps()
        return True

    @http.route('/saas/instance/suspend', type='json', auth='user')
    def instance_suspend(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        instance.action_suspend()
        return {'success': True, 'state': 'suspend', 'operation_state': 'stop'}

    @http.route('/saas/instance/redeploy', type='json', auth='user')
    def instance_redeploy(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        try:
            instance.action_redeploy_latest()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/saas/instance/github-connect', type='json', auth='user')
    def instance_github_connect(self, instance_id, repo_url, branch='main', token=None, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        try:
            instance.action_connect_github(repo_url=repo_url, branch=branch, token=token)
            return {
                'success': True,
                'repo_url': instance.github_repo_url,
                'branch': instance.github_branch or 'main',
                'connected': instance.github_connected,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/saas/instance/github-disconnect', type='json', auth='user')
    def instance_github_disconnect(self, instance_id, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        try:
            instance.action_disconnect_github()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/saas/instance/live-logs', type='json', auth='user')
    def instance_live_logs(self, instance_id, lines=100, **kwargs):
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        self._validate_instance(instance)
        logs = instance.action_get_live_logs(lines=lines)
        return {'success': True, 'logs': logs}

    @http.route('/saas/settings/save', type='json', auth='user')
    def saas_settings_save(self, **kwargs):
        partner = request.env.user.partner_id
        vals = {}
        if 'companyName' in kwargs and kwargs['companyName']:
            vals['company_name'] = kwargs['companyName'].strip()
        if 'phone' in kwargs:
            vals['phone'] = kwargs['phone'].strip()
        if 'accountEmail' in kwargs and kwargs['accountEmail']:
            vals['email'] = kwargs['accountEmail'].strip()
        if vals:
            partner.sudo().write(vals)
        return {'success': True}
