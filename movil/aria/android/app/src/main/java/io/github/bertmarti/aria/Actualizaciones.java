package io.github.bertmarti.aria;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;

/** Busca en GitHub Releases una versión más nueva de la app («app-vX.Y.Z» con «aria-X.Y.Z.apk») y la instala. */
final class Actualizaciones {
    private static final String API = "https://api.github.com/repos/BertMarti/ARIA/releases?per_page=15";
    private static final Pattern ETIQUETA = Pattern.compile("app-v(\\d+)\\.(\\d+)\\.(\\d+)");
    private static final String ARCHIVO = "aria-actualizacion.apk";

    private Actualizaciones() { }

    /** Como mucho una vez al día salvo que se fuerce (atajo «Buscar actualizaciones»). */
    static void comprobar(Activity actividad, boolean forzar) {
        SharedPreferences prefs = actividad.getPreferences(Context.MODE_PRIVATE);
        long hoy = System.currentTimeMillis() / 86_400_000L;
        if (!forzar && prefs.getLong("actualizacion_dia", -1) == hoy) {
            return;
        }
        prefs.edit().putLong("actualizacion_dia", hoy).apply();
        new Thread(() -> buscar(actividad, forzar)).start();
    }

    private static void buscar(Activity actividad, boolean forzar) {
        String actual = BuildConfig.VERSION_NAME;
        String mejorVersion = null;
        String mejorUrl = null;
        HttpURLConnection conexion = null;
        try {
            conexion = (HttpURLConnection) new URL(API).openConnection();
            conexion.setConnectTimeout(8000);
            conexion.setReadTimeout(8000);
            conexion.setRequestProperty("Accept", "application/vnd.github+json");
            StringBuilder texto = new StringBuilder();
            try (BufferedReader lector = new BufferedReader(
                    new InputStreamReader(conexion.getInputStream(), StandardCharsets.UTF_8))) {
                String linea;
                while ((linea = lector.readLine()) != null) {
                    texto.append(linea);
                }
            }
            JSONArray versiones = new JSONArray(texto.toString());
            for (int i = 0; i < versiones.length(); i++) {
                JSONObject version = versiones.getJSONObject(i);
                if (version.optBoolean("draft") || version.optBoolean("prerelease")) {
                    continue;
                }
                Matcher m = ETIQUETA.matcher(version.optString("tag_name"));
                if (!m.matches()) {
                    continue;
                }
                String numero = m.group(1) + "." + m.group(2) + "." + m.group(3);
                String url = urlApk(version.optJSONArray("assets"), "aria-" + numero + ".apk");
                // Solo versiones MAYORES que la instalada y mayores que la mejor encontrada hasta ahora.
                if (url != null && mayor(numero, actual) && (mejorVersion == null || mayor(numero, mejorVersion))) {
                    mejorVersion = numero;
                    mejorUrl = url;
                }
            }
        } catch (Exception ignorada) {
            return;   // sin red o GitHub no responde: se intentará otro día
        } finally {
            if (conexion != null) {
                conexion.disconnect();
            }
        }
        final String version = mejorVersion;
        final String url = mejorUrl;
        actividad.runOnUiThread(() -> {
            if (version != null) {
                dialogo(actividad, version, url);
            } else if (forzar) {
                new AlertDialog.Builder(actividad).setMessage(R.string.sin_actualizaciones)
                        .setPositiveButton(android.R.string.ok, null).show();
            }
        });
    }

    private static String urlApk(JSONArray adjuntos, String nombre) {
        for (int j = 0; adjuntos != null && j < adjuntos.length(); j++) {
            JSONObject adjunto = adjuntos.optJSONObject(j);
            String url = adjunto == null ? "" : adjunto.optString("browser_download_url");
            // Solo descargas de GitHub y por HTTPS.
            if (adjunto != null && nombre.equals(adjunto.optString("name")) && url.startsWith("https://github.com/")) {
                return url;
            }
        }
        return null;
    }

    static boolean mayor(String a, String b) {
        String[] x = a.split("\\.");
        String[] y = b.split("\\.");
        for (int i = 0; i < 3; i++) {
            int n = i < x.length ? Integer.parseInt(x[i].replaceAll("\\D", "")) : 0;
            int m = i < y.length ? Integer.parseInt(y[i].replaceAll("\\D", "")) : 0;
            if (n != m) {
                return n > m;
            }
        }
        return false;
    }

    private static void dialogo(Activity actividad, String version, String url) {
        new AlertDialog.Builder(actividad)
                .setTitle(actividad.getString(R.string.actualizacion_titulo, version))
                .setPositiveButton(R.string.actualizar, (d, w) -> descargar(actividad, version, url))
                .setNegativeButton(R.string.mas_tarde, null)
                .show();
    }

    private static void descargar(Activity actividad, String version, String url) {
        File destino = new File(actividad.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), ARCHIVO);
        if (destino.exists() && !destino.delete()) {
            return;
        }
        DownloadManager.Request peticion = new DownloadManager.Request(Uri.parse(url))
                .setTitle("ARIA " + version)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalFilesDir(actividad, Environment.DIRECTORY_DOWNLOADS, ARCHIVO);
        DownloadManager gestor = (DownloadManager) actividad.getSystemService(Context.DOWNLOAD_SERVICE);
        long id = gestor.enqueue(peticion);
        BroadcastReceiver alTerminar = new BroadcastReceiver() {
            @Override public void onReceive(Context contexto, Intent intent) {
                if (intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1) != id) {
                    return;
                }
                actividad.unregisterReceiver(this);
                instalar(actividad, destino);
            }
        };
        ContextCompat.registerReceiver(actividad, alTerminar, new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),
                ContextCompat.RECEIVER_EXPORTED);
    }

    /** Android comprueba que la APK nueva esté firmada con la misma llave antes de instalarla. */
    private static void instalar(Activity actividad, File apk) {
        if (Build.VERSION.SDK_INT >= 26 && !actividad.getPackageManager().canRequestPackageInstalls()) {
            actividad.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + actividad.getPackageName())));
            return;
        }
        Uri uri = FileProvider.getUriForFile(actividad, actividad.getPackageName() + ".fileprovider", apk);
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        actividad.startActivity(intent);
    }
}
