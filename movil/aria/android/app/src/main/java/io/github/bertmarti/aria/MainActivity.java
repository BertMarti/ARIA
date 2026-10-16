package io.github.bertmarti.aria;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import androidx.annotation.Nullable;
import androidx.core.app.ActivityCompat;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import java.net.URLEncoder;
import java.util.concurrent.TimeUnit;

public class MainActivity extends BridgeActivity {
    private static final String PREFS = "CapacitorStorage";
    private static final String URL_KEY = "aria_url";
    private String ariaUrl;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ariaUrl = getSharedPreferences(PREFS, MODE_PRIVATE).getString(URL_KEY, "");
        WebView web = getBridge().getWebView();
        // Se hereda del cliente de Capacitor: sirve la página local (https://localhost) y mantiene el puente con lo nativo.
        web.setWebViewClient(new BridgeWebViewClient(getBridge()) {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return abrirExternoSiHaceFalta(request.getUrl()) || super.shouldOverrideUrlLoading(view, request);
            }
        });
        crearCanal();
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 20);
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("avisos-aria", ExistingPeriodicWorkPolicy.UPDATE,
                new PeriodicWorkRequest.Builder(AvisosWorker.class, 15, TimeUnit.MINUTES).setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build());
        gestionarIntent(getIntent());
        Actualizaciones.comprobar(this, false);
    }

    private boolean abrirExternoSiHaceFalta(Uri uri) {
        if (ariaUrl.isEmpty() && "https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null) {
            ariaUrl = uri.getScheme() + "://" + uri.getHost() + (uri.getPort() > 0 ? ":" + uri.getPort() : "") + "/";
            return false;
        }
        Uri base = ariaUrl.isEmpty() ? null : Uri.parse(ariaUrl);
        boolean mismaCasa = base != null && base.getScheme().equals(uri.getScheme()) && base.getHost().equalsIgnoreCase(uri.getHost()) && base.getPort() == uri.getPort();
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
        boolean local = "localhost".equals(host);
        // El acceso de Cloudflare (código por correo) pasa por <equipo>.cloudflareaccess.com: debe seguir dentro de la app.
        boolean accesoCloudflare = "https".equalsIgnoreCase(uri.getScheme()) && host.endsWith(".cloudflareaccess.com");
        if (ariaUrl.isEmpty() || mismaCasa || local || accesoCloudflare) return false;
        startActivity(new Intent(Intent.ACTION_VIEW, uri));
        return true;
    }

    private void gestionarIntent(Intent intent) {
        if (intent == null) return;
        String accion = intent.getStringExtra("accion");
        if ("cambiar".equals(accion)) { getSharedPreferences(PREFS, MODE_PRIVATE).edit().remove(URL_KEY).apply(); getBridge().getWebView().loadUrl("https://localhost/?cambiar=1"); ariaUrl = ""; return; }
        if ("actualizaciones".equals(accion)) { Actualizaciones.comprobar(this, true); return; }
        if (accion != null && !ariaUrl.isEmpty()) getBridge().getWebView().loadUrl(ariaUrl + "#" + Uri.encode(accion));
        if (Intent.ACTION_SEND.equals(intent.getAction()) && !ariaUrl.isEmpty()) {
            try {
                String texto = intent.getStringExtra(Intent.EXTRA_TEXT);
                String url = intent.getData() == null ? "" : intent.getDataString();
                String destino = ariaUrl + "?text=" + URLEncoder.encode(texto == null ? "" : texto, "UTF-8") + "&url=" + URLEncoder.encode(url == null ? "" : url, "UTF-8");
                getBridge().getWebView().loadUrl(destino);
            } catch (Exception ignored) { }
        }
    }

    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); gestionarIntent(intent); }

    @Override public void onBackPressed() {
        WebView web = getBridge().getWebView();
        if (web.canGoBack() && web.getUrl() != null && !web.getUrl().startsWith("https://localhost")) web.goBack(); else super.onBackPressed();
    }

    private void crearCanal() {
        if (Build.VERSION.SDK_INT >= 26) ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(new NotificationChannel("avisos", getString(R.string.avisos_canal), NotificationManager.IMPORTANCE_DEFAULT));
    }
}
