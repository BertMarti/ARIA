package io.github.bertmarti.aria;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.webkit.CookieManager;
import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import org.json.JSONArray;
import org.json.JSONObject;

public class AvisosWorker extends Worker {
    /** Pide el resumen ya (al poner el widget o al vincular el móvil), sin esperar a la tarea de cada 15 minutos. */
    static void ahora(Context context) {
        androidx.work.WorkManager.getInstance(context.getApplicationContext()).enqueueUniqueWork("avisos-aria-ahora",
                androidx.work.ExistingWorkPolicy.REPLACE,
                new androidx.work.OneTimeWorkRequest.Builder(AvisosWorker.class)
                        .setConstraints(new androidx.work.Constraints.Builder()
                                .setRequiredNetworkType(androidx.work.NetworkType.CONNECTED).build()).build());
    }

    public AvisosWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        String base = getApplicationContext().getSharedPreferences(
                "CapacitorStorage", Context.MODE_PRIVATE).getString("aria_url", "");
        if (base.isEmpty()) {
            return Result.success();
        }
        String token = DispositivoApp.token(getApplicationContext());
        JSONObject resumen = token.isEmpty() ? null : pedirResumen(base, token);
        if (resumen == null && !token.isEmpty()) {
            resumen = pedirResumenEnCasa(token);   // plan B: la pública bloqueada (LaLiga) pero en casa o con la VPN
        }
        if (resumen == null) {
            resumen = pedirAvisosConCookies(base);
        }
        if (resumen == null) {
            return Result.success();
        }
        guardarResumen(resumen);
        notificarNuevos(base, resumen.optJSONArray("avisos"));
        AriaWidget.actualizarTodos(getApplicationContext());
        return Result.success();
    }

    private JSONObject pedirResumen(String base, String token) {
        HttpURLConnection conexion = null;
        try {
            conexion = (HttpURLConnection) new URL(base + "api/app/resumen").openConnection();
            conexion.setConnectTimeout(8000);
            conexion.setReadTimeout(8000);
            conexion.setRequestProperty("Authorization", "Bearer " + token);
            if (conexion.getResponseCode() == HttpURLConnection.HTTP_UNAUTHORIZED) {
                return null;
            }
            if (conexion.getResponseCode() != HttpURLConnection.HTTP_OK) {
                return null;
            }
            return new JSONObject(leer(conexion));
        } catch (Exception ignorada) {
            return null;
        } finally {
            if (conexion != null) {
                conexion.disconnect();
            }
        }
    }

    private JSONObject pedirResumenEnCasa(String token) {
        HttpURLConnection conexion = Casa.abrir(getApplicationContext(), "api/app/resumen", "Bearer " + token);
        if (conexion == null) {
            return null;
        }
        try {
            if (conexion.getResponseCode() != HttpURLConnection.HTTP_OK) {
                return null;
            }
            return new JSONObject(leer(conexion));
        } catch (Exception ignorada) {
            return null;
        } finally {
            conexion.disconnect();
        }
    }

    private JSONObject pedirAvisosConCookies(String base) {
        HttpURLConnection conexion = null;
        try {
            conexion = (HttpURLConnection) new URL(base + "api/avisos").openConnection();
            conexion.setConnectTimeout(8000);
            conexion.setReadTimeout(8000);
            String cookies = CookieManager.getInstance().getCookie(base);
            if (cookies != null) {
                conexion.setRequestProperty("Cookie", cookies);
            }
            if (conexion.getResponseCode() != HttpURLConnection.HTTP_OK) {
                return null;
            }
            return new JSONObject(leer(conexion));
        } catch (Exception ignorada) {
            return null;
        } finally {
            if (conexion != null) {
                conexion.disconnect();
            }
        }
    }

    private String leer(HttpURLConnection conexion) throws Exception {
        StringBuilder cuerpo = new StringBuilder();
        try (BufferedReader lector = new BufferedReader(new InputStreamReader(
                conexion.getInputStream(), StandardCharsets.UTF_8))) {
            String linea;
            while ((linea = lector.readLine()) != null) {
                cuerpo.append(linea);
            }
        }
        return cuerpo.toString();
    }

    private void guardarResumen(JSONObject resumen) {
        getApplicationContext().getSharedPreferences("widget_aria", Context.MODE_PRIVATE)
                .edit().putString("resumen", resumen.toString()).apply();
    }

    private void notificarNuevos(String base, JSONArray avisos) {
        if (avisos == null) {
            return;
        }
        android.content.SharedPreferences vistos = getApplicationContext()
                .getSharedPreferences("avisos", Context.MODE_PRIVATE);
        android.content.SharedPreferences.Editor edit = vistos.edit();
        for (int i = 0; i < avisos.length(); i++) {
            JSONObject aviso = avisos.optJSONObject(i);
            if (aviso == null || (aviso.has("leido") && aviso.optBoolean("leido", true))) {
                continue;
            }
            String id = aviso.optString("id");
            if (id.isEmpty() || vistos.contains(id)) {
                continue;
            }
            publicar(base, aviso);
            edit.putBoolean(id, true);
        }
        edit.apply();
    }

    private void publicar(String base, JSONObject aviso) {
        Intent open = new Intent(getApplicationContext(), MainActivity.class);
        open.setData(android.net.Uri.parse(base + "#avisos"));
        PendingIntent pi = PendingIntent.getActivity(getApplicationContext(), aviso.optString("id").hashCode(),
                open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder notificacion = new NotificationCompat.Builder(
                getApplicationContext(), "avisos");
        notificacion.setSmallIcon(R.drawable.ic_stat_aria);
        notificacion.setContentTitle("ARIA");
        notificacion.setContentText(aviso.optString("texto", "Nuevo aviso"));
        notificacion.setAutoCancel(true);
        notificacion.setContentIntent(pi);
        androidx.core.app.NotificationManagerCompat.from(getApplicationContext())
                .notify(aviso.optString("id").hashCode(), notificacion.build());
    }
}
