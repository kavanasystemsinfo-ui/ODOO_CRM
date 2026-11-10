"""Simulador de la empresa viva: cada tramo de la jornada pasa algo real.

Muebles del Hogar S.L. trabaja sola. En cada tramo (ver simulador_plan.TRAMOS)
entran leads, los comerciales hablan con clientes y cierran llamadas, se
mandan y confirman presupuestos, se entrega, se factura lo entregado, se cobra,
se compra lo que se agota y se recibe lo comprado. Todo por el ORM y con los
métodos de negocio de Odoo (action_confirm, button_validate, _create_invoices,
el asistente de pagos...), así que las reglas de cada módulo se cumplen igual
que si lo hiciera una persona.

Reglas del simulador:
  * Coherencia antes que volumen: solo se confirma lo que tiene stock, solo se
    factura lo entregado y solo se cobra lo facturado.
  * Reproducible: el tramo «2026-11-10#13» siempre produce el mismo plan.
  * Idempotente: un tramo ya simulado no se repite (parámetro del sistema).
  * Ningún correo puede salir: todas las direcciones usan dominios reservados
    (.example) y los mail.mail que genere el tramo se borran sin enviar.
  * Si al final algo no cuadra (stock negativo, un correo real), el tramo
    entero se deshace.

En la demo lo lanza muebles-jornada.timer a través de panel/jornada.sh, entre
la verificación del laboratorio y la nueva instantánea. No se expone por API:
los métodos son privados y exigen superusuario.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from psycopg2 import errors as pg_errors

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from . import simulador_plan as plan

_logger = logging.getLogger(__name__)

PARAM_ULTIMO = 'odoo_crm.simulador.ultimo_tramo'
PARAM_SANEADO = 'odoo_crm.simulador.saneado'
STOCK_MINIMO = 4      # por debajo de esto (previsto) se pide al proveedor
STOCK_OBJETIVO = 12   # hasta dónde se repone
DIAS_PARA_COBRO = 3
DIAS_PRESUPUESTO_PERDIDO = 30
COMERCIALES = (('laura.ferrer', 'Laura Ferrer'), ('pau.marti', 'Pau Martí'))


class SimuladorEmpresa(models.AbstractModel):
    _name = 'odoo_crm.simulador'
    _description = 'Simulador de la jornada de Muebles del Hogar'

    # ------------------------------------------------------------------ entrada

    @api.model
    def _simular_tramo(self, momento: datetime | None = None) -> dict:
        """Simula el tramo en curso. Devuelve un resumen de lo que ha pasado."""
        if not self.env.is_superuser():
            raise AccessError(_('El simulador solo lo puede lanzar el sistema.'))
        momento = momento or self._ahora_local()
        clave = plan.clave_tramo(momento)
        if clave is None:
            return {'omitido': 'fuera de horario', 'momento': momento.isoformat()}
        ultimo = self._param(PARAM_ULTIMO)
        if clave <= ultimo:
            return {'omitido': f'tramo ya simulado ({ultimo})', 'tramo': clave}

        primer_correo = self.env['mail.mail'].search([], order='id desc', limit=1).id or 0
        resumen = {'tramo': clave, 'incidencias': []}
        if not self._param(PARAM_SANEADO):
            resumen['saneamiento'] = self._paso(resumen, 'saneamiento', self._sanear)
            self._param(PARAM_SANEADO, clave)

        rng = plan.generador(clave)
        cuantos = plan.plan_tramo(clave)
        hoy = momento.date()
        # Lo creado en este tramo no avanza en el mismo tramo: un lead no se
        # cualifica ni un presupuesto se confirma a la hora de nacer.
        nuevos = {'leads': [], 'pedidos': []}
        pasos = (
            ('correos_saneados', self._correos_ficticios),
            ('albaranes_reparados', self._reparar_albaranes),
            ('leads_nuevos', lambda: self._leads_nuevos(rng, cuantos['leads_nuevos'], nuevos)),
            ('cualificaciones', lambda: self._cualificar(cuantos['cualificaciones'], nuevos)),
            ('propuestas', lambda: self._proponer(rng, cuantos['propuestas'], nuevos)),
            ('pedidos_recurrentes', lambda: self._recurrentes(
                rng, cuantos['pedidos_recurrentes'], nuevos)),
            ('correos_cliente', lambda: self._correos_cliente(rng, cuantos['correos_cliente'])),
            ('actividades_hechas', lambda: self._cerrar_actividades(rng, cuantos['actividades_hechas'], hoy)),
            ('actividades_nuevas', lambda: self._planificar_actividades(rng, cuantos['actividades_nuevas'], hoy)),
            ('confirmaciones', lambda: self._confirmar(cuantos['confirmaciones'], nuevos)),
            ('perdidas', lambda: self._perder(cuantos['perdidas'], hoy)),
            ('entregas', lambda: self._entregar(cuantos['entregas'])),
            ('facturas', lambda: self._facturar(cuantos['facturas'], hoy)),
            ('cobros', lambda: self._cobrar(cuantos['cobros'], hoy)),
            ('compras', lambda: self._reponer()),
            ('recepciones', lambda: self._recibir(cuantos['recepciones'], momento)),
            ('facturas_proveedor', lambda: self._facturas_proveedor(cuantos['facturas_proveedor'], hoy)),
        )
        for nombre, paso in pasos:
            resumen[nombre] = self._paso(resumen, nombre, paso)

        self._descartar_correos(primer_correo)
        problemas = self._comprobar_coherencia()
        if problemas:
            raise UserError(_('El tramo %(tramo)s deja la base incoherente: %(p)s',
                              tramo=clave, p='; '.join(problemas)))
        self._param(PARAM_ULTIMO, clave)
        _logger.info('Simulador: tramo %s %s', clave, resumen)
        return resumen

    def _paso(self, resumen: dict, nombre: str, funcion) -> int:
        """Cada paso en su punto de guardado: si falla, se deshace solo ese paso."""
        try:
            with self.env.cr.savepoint():
                resultado = funcion() or 0
                # Los recálculos pendientes se hacen aquí, con el entorno del
                # simulador. Si se dejan para el cierre del punto de guardado,
                # Odoo 20 los hace con otro entorno y el seguimiento de compras
                # («cantidad recibida») no encuentra el producto (MissingError).
                self.env.flush_all()
                return resultado
        except (pg_errors.SerializationFailure, pg_errors.DeadlockDetected):
            # Otro proceso (las tareas programadas de Odoo) tocó lo mismo: el
            # tramo entero se repite con una transacción nueva (simular_tramo.py).
            raise
        except Exception as exc:  # noqa: BLE001 - se informa y se sigue
            # La base volvió al punto de guardado, pero la caché del ORM aún
            # recuerda lo que el paso hizo: se vacía para no arrastrarlo.
            self.env.invalidate_all()
            _logger.warning('Simulador: el paso %s falló: %s', nombre, exc, exc_info=True)
            resumen['incidencias'].append(f'{nombre}: {exc}')
            return 0

    def _param(self, clave: str, valor: str | None = None) -> str:
        """Lee o escribe un parámetro del sistema (Odoo 20: get_str/set_str)."""
        parametros = self.env['ir.config_parameter'].sudo()
        if valor is None:
            if hasattr(parametros, 'get_str'):
                return parametros.get_str(clave) or ''
            return parametros.get_param(clave) or ''
        if hasattr(parametros, 'set_str'):
            parametros.set_str(clave, valor)
        else:
            parametros.set_param(clave, valor)
        return valor

    def _ahora_local(self) -> datetime:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Europe/Madrid')).replace(tzinfo=None)

    # ------------------------------------------------------------- saneamiento

    def _sanear(self) -> int:
        """Una sola vez: deja la base de partida en condiciones de empresa real."""
        cambios = self._crear_comerciales()
        cambios += self._correos_ficticios()
        cambios += self._asignar_proveedores()
        cambios += self._descartar_correos(0)  # la cola heredada tampoco puede salir
        return cambios

    def _crear_comerciales(self) -> int:
        Usuarios = self.env['res.users'].with_context(no_reset_password=True)
        grupo = self.env.ref('sales_team.group_sale_salesman_all_leads')
        campo_grupos = 'group_ids' if 'group_ids' in Usuarios._fields else 'groups_id'
        comerciales = self.env['res.users']
        creados = 0
        for login, nombre in COMERCIALES:
            usuario = Usuarios.with_context(active_test=False).search([('login', '=', login)])
            if not usuario:
                usuario = Usuarios.create({
                    'login': login, 'name': nombre,
                    'email': plan.email_ficticio(nombre, 'mueblesdelhogar.example'),
                    campo_grupos: [(4, self.env.ref('base.group_user').id), (4, grupo.id)],
                })
                creados += 1
            comerciales |= usuario
        visita = Usuarios.search([('login', '=', 'visita')])
        sin_comercial = self.env['crm.lead'].with_context(active_test=False).search(
            ['|', ('user_id', '=', False), ('user_id', 'in', visita.ids)], order='id')
        for i, lead in enumerate(sin_comercial):
            lead.user_id = comerciales[i % len(comerciales)]
        pedidos = self.env['sale.order'].search([('user_id', '=', False)], order='id')
        for i, pedido in enumerate(pedidos):
            pedido.user_id = comerciales[i % len(comerciales)]
        for actividad in self.env['mail.activity'].search([('res_model', '=', 'crm.lead')]):
            lead = self.env['crm.lead'].browse(actividad.res_id).exists()
            if lead and lead.user_id:
                actividad.user_id = lead.user_id
        return creados + len(sin_comercial) + len(pedidos)

    def _correos_ficticios(self) -> int:
        """Los datos de ejemplo traen correos de dominios reales: se sustituyen."""
        cambios = 0
        for socio in self.env['res.partner'].with_context(active_test=False).search(
                [('email', '!=', False)]):
            if plan.es_email_ficticio(socio.email):
                continue
            empresa = socio.commercial_partner_id.name or socio.name
            socio.email = plan.email_ficticio(
                'info' if socio.is_company else socio.name, plan.dominio_ficticio(empresa))
            cambios += 1
        for lead in self.env['crm.lead'].with_context(active_test=False).search(
                [('email_from', '!=', False)]):
            if plan.es_email_ficticio(lead.email_from):
                continue
            if lead.partner_id.email:
                lead.email_from = lead.partner_id.email
            else:
                lead.email_from = plan.email_ficticio(
                    lead.contact_name or 'contacto',
                    plan.dominio_ficticio(lead.partner_name or lead.name))
            cambios += 1
        return cambios

    def _reparar_albaranes(self) -> int:
        """Albaranes pendientes con ubicaciones que su operación ya no usa.

        La demo heredó de una configuración en tres pasos recepciones que iban a
        «Control de calidad» (archivada) y entregas que salían de ahí: al
        validarlas dejaban existencias negativas. Se devuelven a las ubicaciones
        de su tipo de operación y se vuelven a reservar.
        """
        reparados = 0
        for albaran in self.env['stock.picking'].search(
                [('state', 'in', ('waiting', 'confirmed', 'assigned'))]):
            tipo = albaran.picking_type_id
            origen, destino = tipo.default_location_src_id, tipo.default_location_dest_id
            if not origen or not destino or (
                    albaran.location_id == origen and albaran.location_dest_id == destino):
                continue
            albaran.do_unreserve()
            valores = {'location_id': origen.id, 'location_dest_id': destino.id}
            albaran.write(valores)
            albaran.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')).write(valores)
            try:
                with self.env.cr.savepoint():
                    albaran.action_assign()
                    self.env.flush_all()
            except UserError:
                self.env.invalidate_all()
            albaran.message_post(body=_('Ubicaciones corregidas a las de «%s».', tipo.name),
                                 message_type='comment', subtype_xmlid='mail.mt_note')
            reparados += 1
        return reparados

    def _asignar_proveedores(self) -> int:
        """Cada referencia sin proveedor recibe uno, repartido por categoría."""
        proveedores = self.env['res.partner'].search([('supplier_rank', '>', 0)], order='id')
        if not proveedores:
            return 0
        plantillas = self.env['product.template'].search(
            [('is_storable', '=', True), ('seller_ids', '=', False)], order='categ_id, id')
        categorias = plantillas.categ_id.sorted('id')
        for plantilla in plantillas:
            proveedor = proveedores[list(categorias).index(plantilla.categ_id) % len(proveedores)]
            self.env['product.supplierinfo'].create({
                'partner_id': proveedor.id, 'product_tmpl_id': plantilla.id,
                'price': plantilla.standard_price, 'min_qty': 1, 'delay': 5,
            })
        return len(plantillas)

    # ------------------------------------------------------------------- CRM

    def _comerciales(self):
        usuarios = self.env['res.users'].search([('login', 'in', [c[0] for c in COMERCIALES])])
        return usuarios or self.env.user

    def _etapas(self):
        """Nuevo, cualificado y propuesta: las tres primeras etapas no ganadas."""
        etapas = self.env['crm.stage'].search([('is_won', '=', False)], order='sequence, id')
        return etapas[:1], etapas[1:2] or etapas[:1], etapas[2:3] or etapas[1:2] or etapas[:1]

    def _equipo(self):
        return self.env.ref('sales_team.team_sales_department', raise_if_not_found=False)

    def _leads_nuevos(self, rng, cuantos: int, nuevos: dict) -> int:
        nuevo, _calificado, _propuesta = self._etapas()
        comerciales = self._comerciales()
        for _i in range(cuantos):
            contacto = plan.persona(rng)
            particular = rng.random() < 0.3
            empresa = '' if particular else plan.empresa(rng)
            lead = self.env['crm.lead'].create({
                'name': plan.asunto(rng),
                'type': 'lead',
                'contact_name': contacto,
                'partner_name': empresa,
                'email_from': False if particular else plan.email_ficticio(
                    contacto, plan.dominio_ficticio(empresa)),
                'phone': f'+34 6{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}',
                'user_id': rng.choice(comerciales).id,
                'team_id': self._equipo().id if self._equipo() else False,
                'stage_id': nuevo.id,
                'x_es_contrato': not particular and rng.random() < 0.4,
                'x_muestra_pedida': rng.random() < 0.25,
                'x_proyecto_referenciado': not particular and rng.random() < 0.3,
            })
            nuevos['leads'].append(lead.id)
        return cuantos

    def _cualificar(self, cuantos: int, nuevos: dict) -> int:
        _nuevo, calificado, _propuesta = self._etapas()
        leads = self.env['crm.lead'].search(
            [('type', '=', 'lead'), ('id', 'not in', nuevos['leads'])],
            order='create_date, id', limit=cuantos)
        for lead in leads:
            socio = lead.partner_id or self.env['res.partner'].create({
                'name': lead.partner_name or lead.contact_name or lead.name,
                'is_company': bool(lead.partner_name),
                'email': lead.email_from,
                'phone': lead.phone,
            })
            lead.write({'type': 'opportunity', 'partner_id': socio.id,
                        'stage_id': calificado.id, 'email_from': lead.email_from})
            lead.message_post(body=_('Cualificado: hay proyecto y presupuesto.'),
                              message_type='comment', subtype_xmlid='mail.mt_note')
        return len(leads)

    def _productos_con_stock(self):
        return self.env['product.product'].search(
            [('is_storable', '=', True), ('sale_ok', '=', True)]).filtered(
            lambda p: p.free_qty >= 1)

    def _lineas(self, rng, maximo: int = 3) -> list:
        productos = self._productos_con_stock()
        if not productos:
            return []
        elegidos = rng.sample(list(productos), min(len(productos), rng.randint(1, maximo)))
        return [(0, 0, {'product_id': p.id,
                        'product_uom_qty': max(1, min(int(p.free_qty), rng.randint(1, 4)))})
                for p in elegidos]

    def _proponer(self, rng, cuantos: int, nuevos: dict) -> int:
        _nuevo, calificado, propuesta = self._etapas()
        oportunidades = self.env['crm.lead'].search(
            [('type', '=', 'opportunity'), ('stage_id', '=', calificado.id),
             ('order_ids', '=', False), ('partner_id', '!=', False)],
            order='create_date, id', limit=cuantos)
        hechas = 0
        for oportunidad in oportunidades:
            lineas = self._lineas(rng)
            if not lineas:
                break
            pedido = self.env['sale.order'].create({
                'partner_id': oportunidad.partner_id.id, 'opportunity_id': oportunidad.id,
                'user_id': oportunidad.user_id.id, 'team_id': oportunidad.team_id.id,
                'order_line': lineas,
            })
            if hasattr(pedido, 'action_quotation_sent'):
                pedido.action_quotation_sent()  # «marcar como enviado», sin correo
            nuevos['pedidos'].append(pedido.id)
            oportunidad.stage_id = propuesta
            hechas += 1
        return hechas

    def _recurrentes(self, rng, cuantos: int, nuevos: dict) -> int:
        """Clientes de contract que repiten: presupuesto sin pasar por el CRM."""
        clientes = self.env['sale.order'].search([('state', '=', 'sale')]).partner_id
        hechos = 0
        for _i in range(cuantos):
            lineas = self._lineas(rng, maximo=2)
            if not clientes or not lineas:
                break
            cliente = rng.choice(list(clientes))
            pedido = self.env['sale.order'].create({
                'partner_id': cliente.id, 'user_id': rng.choice(self._comerciales()).id,
                'order_line': lineas,
            })
            nuevos['pedidos'].append(pedido.id)
            hechos += 1
        return hechos

    def _correos_cliente(self, rng, cuantos: int) -> int:
        """Respuestas entrantes del cliente: la señal de contacto más fiable."""
        oportunidades = self.env['crm.lead'].search(
            [('type', '=', 'opportunity'), ('partner_id', '!=', False),
             ('partner_id.email', '!=', False)])
        if not oportunidades:
            return 0
        elegidas = rng.sample(list(oportunidades), min(cuantos, len(oportunidades)))
        for oportunidad in elegidas:
            oportunidad.message_post(
                body=plan.correo_cliente(rng), message_type='email',
                author_id=oportunidad.partner_id.id, email_from=oportunidad.partner_id.email,
                subtype_xmlid='mail.mt_comment')
        return len(elegidas)

    def _cerrar_actividades(self, rng, cuantos: int, hoy) -> int:
        actividades = self.env['mail.activity'].search(
            [('res_model', 'in', ('crm.lead', 'sale.order', 'purchase.order')),
             ('date_deadline', '<=', hoy)],
            order='date_deadline, id', limit=cuantos)
        for actividad in actividades:
            actividad.action_feedback(feedback=plan.feedback_llamada(rng))
        return len(actividades)

    def _planificar_actividades(self, rng, cuantos: int, hoy) -> int:
        oportunidades = self.env['crm.lead'].search(
            [('type', '=', 'opportunity'), ('activity_ids', '=', False)],
            order='write_date, id', limit=cuantos)
        tipos = ['mail.mail_activity_data_call', 'mail.mail_activity_data_email']
        for oportunidad in oportunidades:
            oportunidad.activity_schedule(
                rng.choice(tipos), date_deadline=hoy + timedelta(days=rng.randint(1, 4)),
                summary=_('Seguimiento de la propuesta'),
                user_id=(oportunidad.user_id or self.env.user).id)
        return len(oportunidades)

    # ----------------------------------------------------------------- ventas

    def _confirmar(self, cuantos: int, nuevos: dict) -> int:
        """Solo se confirma un presupuesto si hay stock libre para todas sus líneas."""
        candidatos = self.env['sale.order'].search(
            [('state', 'in', ('draft', 'sent')), ('id', 'not in', nuevos['pedidos'])],
            order='date_order desc, id desc', limit=15)
        con_stock = candidatos.filtered(lambda o: o.order_line and all(
            not linea.product_id.is_storable or linea.product_id.free_qty >= linea.product_uom_qty
            for linea in o.order_line))
        hechos = 0
        for pedido in con_stock[:cuantos]:
            pedido.action_confirm()
            if pedido.opportunity_id and pedido.opportunity_id.active:
                pedido.opportunity_id.action_set_won()
            hechos += 1
        return hechos

    def _perder(self, cuantos: int, hoy) -> int:
        """Oportunidades con la propuesta parada más de un mes: se dan por perdidas."""
        if not cuantos:
            return 0
        limite = fields.Datetime.to_datetime(hoy) - timedelta(days=DIAS_PRESUPUESTO_PERDIDO)
        pedidos = self.env['sale.order'].search(
            [('state', 'in', ('draft', 'sent')), ('opportunity_id', '!=', False),
             ('date_order', '<', limite)], order='date_order, id', limit=cuantos)
        motivo = self.env['crm.lost.reason'].search([], limit=1)
        for pedido in pedidos:
            pedido._action_cancel()
            pedido.opportunity_id.action_set_lost(lost_reason_id=motivo.id)
        return len(pedidos)

    def _validar(self, albaran, completar: bool = False) -> bool:
        """Valida un albarán entero o no lo toca.

        Salida: solo si todo está reservado (nunca se fuerza cantidad: eso deja
        existencias negativas). Entrada (completar=True): llega lo pedido.
        """
        movimientos = albaran.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        if not completar and any(m.quantity < m.product_uom_qty for m in movimientos):
            return False
        for movimiento in movimientos:
            if completar:
                movimiento.quantity = movimiento.product_uom_qty
            movimiento.picked = True
        albaran.with_context(skip_backorder=True, skip_sms=True).button_validate()
        return albaran.state == 'done'

    def _entregar(self, cuantos: int) -> int:
        pendientes = self.env['stock.picking'].search(
            [('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting'))])
        for albaran in pendientes:  # uno a uno: «nada que reservar» no para a los demás
            try:
                with self.env.cr.savepoint():
                    albaran.action_assign()
                    self.env.flush_all()
            except UserError:
                self.env.invalidate_all()
        albaranes = self.env['stock.picking'].search(
            [('picking_type_code', '=', 'outgoing'), ('state', '=', 'assigned')],
            order='scheduled_date, id', limit=cuantos)
        return sum(1 for albaran in albaranes if self._validar(albaran))

    def _facturar(self, cuantos: int, hoy) -> int:
        """Se factura lo entregado: pedidos con todos sus albaranes hechos."""
        if not self.env['account.journal'].search([('type', '=', 'sale')], limit=1):
            return 0
        pedidos = self.env['sale.order'].search(
            [('state', '=', 'sale'), ('invoice_status', '=', 'to invoice')],
            order='date_order, id').filtered(
            lambda o: o.picking_ids and all(p.state in ('done', 'cancel') for p in o.picking_ids))
        facturas = pedidos[:cuantos]._create_invoices() if pedidos else self.env['account.move']
        facturas.invoice_date = hoy
        facturas.action_post()
        return len(facturas)

    def _cobrar(self, cuantos: int, hoy) -> int:
        if not cuantos or not self.env['account.journal'].search([('type', '=', 'bank')], limit=1):
            return 0
        facturas = self.env['account.move'].search(
            [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
             ('payment_state', 'in', ('not_paid', 'partial')),
             ('invoice_date', '<=', hoy - timedelta(days=DIAS_PARA_COBRO))],
            order='invoice_date, id', limit=cuantos)
        for factura in facturas:
            self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=factura.ids,
            ).create({'payment_date': hoy})._create_payments()
        return len(facturas)

    # ---------------------------------------------------------------- compras

    def _reponer(self) -> int:
        """Lo que se va a agotar se pide a su proveedor (un pedido por tramo)."""
        faltan = self.env['product.product'].search(
            [('is_storable', '=', True), ('purchase_ok', '=', True)]).filtered(
            lambda p: p.virtual_available < STOCK_MINIMO and p.seller_ids)
        if not faltan:
            return 0
        proveedor = faltan[0].seller_ids[0].partner_id
        lineas = [(0, 0, {'product_id': p.id,
                          'product_qty': STOCK_OBJETIVO - p.virtual_available,
                          'price_unit': p.seller_ids[0].price or p.standard_price})
                  for p in faltan.filtered(lambda p: p.seller_ids[0].partner_id == proveedor)[:6]]
        compra = self.env['purchase.order'].create({'partner_id': proveedor.id,
                                                    'order_line': lineas})
        compra.button_confirm()
        return 1

    def _recibir(self, cuantos: int, momento: datetime) -> int:
        """El proveedor tarda: solo llega lo pedido antes de hoy."""
        inicio_del_dia = datetime.combine(momento.date(), time.min)
        albaranes = self.env['stock.picking'].search(
            [('picking_type_code', '=', 'incoming'), ('state', '=', 'assigned'),
             ('create_date', '<', inicio_del_dia)], order='scheduled_date, id', limit=cuantos)
        return sum(1 for albaran in albaranes if self._validar(albaran, completar=True))

    def _facturas_proveedor(self, cuantos: int, hoy) -> int:
        if not cuantos or not self.env['account.journal'].search(
                [('type', '=', 'purchase')], limit=1):
            return 0
        compras = self.env['purchase.order'].search(
            [('state', '=', 'purchase'), ('invoice_status', '=', 'to invoice')],
            order='date_approve, id', limit=cuantos)
        hechas = 0
        for compra in compras:
            compra.action_create_invoice()
            borradores = compra.invoice_ids.filtered(lambda f: f.state == 'draft')
            borradores.invoice_date = hoy
            borradores.action_post()
            hechas += len(borradores)
        return hechas

    # --------------------------------------------------------------- controles

    def _descartar_correos(self, desde_id: int) -> int:
        """No hay servidor de correo: lo que el tramo dejó en cola no sale nunca."""
        cola = self.env['mail.mail'].search(
            [('id', '>', desde_id), ('state', 'in', ('outgoing', 'exception'))])
        cola.unlink()
        return len(cola)

    def _comprobar_coherencia(self) -> list[str]:
        problemas = []
        negativos = self.env['stock.quant'].search_count(
            [('location_id.usage', '=', 'internal'), ('quantity', '<', 0)])
        if negativos:
            problemas.append(f'{negativos} existencias negativas')
        ubicacion_archivada = self.env['stock.move'].search_count(
            [('state', 'not in', ('done', 'cancel')), '|',
             ('location_id.active', '=', False), ('location_dest_id.active', '=', False)])
        if ubicacion_archivada:
            problemas.append(f'{ubicacion_archivada} movimientos pendientes en ubicaciones archivadas')
        reales = [s.email for s in self.env['res.partner'].with_context(active_test=False).search(
            [('email', '!=', False)]) if not plan.es_email_ficticio(s.email)]
        reales += [lead.email_from for lead in self.env['crm.lead'].with_context(
            active_test=False).search([('email_from', '!=', False)])
            if not plan.es_email_ficticio(lead.email_from)]
        if reales:
            problemas.append(f'{len(reales)} correos con dominio real (p. ej. {reales[0]})')
        return problemas
