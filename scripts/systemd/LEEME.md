# Servicios del laboratorio en el servidor

| Unidad | Usuario | Qué hace |
|---|---|---|
| `muebles-panel.service` | `muebles-panel` (sin privilegios) | Sirve el panel del día en 127.0.0.1:8081; el proxy lo publica en `/panel` |
| `muebles-restore.timer` → `muebles-restore.service` | root | Cada 30 min ejecuta `panel/limpieza_automatica.sh`: verifica y restaura solo si alguien cambió la demo |
| `muebles-restore-ahora.service` | root | Restauración inmediata, la del botón del panel |
| `muebles-jornada.timer` → `muebles-jornada.service` | root | Un tramo de la empresa simulada (L-V 9, 13 y 17 h; sábado 11 h): verifica, simula y fija la instantánea |
| `muebles-panel.sudoers` | — | Permite al panel una sola orden: arrancar `muebles-restore-ahora.service` |

## Instalación (como root, con el checkout en `/root/ODOO_CRM`)

```bash
useradd --system --no-create-home --shell /usr/sbin/nologin muebles-panel
visudo -cf scripts/systemd/muebles-panel.sudoers \
  && install -m 0440 scripts/systemd/muebles-panel.sudoers /etc/sudoers.d/muebles-panel
cp scripts/systemd/muebles-panel.service scripts/systemd/muebles-restore.service \
   scripts/systemd/muebles-restore-ahora.service scripts/systemd/muebles-restore.timer \
   scripts/systemd/muebles-jornada.service scripts/systemd/muebles-jornada.timer \
   /etc/systemd/system/
systemctl daemon-reload
systemctl restart muebles-panel.service
systemctl enable --now muebles-restore.timer muebles-jornada.timer
```

`/etc/muebles/panel.env` lo lee systemd como root antes de cambiar de usuario:
puede seguir en `600 root` y el usuario del panel no lo lee del disco.

## Comprobación

```bash
systemctl show -p User --value muebles-panel.service        # muebles-panel
ps -o user= -p "$(systemctl show -p MainPID --value muebles-panel.service)"
sudo -u muebles-panel sudo -n -l                            # solo la orden de restaurar
systemctl start muebles-restore.service && journalctl -u muebles-restore -n 5
# con la demo intacta debe decir «intacto: no se toca» y Odoo no se reinicia
```
