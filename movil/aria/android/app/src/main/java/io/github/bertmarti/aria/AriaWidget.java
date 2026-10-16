package io.github.bertmarti.aria;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import org.json.JSONArray;
import org.json.JSONObject;

public class AriaWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        actualizar(context, manager, ids);
    }

    static void actualizar(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName nombre = new ComponentName(context, AriaWidget.class);
        actualizar(context, manager, manager.getAppWidgetIds(nombre));
    }

    private static void actualizar(Context context, AppWidgetManager manager, int[] ids) {
        String texto = context.getSharedPreferences("widget_aria", Context.MODE_PRIVATE)
                .getString("resumen", "");
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.aria_widget);
            views.setOnClickPendingIntent(R.id.widget_hablar, accion(context, "hablar", id));
            views.setOnClickPendingIntent(R.id.widget_nota, accion(context, "nota", id + 1000));
            views.setOnClickPendingIntent(R.id.widget_resumen, accion(context, "avisos", id + 2000));
            rellenar(views, texto);
            manager.updateAppWidget(id, views);
        }
    }

    private static void rellenar(RemoteViews views, String texto) {
        if (texto.isEmpty()) {
            views.setTextViewText(R.id.widget_tiempo, "Abre ARIA para vincular");
            views.setTextViewText(R.id.widget_proximo, "");
            views.setTextViewText(R.id.widget_avisos, "");
            return;
        }
        try {
            JSONObject resumen = new JSONObject(texto);
            JSONObject tiempo = resumen.optJSONObject("tiempo");
            if (tiempo == null) {
                views.setTextViewText(R.id.widget_tiempo, "Tiempo no disponible");
            } else {
                String lugar = tiempo.optString("lugar", "");
                String grados = tiempo.optString("actual", "") + "°";
                String cielo = tiempo.optString("cielo", "");
                views.setTextViewText(R.id.widget_tiempo, lugar + " · " + grados + " · " + cielo);
            }
            JSONObject proximo = resumen.optJSONObject("proximo");
            String evento = proximo == null ? "Sin próximos eventos" : fecha(proximo.optString("inicio"))
                    + " · " + proximo.optString("titulo", "Evento");
            views.setTextViewText(R.id.widget_proximo, evento);
            JSONArray avisos = resumen.optJSONArray("avisos");
            views.setTextViewText(R.id.widget_avisos, (avisos == null ? 0 : avisos.length()) + " avisos sin leer");
        } catch (Exception ignorada) {
            views.setTextViewText(R.id.widget_tiempo, "Abre ARIA para vincular");
        }
    }

    private static String fecha(String texto) {
        try {
            String normalizado = texto.replaceAll("([+-]\\d\\d):(\\d\\d)$", "$1$2").replace("Z", "+0000");
            SimpleDateFormat lector = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.US);
            Date fecha = lector.parse(normalizado);
            Calendar hoy = Calendar.getInstance();
            Calendar dia = Calendar.getInstance();
            dia.setTime(fecha);
            String prefijo = dia.get(Calendar.DAY_OF_YEAR) == hoy.get(Calendar.DAY_OF_YEAR)
                    ? "Hoy" : "Mañana";
            return prefijo + " " + new SimpleDateFormat("HH:mm", Locale.getDefault()).format(fecha);
        } catch (Exception ignorada) {
            return texto;
        }
    }

    private static PendingIntent accion(Context context, String accion, int request) {
        Intent intent = new Intent(context, MainActivity.class)
                .putExtra("accion", accion).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(context, request, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
