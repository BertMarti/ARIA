package io.github.bertmarti.aria;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.widget.RemoteViews;
import org.json.JSONArray;
import org.json.JSONObject;

/** Widget de Hogar: vigilancia automática, cámaras y luces (lo que ARIA ya sabe). Solo para administradores. */
public class AriaWidgetHogar extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        actualizar(context, manager, ids);
        AvisosWorker.ahora(context);
    }

    static void actualizar(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        actualizar(context, manager, manager.getAppWidgetIds(new ComponentName(context, AriaWidgetHogar.class)));
    }

    private static void actualizar(Context context, AppWidgetManager manager, int[] ids) {
        JSONObject resumen = AriaWidget.resumen(context);
        JSONObject hogar = resumen == null ? null : resumen.optJSONObject("hogar");
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.aria_widget_hogar);
            views.setOnClickPendingIntent(R.id.hogar_raiz, AriaWidget.accion(context, "hogar", id + 6000));
            views.setTextViewText(R.id.hogar_camaras, "");
            views.setTextViewText(R.id.hogar_luces, "");
            if (resumen == null) {
                views.setTextViewText(R.id.hogar_vigilancia, AriaWidget.sinDatos(context));
            } else if (hogar == null) {
                views.setTextViewText(R.id.hogar_vigilancia, "Solo para quien administra ARIA");
            } else {
                JSONObject v = hogar.optJSONObject("vigilancia");
                String vigilancia = v == null ? "Vigilancia sin configurar"
                        : !v.optBoolean("activa") ? "Vigilancia desactivada"
                        : "fuera".equals(v.optString("estado")) ? "No hay nadie: la cámara vigila"
                        : "Hay alguien en casa";
                JSONArray quien = v == null ? null : v.optJSONArray("en_casa");
                if (quien != null && quien.length() > 0) {
                    StringBuilder nombres = new StringBuilder();
                    for (int i = 0; i < quien.length(); i++) nombres.append(i == 0 ? "" : ", ").append(quien.optString(i));
                    vigilancia = "fuera".equals(v.optString("estado")) ? vigilancia : "En casa: " + nombres;
                }
                views.setTextViewText(R.id.hogar_vigilancia, vigilancia);
                int camaras = hogar.optInt("camaras"), tapadas = hogar.optInt("tapadas"), dormidas = hogar.optInt("sin_respuesta");
                if (camaras > 0) {
                    views.setTextViewText(R.id.hogar_camaras, camaras + " cámaras"
                            + (tapadas > 0 ? " · " + tapadas + (tapadas == 1 ? " tapada" : " tapadas") : "")
                            + (dormidas > 0 ? " · " + dormidas + " sin respuesta" : ""));
                }
                int luces = hogar.optInt("luces");
                if (luces > 0) {
                    views.setTextViewText(R.id.hogar_luces, "Luces: " + hogar.optInt("luces_encendidas") + " de " + luces + " encendidas");
                }
            }
            manager.updateAppWidget(id, views);
        }
    }
}
