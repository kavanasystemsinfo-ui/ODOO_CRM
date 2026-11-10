"""Coherencia de los datos de la empresa simulada (paso de cada tramo).

La base arrastra restos de los datos de ejemplo de Odoo y de la carga inicial:
proveedores con dirección en California, clientes con nombre valenciano en
Sevilla, leads con teléfonos belgas, la empresa del lead escondida en el
título, descripciones de pedido en inglés del catálogo antiguo, la URL interna
del servidor en los documentos... Este paso lo deja coherente y vuelve a
pasar en cada tramo: lo que ya está bien no se toca (idempotente).

Las reglas (ciudades, NIF, teléfonos) son puras y están en simulador_datos.py.
"""
from __future__ import annotations

from odoo import api, models

from . import simulador_datos as datos
from . import simulador_plan as plan


class SimuladorCoherencia(models.AbstractModel):
    _inherit = 'odoo_crm.simulador'

    @api.model
    def _coherencia_datos(self) -> int:
        return (self._coherencia_parametros() + self._coherencia_contactos()
                + self._coherencia_leads() + self._coherencia_catalogo()
                + self._coherencia_lineas())

    # ------------------------------------------------------------ parámetros

    def _coherencia_parametros(self) -> int:
        cambios = 0
        url = self._param('web.base.url')
        if not url or '127.0.0.1' in url or 'localhost' in url:
            self._param('web.base.url', datos.URL_PUBLICA)  # enlaces de documentos y correos
            cambios += 1
        if self._param('web.base.url.freeze') != 'True':
            self._param('web.base.url.freeze', 'True')     # que no la pise un acceso interno
            cambios += 1
        sin_zona = self.env['res.users'].search([('share', '=', False), ('tz', '=', False)])
        sin_zona.tz = datos.ZONA_HORARIA
        cambios += len(sin_zona)
        sin_pais = self.env['res.users'].search([('share', '=', False)]).partner_id.filtered(
            lambda p: not p.country_id)
        sin_pais.country_id = self.env.ref('base.es')
        cambios += len(sin_pais)
        empresa = self.env.company.partner_id
        cambios += self._escribir_si_cambia(empresa, self._valores_direccion(
            empresa, ciudad='Castelló de la Plana', telefono=empresa.phone))
        return cambios

    # ------------------------------------------------------------ contactos

    def _provincia(self, codigo: str):
        return self.env['res.country.state'].search(
            [('country_id.code', '=', 'ES'), ('code', '=', codigo)], limit=1)

    def _valores_direccion(self, socio, ciudad: str | None = None, telefono: str | None = None) -> dict:
        semilla = f'res.partner/{socio.id}'
        direccion = datos.direccion(socio.name, semilla)
        if ciudad:  # la empresa propia: ciudad fija, calle la que ya tiene
            provincia, cp, _prefijo = datos.CIUDADES[ciudad]
            direccion.update(city=ciudad, provincia=provincia,
                             street=socio.street or direccion['street'],
                             zip=socio.zip or direccion['zip'])
        return {
            'street': direccion['street'], 'city': direccion['city'], 'zip': direccion['zip'],
            'state_id': self._provincia(direccion['provincia']).id,
            'country_id': self.env.ref('base.es').id,
            'phone': telefono if telefono and datos.es_telefono_espanol(telefono)
            and not datos.telefono_de_relleno(telefono) else direccion['phone'],
        }

    def _escribir_si_cambia(self, registro, valores: dict) -> int:
        distintos = {}
        for campo, valor in valores.items():
            actual = registro[campo]
            actual = actual.id if hasattr(actual, '_name') else actual
            if actual != valor:
                distintos[campo] = valor
        if distintos:
            registro.write(distintos)
        return 1 if distintos else 0

    def _datos_contacto(self, socio) -> int:
        """Dirección, provincia, teléfono y NIF coherentes para un cliente o proveedor."""
        valores = {}
        nombre = datos.renombrar(datos.empresa_del_titulo(socio.name) or socio.name)
        if nombre != socio.name:
            valores['name'] = nombre
        es_empresa = socio.is_company or datos.parece_empresa(nombre)
        if es_empresa and not socio.is_company:
            valores['is_company'] = True
        valores.update(self._valores_direccion(socio, telefono=socio.phone))
        # NIF y país van juntos: Odoo 20 valida el NIF contra el país al escribir.
        semilla = f'res.partner/{socio.id}'
        if es_empresa and not datos.cif_valido(socio.vat):
            valores['vat'] = datos.cif(semilla)
        elif not es_empresa and not (socio.vat or '').startswith('ES'):
            valores['vat'] = datos.nif(semilla)
        return self._escribir_si_cambia(socio, valores)

    def _coherencia_contactos(self) -> int:
        con_lead = self.env['crm.lead'].with_context(active_test=False).search(
            [('partner_id', '!=', False)]).partner_id.commercial_partner_id
        socios = self.env['res.partner'].search(
            [('parent_id', '=', False), '|', '|', ('customer_rank', '>', 0),
             ('supplier_rank', '>', 0), ('id', 'in', con_lead.ids)])
        socios -= self.env['res.users'].with_context(active_test=False).search([]).partner_id
        socios -= self.env['res.company'].search([]).partner_id
        return sum(self._datos_contacto(socio) for socio in socios)

    # ------------------------------------------------------------ CRM

    def _coherencia_leads(self) -> int:
        cambios = 0
        for lead in self.env['crm.lead'].with_context(active_test=False).search([]):
            rng = plan.generador(f'crm.lead/{lead.id}')
            valores = {}
            titulo = datos.renombrar(lead.name)
            if titulo != lead.name:
                valores['name'] = titulo
            empresa = lead.partner_name or (
                '' if lead.partner_id else datos.empresa_del_titulo(titulo))
            if empresa and empresa != lead.partner_name:
                valores['partner_name'] = datos.renombrar(empresa)
            contacto = lead.contact_name
            if not contacto or contacto == lead.name or (
                    datos.parece_empresa(contacto) and contacto in (lead.partner_name, empresa)):
                valores['contact_name'] = plan.persona(rng)
            if not datos.es_telefono_espanol(lead.phone):
                valores['phone'] = datos.movil(f'crm.lead/{lead.id}')
            origen = lead.partner_id.commercial_partner_id
            if origen and origen.country_id:
                destino = {'city': origen.city, 'zip': origen.zip, 'street': origen.street,
                           'state_id': origen.state_id.id, 'country_id': origen.country_id.id}
            else:
                d = datos.direccion(empresa or lead.name, f'crm.lead/{lead.id}')
                destino = {'city': d['city'], 'zip': d['zip'], 'street': lead.street or False,
                           'state_id': self._provincia(d['provincia']).id,
                           'country_id': self.env.ref('base.es').id}
            if valores:
                lead.write(valores)
            cambios += bool(valores) + self._escribir_si_cambia(lead, destino)
        return cambios

    # ------------------------------------------------------------ catálogo
    #
    # Los nombres y descripciones del catálogo están guardados solo en una
    # clave de idioma (es_ES o en_US, según cómo se cargaron). Cualquier lectura
    # que acabe en la otra devuelve False: el producto sale sin nombre. Por eso
    # este paso lee y escribe el JSON de traducciones directamente: los dos
    # idiomas llevan el mismo texto en español (la empresa solo trabaja en
    # español) y la lectura no depende del idioma del contexto.

    def _textos_catalogo(self) -> dict[int, tuple[str, str, str]]:
        """product.product id -> (referencia, nombre, descripción de venta) en español."""
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT pp.id, coalesce(pp.default_code, ''),
                   coalesce(pt.name->>'es_ES', pt.name->>'en_US', ''),
                   coalesce(pt.description_sale->>'es_ES', pt.description_sale->>'en_US', '')
              FROM product_product pp JOIN product_template pt ON pt.id = pp.product_tmpl_id
        """)
        return {fila[0]: fila[1:] for fila in self.env.cr.fetchall()}

    def _coherencia_catalogo(self) -> int:
        cr = self.env.cr
        self.env.flush_all()
        cambios = 0
        for columna in ('name', 'description_sale'):
            cr.execute(f"""
                UPDATE product_template
                   SET {columna} = {columna}
                       || jsonb_build_object('es_ES', coalesce({columna}->>'es_ES', {columna}->>'en_US'),
                                             'en_US', coalesce({columna}->>'es_ES', {columna}->>'en_US'))
                 WHERE {columna} IS NOT NULL
                   AND ({columna}->>'es_ES' IS DISTINCT FROM {columna}->>'en_US')
            """)
            cambios += cr.rowcount
        cr.execute("""
            SELECT id, name->>'es_ES', description_sale->>'es_ES', furniture_material
              FROM product_template WHERE description_sale IS NOT NULL
        """)
        for plantilla_id, nombre, descripcion, material_actual in cr.fetchall():
            texto, material = datos.corregir_descripcion(nombre, descripcion)
            if texto and texto != descripcion:
                cr.execute("""
                    UPDATE product_template
                       SET description_sale = jsonb_build_object('es_ES', %s::text, 'en_US', %s::text)
                     WHERE id = %s
                """, (texto, texto, plantilla_id))
                cambios += 1
            if material and (material_actual or '').lower() != material:
                cr.execute('UPDATE product_template SET furniture_material = %s WHERE id = %s',
                           (material.capitalize(), plantilla_id))
                cambios += 1
        if cambios:
            self.env.invalidate_all()
        return cambios

    # ------------------------------------------------------------ pedidos

    def _coherencia_lineas(self) -> int:
        """Líneas con el texto del catálogo antiguo (inglés) o una descripción ya corregida."""
        cambios = 0
        textos = self._textos_catalogo()

        def esperado_venta(producto_id: int) -> str:
            referencia, nombre, descripcion = textos[producto_id]
            texto = f'[{referencia}] {nombre}' if referencia else nombre
            return f'{texto}\n{descripcion}' if descripcion else texto

        def esperado_compra(producto_id: int) -> str:
            referencia, nombre, _descripcion = textos[producto_id]
            return f'[{referencia}] {nombre}' if referencia else nombre

        for modelo, esperado, criterio in (
                ('sale.order.line', esperado_venta,
                 lambda l: datos.parece_ingles(l.name) or ' de estilo ' in (l.name or '')),
                ('purchase.order.line', esperado_compra, lambda l: datos.parece_ingles(l.name))):
            for linea in self.env[modelo].search([('product_id', '!=', False)]).filtered(criterio):
                texto = esperado(linea.product_id.id)
                if texto and texto != linea.name:
                    linea.name = texto
                    cambios += 1
        return cambios

    # ------------------------------------------------------------ control

    def _comprobar_coherencia(self) -> list[str]:
        problemas = super()._comprobar_coherencia()
        fuera = self.env['res.partner'].search_count(
            [('parent_id', '=', False), ('country_id.code', '!=', 'ES'), '|',
             ('customer_rank', '>', 0), ('supplier_rank', '>', 0)])
        if fuera:
            problemas.append(f'{fuera} clientes o proveedores fuera de España')
        telefonos = self.env['crm.lead'].with_context(active_test=False).search(
            [('phone', '!=', False)]).filtered(lambda l: not datos.es_telefono_espanol(l.phone))
        if telefonos:
            problemas.append(f'{len(telefonos)} leads con teléfono extranjero')
        return problemas
