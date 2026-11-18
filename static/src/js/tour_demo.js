/**
 * Recorrido guiado de la demo (Ventas: de la lista al pedido).
 *
 * Es un tour interactivo de Odoo (el puntero morado): el visitante hace clic
 * en cada elemento señalado. Vive solo en el cliente: no escribe nada en la
 * base de datos ni exige actualizar el módulo.
 *
 * - Se abre solo la primera vez que un navegador entra en una base
 *   (clave en localStorage por base de datos).
 * - Se repite desde el menú del usuario: «Recorrido guiado».
 */
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const TOUR = "muebles_demo";
const CLAVE_VISTO = `muebles_tour_visto_${session.db || "demo"}`;

registry.category("web_tour.tours").add(TOUR, {
    steps: () => [
        {
            trigger: ".o_navbar_apps_menu button",
            content:
                "Aquí están todas las aplicaciones de la empresa de muebles: ventas, compras, inventario, facturación… Ábrelo.",
            tooltipPosition: "bottom",
            run: "click",
        },
        {
            trigger: '.o-dropdown--menu .o_app[data-menu-xmlid="sale.sale_menu_root"]',
            content: "Empieza por Ventas: los presupuestos y pedidos de los clientes.",
            tooltipPosition: "right",
            run: "click",
        },
        {
            trigger: ".o_list_view .o_data_row .o_data_cell",
            content:
                "Cada fila es un presupuesto o un pedido, con su cliente, su total y su estado. Abre uno.",
            tooltipPosition: "bottom",
            run: "click",
        },
        {
            trigger: ".o_form_view .o_statusbar_status",
            content: "Arriba ves en qué punto está: presupuesto, enviado o pedido de venta.",
            tooltipPosition: "bottom",
            run: "click",
        },
        {
            trigger: '.o_form_view .o_field_widget[name="order_line"]',
            content:
                "Estas son las líneas: qué muebles, cuántos, a qué precio y con qué IVA. El total sale solo. Mira también Muebles de Hogar y CRM en el menú de aplicaciones.",
            tooltipPosition: "top",
            run: "click",
        },
    ],
});

function marcarVisto() {
    try {
        localStorage.setItem(CLAVE_VISTO, "1");
    } catch (e) {
        /* sin almacenamiento: el recorrido se ofrecerá de nuevo */
    }
}

function yaVisto() {
    try {
        return localStorage.getItem(CLAVE_VISTO) === "1";
    } catch (e) {
        return false;
    }
}

function empezar(tourService) {
    // El motor de tours activa en el servidor el «modo onboarding» del usuario
    // al lanzar un tour manual y eso encadena los tours nativos de Odoo y
    // escribe en la base. Se marca como activo en el cliente para evitarlo.
    tourService.toursEnabled = true;
    return tourService.startTour(TOUR, { mode: "manual", redirect: false });
}

registry.category("services").add("muebles_tour_demo", {
    dependencies: ["tour_service"],
    start(env, { tour_service }) {
        if (window.frameElement || session.is_public) {
            return;
        }
        // Se abre solo la primera vez, cuando la pantalla ya ha cargado.
        setTimeout(() => {
            const enCurso = localStorage.getItem("current_tour");
            if (!yaVisto() && !enCurso) {
                marcarVisto();
                empezar(tour_service);
            }
        }, 1500);
    },
});

registry.category("user_menuitems").add("muebles_tour", (env) => ({
    type: "item",
    id: "muebles_tour",
    description: "Recorrido guiado",
    callback: () => empezar(env.services.tour_service),
    sequence: 3,
}));
