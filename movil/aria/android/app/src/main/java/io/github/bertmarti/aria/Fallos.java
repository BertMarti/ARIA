package io.github.bertmarti.aria;

import android.content.Context;
import android.net.Uri;
import android.webkit.CookieManager;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** Guarda y entrega el último cierre de la app, sin incluir datos de la sesión o del usuario. */
final class Fallos {
    private static final String PREFS = "fallos_aria";
    private static final String INFORME = "informe";
    private static final String INTENTOS = "intentos";

    private static boolean instalado;

    private Fallos() { }

    /** Una sola vez por proceso (la actividad se recrea al girar la pantalla, y el servicio también llama aquí). */
    static synchronized void instalar(Context contexto) {
        if (instalado) return;
        instalado = true;
        final Context context = contexto.getApplicationContext();
        final Thread.UncaughtExceptionHandler anterior = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((hilo, error) -> {
            try {
                JSONObject informe = new JSONObject();
                // Android envuelve muchos fallos («Unable to start activity…»): lo útil es la causa más profunda.
                Throwable raiz = error;
                for (int i = 0; i < 10 && raiz.getCause() != null && raiz.getCause() != raiz; i++) raiz = raiz.getCause();
                String mensaje = raiz.getMessage();
                informe.put("excepcion", raiz.getClass().getName() + (mensaje == null || mensaje.isEmpty() ? "" : ": " + mensaje));
                StringBuilder traza = new StringBuilder();
                int lineas = 0;
                for (StackTraceElement elemento : raiz.getStackTrace()) {
                    if (lineas++ >= 25) break;
                    String linea = "at " + elemento;
                    if (traza.length() + linea.length() + 1 > 4000) break;
                    if (traza.length() > 0) traza.append('\n');
                    traza.append(linea);
                }
                informe.put("traza", traza.toString());
                informe.put("version", BuildConfig.VERSION_NAME);
                informe.put("android", android.os.Build.VERSION.SDK_INT);
                informe.put("modelo", android.os.Build.MODEL);
                informe.put("cuando", System.currentTimeMillis());
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                        .putString(INFORME, informe.toString()).putInt(INTENTOS, 0).commit();
            } catch (Exception ignorado) {
                // El manejador de cierres nunca debe impedir el cierre normal de Android.
            }
            if (anterior != null) anterior.uncaughtException(hilo, error);
        });
    }

    static void enviarPendiente(Context context, String base) {
        if (base == null || base.isEmpty()) return;
        Context app = context.getApplicationContext();
        new Thread(() -> enviar(app, base), "aria-fallo").start();
    }

    private static void enviar(Context context, String base) {
        android.content.SharedPreferences preferencias = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String informe = preferencias.getString(INFORME, "");
        if (informe.isEmpty()) return;
        int intentos = preferencias.getInt(INTENTOS, 0) + 1;
        HttpURLConnection conexion = null;
        boolean correcto = false;
        try {
            String raiz = base.endsWith("/") ? base : base + "/";
            Uri origen = Uri.parse(raiz);
            String autoridad = origen.getHost();
            if (autoridad == null) return;
            if (origen.getPort() > 0) autoridad += ":" + origen.getPort();
            conexion = (HttpURLConnection) new URL(raiz + "api/app/fallos").openConnection();
            conexion.setRequestMethod("POST");
            conexion.setConnectTimeout(8000);
            conexion.setReadTimeout(8000);
            conexion.setDoOutput(true);
            conexion.setRequestProperty("Content-Type", "application/json");
            conexion.setRequestProperty("Origin", origen.getScheme() + "://" + autoridad);
            String cookies = CookieManager.getInstance().getCookie(raiz);
            if (cookies != null) conexion.setRequestProperty("Cookie", cookies);
            try (OutputStream salida = conexion.getOutputStream()) {
                salida.write(informe.getBytes(StandardCharsets.UTF_8));
            }
            int respuesta = conexion.getResponseCode();
            correcto = respuesta >= 200 && respuesta < 300;
        } catch (Exception ignorado) {
            // Se conserva para el siguiente arranque o carga de la página.
        } finally {
            if (conexion != null) conexion.disconnect();
        }
        android.content.SharedPreferences.Editor cambio = preferencias.edit();
        if (correcto || intentos >= 5) cambio.remove(INFORME).remove(INTENTOS);
        else cambio.putInt(INTENTOS, intentos);
        cambio.commit();
    }
}
