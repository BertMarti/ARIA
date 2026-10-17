package io.github.bertmarti.aria;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.widget.RemoteViews;

/** Widget de 1×1: un toque y ARIA se abre escuchando. */
public class AriaWidgetHablar extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.aria_widget_hablar);
            views.setOnClickPendingIntent(R.id.widget_hablar_raiz, AriaWidget.accion(context, "hablar", id + 3000));
            manager.updateAppWidget(id, views);
        }
    }
}
