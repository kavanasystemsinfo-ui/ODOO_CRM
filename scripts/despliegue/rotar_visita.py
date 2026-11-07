# Se ejecuta con `odoo shell -d <base>`. Cambia la contraseña del usuario de
# visita de la demo, que estuvo publicada en el README de la v1 (sigue en el
# historial de git). La entrada pública /demo abre la sesión de visita sin
# contraseña, así que la demo no cambia para nadie.
# Imprime VISITA_PASSWORD=<nueva> para que quien lo llama la guarde en un
# fichero con permisos 600; no se escribe en ningún otro sitio.
import secrets

usuario = env['res.users'].with_context(active_test=False).search([('login', '=', 'visita')], limit=1)
if not usuario:
    print('VISITA_NO_EXISTE')
else:
    nueva = 'Visita-' + secrets.token_urlsafe(18)
    usuario.sudo().password = nueva
    env.cr.commit()
    print(f'VISITA_OK usuario={usuario.id}')
    print('VISITA_PASSWORD=' + nueva)
