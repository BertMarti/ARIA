package io.github.bertmarti.aria;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import org.json.JSONObject;

final class DispositivoApp {
    static final String PREFS = "dispositivo_app";
    static final String TOKEN = "token_dispositivo";
    private static final String CADUCA = "caduca_dispositivo";
    private static final String NO_DISPONIBLE = "dispositivo_no_disponible";
    private static final long QUINCE_DIAS = 15L * 86_400_000L;
    private static final long UN_DIA = 86_400_000L;

    private DispositivoApp() { }

    static String token(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(TOKEN, "");
    }

    static boolean debeRenovar(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String token = prefs.getString(TOKEN, "");
        long caduca = prefs.getLong(CADUCA, 0L);
        return token.isEmpty() || caduca - System.currentTimeMillis() < QUINCE_DIAS;
    }

    static void vincularEnSegundoPlano(Context context, String base) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (!debeRenovar(context)
                || System.currentTimeMillis() - prefs.getLong(NO_DISPONIBLE, 0L) < UN_DIA) {
            return;
        }
        new Thread(() -> vincular(context.getApplicationContext(), base)).start();
    }

    static void borrar(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .remove(TOKEN).remove(CADUCA).remove(NO_DISPONIBLE).apply();
    }

    private static void vincular(Context context, String base) {
        HttpURLConnection conexion = null;
        try {
            conexion = (HttpURLConnection) new URL(base + "api/app/dispositivos").openConnection();
            conexion.setRequestMethod("POST");
            conexion.setConnectTimeout(8000);
            conexion.setReadTimeout(8000);
            conexion.setDoOutput(true);
            conexion.setRequestProperty("Content-Type", "application/json");
            String cookies = android.webkit.CookieManager.getInstance().getCookie(base);
            if (cookies != null) {
                conexion.setRequestProperty("Cookie", cookies);
            }
            JSONObject solicitud = new JSONObject().put("nombre", Build.MODEL);
            conexion.getOutputStream().write(solicitud.toString().getBytes(StandardCharsets.UTF_8));
            if (conexion.getResponseCode() == HttpURLConnection.HTTP_NOT_FOUND) {
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                        .putLong(NO_DISPONIBLE, System.currentTimeMillis()).apply();
                return;
            }
            if (conexion.getResponseCode() < 200 || conexion.getResponseCode() >= 300) {
                return;
            }
            StringBuilder cuerpo = new StringBuilder();
            try (BufferedReader lector = new BufferedReader(new InputStreamReader(
                    conexion.getInputStream(), StandardCharsets.UTF_8))) {
                String linea;
                while ((linea = lector.readLine()) != null) {
                    cuerpo.append(linea);
                }
            }
            JSONObject respuesta = new JSONObject(cuerpo.toString());
            String token = respuesta.optString("token", "");
            long caduca = fecha(respuesta.optString("caduca", ""));
            if (!token.isEmpty() && caduca > 0L) {
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                        .putString(TOKEN, token).putLong(CADUCA, caduca).remove(NO_DISPONIBLE).apply();
                AvisosWorker.ahora(context);   // el widget se rellena en cuanto el móvil queda vinculado
            }
        } catch (Exception ignorada) {
            return;
        } finally {
            if (conexion != null) {
                conexion.disconnect();
            }
        }
    }

    private static long fecha(String texto) {
        try {
            double epoch = Double.parseDouble(texto);
            return (long) (epoch < 1_000_000_000_000L ? epoch * 1000L : epoch);
        } catch (NumberFormatException ignorada) {
            // La API antigua puede devolver una fecha ISO.
        }
        String normalizado = texto.replaceAll("([+-]\\d\\d):(\\d\\d)$", "$1$2").replace("Z", "+0000");
        String[] formatos = {"yyyy-MM-dd'T'HH:mm:ss.SSSZ", "yyyy-MM-dd'T'HH:mm:ssZ",
                "yyyy-MM-dd HH:mm:ss"};
        for (String formato : formatos) {
            try {
                SimpleDateFormat fecha = new SimpleDateFormat(formato, Locale.US);
                fecha.setTimeZone(TimeZone.getTimeZone("UTC"));
                Date resultado = fecha.parse(normalizado);
                if (resultado != null) {
                    return resultado.getTime();
                }
            } catch (Exception ignorada) {
                // Prueba el siguiente formato.
            }
        }
        return 0L;
    }
}
