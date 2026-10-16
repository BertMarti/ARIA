package io.github.bertmarti.aria;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

public class AriaWidget extends AppWidgetProvider {
    @Override public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) { RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.aria_widget); views.setOnClickPendingIntent(R.id.widget_hablar, accion(context, "hablar", id)); views.setOnClickPendingIntent(R.id.widget_nota, accion(context, "nota", id + 1000)); manager.updateAppWidget(id, views); }
    }
    private PendingIntent accion(Context context, String accion, int request) { Intent i = new Intent(context, MainActivity.class).putExtra("accion", accion).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP); return PendingIntent.getActivity(context, request, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE); }
}
