package io.github.bertmarti.aria;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.widget.RemoteViews;
import org.json.JSONArray;
import org.json.JSONObject;

/** Widget de Agenda: los próximos tres eventos de los siete días siguientes. */
public class AriaWidgetAgenda extends AppWidgetProvider {
    private static final int[] FILAS = {R.id.agenda_1, R.id.agenda_2, R.id.agenda_3};

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        actualizar(context, manager, ids);
        AvisosWorker.ahora(context);
    }

    static void actualizar(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        actualizar(context, manager, manager.getAppWidgetIds(new ComponentName(context, AriaWidgetAgenda.class)));
    }

    private static void actualizar(Context context, AppWidgetManager manager, int[] ids) {
        JSONObject resumen = AriaWidget.resumen(context);
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.aria_widget_agenda);
            views.setOnClickPendingIntent(R.id.agenda_raiz, AriaWidget.accion(context, "agenda", id + 4000));
            for (int fila : FILAS) views.setTextViewText(fila, "");
            JSONArray proximos = resumen == null ? null : resumen.optJSONArray("proximos");
            if (resumen == null) {
                views.setTextViewText(R.id.agenda_1, AriaWidget.sinDatos(context));
            } else if (proximos == null || proximos.length() == 0) {
                views.setTextViewText(R.id.agenda_1, "Nada en los próximos 7 días");
            } else {
                for (int i = 0; i < Math.min(FILAS.length, proximos.length()); i++) {
                    JSONObject e = proximos.optJSONObject(i);
                    if (e != null) views.setTextViewText(FILAS[i], AriaWidget.fecha(e.optString("inicio"))
                            + " · " + e.optString("titulo", "Evento"));
                }
            }
            manager.updateAppWidget(id, views);
        }
    }
}
