package io.github.bertmarti.aria;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.widget.RemoteViews;
import java.text.NumberFormat;
import java.util.Locale;
import org.json.JSONObject;

/** Widget de Casa: anuncios bloqueados hoy, móviles en la VPN y si los servicios van bien. Solo para administradores. */
public class AriaWidgetCasa extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        actualizar(context, manager, ids);
        AvisosWorker.ahora(context);
    }

    static void actualizar(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        actualizar(context, manager, manager.getAppWidgetIds(new ComponentName(context, AriaWidgetCasa.class)));
    }

    private static void actualizar(Context context, AppWidgetManager manager, int[] ids) {
        JSONObject resumen = AriaWidget.resumen(context);
        JSONObject casa = resumen == null ? null : resumen.optJSONObject("casa");
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.aria_widget_casa);
            views.setOnClickPendingIntent(R.id.casa_raiz, AriaWidget.accion(context, "red", id + 5000));
            views.setTextViewText(R.id.casa_anuncios, "");
            views.setTextViewText(R.id.casa_anuncios_txt, "");
            views.setTextViewText(R.id.casa_vpn, "");
            views.setTextViewText(R.id.casa_servicios, "");
            if (resumen == null) {
                views.setTextViewText(R.id.casa_anuncios_txt, AriaWidget.sinDatos(context));
            } else if (casa == null) {
                views.setTextViewText(R.id.casa_anuncios_txt, "Solo para quien administra ARIA");
            } else {
                if (!casa.isNull("anuncios")) {
                    views.setTextViewText(R.id.casa_anuncios,
                            NumberFormat.getIntegerInstance(new Locale("es", "ES")).format(casa.optLong("anuncios")));
                    views.setTextViewText(R.id.casa_anuncios_txt, casa.optBoolean("bloqueo_activo", true)
                            ? "anuncios bloqueados hoy" : "anuncios bloqueados (bloqueo en pausa)");
                } else {
                    views.setTextViewText(R.id.casa_anuncios_txt, "SHIELD-DNS sin datos");
                }
                if (!casa.isNull("vpn_conectados")) {
                    int n = casa.optInt("vpn_conectados");
                    views.setTextViewText(R.id.casa_vpn, n == 0 ? "VPN: nadie conectado"
                            : n == 1 ? "VPN: 1 conectado" : "VPN: " + n + " conectados");
                }
                if (!casa.isNull("servicios_ok")) {
                    views.setTextViewText(R.id.casa_servicios, casa.optBoolean("servicios_ok")
                            ? "✓ Todo funciona" : "⚠ Algún servicio falla");
                }
            }
            manager.updateAppWidget(id, views);
        }
    }
}
