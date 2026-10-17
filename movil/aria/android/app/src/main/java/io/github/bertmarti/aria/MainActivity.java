package io.github.bertmarti.aria;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.net.http.SslError;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import android.graphics.Color;
import android.view.View;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import java.net.URLEncoder;
import java.util.concurrent.TimeUnit;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.drawable.Icon;

public class MainActivity extends BridgeActivity {
    private static final String PREFS = "CapacitorStorage";
    private static final String URL_KEY = "aria_url";
    private String ariaUrl = "";
    // Capacitor llama a onNewIntent DENTRO de super.onCreate cuando la app se abre en frío con una acción (widget,
    // atajos): entonces aún no hemos leído la dirección y la app se cerraba. Esa primera llamada se ignora y la
    // acción se atiende al final de onCreate.
    private boolean listo;
    private boolean planB;   // la dirección pública no responde: buscando o usando la de casa
    private String casaActual;   // dirección de casa en uso durante el plan B (null = ninguna responde)

    @Override public void onCreate(Bundle state) {
        Fallos.instalar(this);
        super.onCreate(state);
        ariaUrl = getSharedPreferences(PREFS, MODE_PRIVATE).getString(URL_KEY, "");
        WebView web = getBridge().getWebView();
        aplicarZonaSegura(web);
        // Se mantiene el puente de Capacitor mientras se navega por ARIA.
        web.setWebViewClient(new BridgeWebViewClient(getBridge()) {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return abrirExternoSiHaceFalta(request.getUrl())
                        || super.shouldOverrideUrlLoading(view, request);
            }

            @Override public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                Uri pagina = Uri.parse(url);
                if (esPaginaDeCasa(pagina)) {
                    planB = false;
                    DispositivoApp.vincularEnSegundoPlano(MainActivity.this, ariaUrl);
                    Fallos.enviarPendiente(MainActivity.this, ariaUrl);
                    Casa.actualizar(MainActivity.this, ariaUrl);   // direcciones de casa para el plan B
                    pedirNotificacionesUnaVez();   // ya dentro de ARIA: ahora el permiso tiene sentido
                }
            }

            // Certificado no válido: el de casa (ya validado contra su raíz) se acepta; el resto, nunca. Si el que
            // falla es el de la dirección pública, casi siempre es el bloqueo del operador: se pasa al plan B.
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                if (Casa.aceptar(MainActivity.this, error)) {
                    handler.proceed();
                    return;
                }
                handler.cancel();
                if (esPublica(Uri.parse(error.getUrl()))) activarPlanB();
            }

            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame() && esPublica(request.getUrl())) activarPlanB();
            }
        });
        crearCanal();
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("avisos-aria", ExistingPeriodicWorkPolicy.UPDATE,
                new PeriodicWorkRequest.Builder(AvisosWorker.class, 15, TimeUnit.MINUTES)
                        .setConstraints(new Constraints.Builder()
                                .setRequiredNetworkType(NetworkType.CONNECTED).build()).build());
        listo = true;
        gestionarIntent(getIntent());
        crearAtajoEscucha();
        Actualizaciones.comprobar(this, false);
    }

    private boolean abrirExternoSiHaceFalta(Uri uri) {
        if ("aria".equalsIgnoreCase(uri.getScheme()) && "asistente".equalsIgnoreCase(uri.getHost())) {
            abrirAjustesAsistencia();
            return true;
        }
        if ("aria".equalsIgnoreCase(uri.getScheme()) && "vpn".equalsIgnoreCase(uri.getHost())) {
            abrirVpn();
            return true;
        }
        if ("aria".equalsIgnoreCase(uri.getScheme()) && "reintentar".equalsIgnoreCase(uri.getHost())) {
            planB = false;
            getBridge().getWebView().loadUrl(ariaUrl.isEmpty() ? "https://localhost/" : ariaUrl);
            return true;
        }
        if (ariaUrl.isEmpty() && "https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null) {
            ariaUrl = uri.getScheme() + "://" + uri.getHost()
                    + (uri.getPort() > 0 ? ":" + uri.getPort() : "") + "/";
            return false;
        }
        Uri base = ariaUrl.isEmpty() ? null : Uri.parse(ariaUrl);
        boolean mismaCasa = base != null && base.getScheme().equals(uri.getScheme())
                && base.getHost().equalsIgnoreCase(uri.getHost()) && base.getPort() == uri.getPort()
                || Casa.esCasa(this, uri);   // las direcciones locales del plan B también son ARIA
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
        boolean local = "localhost".equals(host);
        // El acceso de Cloudflare (código por correo) pasa por <equipo>.cloudflareaccess.com: debe seguir dentro de la app.
        boolean accesoCloudflare = "https".equalsIgnoreCase(uri.getScheme()) && host.endsWith(".cloudflareaccess.com");
        if (ariaUrl.isEmpty() || mismaCasa || local || accesoCloudflare) return false;
        startActivity(new Intent(Intent.ACTION_VIEW, uri));
        return true;
    }

    private boolean esPublica(Uri uri) {
        if (ariaUrl.isEmpty() || uri == null || uri.getHost() == null) return false;
        return uri.getHost().equalsIgnoreCase(Uri.parse(ariaUrl).getHost());
    }

    /** La dirección pública falla: se prueba ARIA en casa (wifi o VPN); si tampoco, se explica qué pasa. */
    private void activarPlanB() {
        if (planB) return;
        planB = true;
        new Thread(() -> {
            String local = Casa.buscar(this);
            runOnUiThread(() -> {
                casaActual = local;
                getBridge().getWebView().loadUrl(local != null ? local : "https://localhost/bloqueo.html");
            });
        }, "aria-plan-b").start();
    }

    /** Abre la app de VPN (WG Tunnel o WireGuard) para entrar en casa por HEIMDALL. */
    private void abrirVpn() {
        for (String paquete : new String[]{"com.zaneschepke.wireguardautotunnel", "com.wireguard.android"}) {
            Intent abrir = getPackageManager().getLaunchIntentForPackage(paquete);
            if (abrir != null) {
                startActivity(abrir);
                return;
            }
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.zaneschepke.wireguardautotunnel")));
        } catch (Exception e) {
            startActivity(new Intent(Intent.ACTION_VIEW,
                    Uri.parse("https://play.google.com/store/apps/details?id=com.zaneschepke.wireguardautotunnel")));
        }
    }

    // Al volver a la app: si se estaba en casa por el plan B y la dirección pública ya responde, se vuelve a ella.
    @Override public void onResume() {
        super.onResume();
        WebView web = getBridge() == null ? null : getBridge().getWebView();
        String actual = web == null ? null : web.getUrl();
        if (ariaUrl.isEmpty() || actual == null) return;
        Uri pagina = Uri.parse(actual);
        boolean fuera = Casa.esCasa(this, pagina) || actual.startsWith("https://localhost/bloqueo");
        if (!fuera) return;
        new Thread(() -> {
            if (Casa.publicaAccesible(ariaUrl)) {
                runOnUiThread(() -> { planB = false; casaActual = null; getBridge().getWebView().loadUrl(ariaUrl); });
            } else if (actual.startsWith("https://localhost/bloqueo")) {
                String local = Casa.buscar(this);   // quizá ya se ha conectado la VPN
                if (local != null) runOnUiThread(() -> { casaActual = local; getBridge().getWebView().loadUrl(local); });
            }
        }, "aria-volver").start();
    }

    private void abrirAjustesAsistencia() {
        try {
            startActivity(new Intent(Settings.ACTION_VOICE_INPUT_SETTINGS));
        } catch (Exception ignorada) {
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS));
            } catch (Exception ignoradaTambien) {
                startActivity(new Intent(Settings.ACTION_SETTINGS));
            }
        }
    }

    private void gestionarIntent(Intent intent) {
        if (intent == null) return;
        if (Intent.ACTION_ASSIST.equals(intent.getAction())
                || Intent.ACTION_VOICE_COMMAND.equals(intent.getAction())) {
            intent.putExtra("accion", "hablar");
        }
        String accion = intent.getStringExtra("accion");
        if ("cambiar".equals(accion)) {
            DispositivoApp.borrar(this);
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().remove(URL_KEY).apply();
            getBridge().getWebView().loadUrl("https://localhost/?cambiar=1");
            ariaUrl = "";
            return;
        }
        if ("actualizaciones".equals(accion)) {
            Actualizaciones.comprobar(this, true);
            return;
        }
        if ("escuchar".equals(accion)) {
            alternarEscucha();
            return;
        }
        if ("asistente".equals(accion)) {
            abrirAjustesAsistencia();
            return;
        }
        if (accion != null && !ariaUrl.isEmpty()) {
            // En el plan B, la acción va a la dirección de casa en uso (la pública está bloqueada).
            String base = planB ? casaActual : ariaUrl;
            getBridge().getWebView().loadUrl(base != null ? base + "#" + Uri.encode(accion) : "https://localhost/bloqueo.html");
        }
        if (Intent.ACTION_SEND.equals(intent.getAction()) && !ariaUrl.isEmpty()) {
            try {
                String texto = intent.getStringExtra(Intent.EXTRA_TEXT);
                String url = intent.getData() == null ? "" : intent.getDataString();
                String destino = ariaUrl + "?text="
                        + URLEncoder.encode(texto == null ? "" : texto, "UTF-8")
                        + "&url=" + URLEncoder.encode(url == null ? "" : url, "UTF-8");
                getBridge().getWebView().loadUrl(destino);
            } catch (Exception ignored) { }
        }
    }

    private void alternarEscucha() {
        if (EscuchaService.estaActiva(this)) {
            stopService(new Intent(this, EscuchaService.class));
            return;
        }
        if (Build.VERSION.SDK_INT >= 23
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 31);
            return;
        }
        if (ahorroDeBateria()) return;
        EscuchaService.iniciar(this);
    }

    private boolean ahorroDeBateria() {
        PowerManager energia = (PowerManager) getSystemService(POWER_SERVICE);
        return Build.VERSION.SDK_INT >= 21 && energia.isPowerSaveMode();
    }

    @Override public void onRequestPermissionsResult(int codigo, String[] permisos, int[] resultados) {
        super.onRequestPermissionsResult(codigo, permisos, resultados);
        if (codigo == 31 && resultados.length > 0 && resultados[0] == PackageManager.PERMISSION_GRANTED) {
            EscuchaService.iniciar(this);
        }
    }

    /**
     * Android 15 dibuja la app detrás de la barra de estado, la cámara y la barra de navegación, y el WebView no siempre
     * informa a la web de esos márgenes: se aplican como relleno del contenedor (fondo oscuro de ARIA) y nada queda tapado.
     */
    private void aplicarZonaSegura(WebView web) {
        View contenedor = (View) web.getParent();
        int fondo = Color.parseColor("#070b12");
        contenedor.setBackgroundColor(fondo);
        // Barras del sistema oscuras con iconos claros, como el resto de ARIA (en Android 15 manda el relleno de arriba).
        getWindow().setStatusBarColor(fondo);
        getWindow().setNavigationBarColor(fondo);
        WindowInsetsControllerCompat barras = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        barras.setAppearanceLightStatusBars(false);
        barras.setAppearanceLightNavigationBars(false);
        ViewCompat.setOnApplyWindowInsetsListener(contenedor, (vista, margenes) -> {
            Insets zona = margenes.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout()
                    | WindowInsetsCompat.Type.ime());
            vista.setPadding(zona.left, zona.top, zona.right, zona.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
        ViewCompat.requestApplyInsets(contenedor);
    }

    private boolean notificacionesPedidas;

    private void pedirNotificacionesUnaVez() {
        if (notificacionesPedidas || Build.VERSION.SDK_INT < 33) {
            return;
        }
        notificacionesPedidas = true;
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 20);
        }
    }

    private void crearAtajoEscucha() {
        try {
            crearAtajosDinamicos();
        } catch (RuntimeException e) {
            android.util.Log.w("ARIA", "No se pudieron crear los atajos dinámicos", e);
        }
    }

    private void crearAtajosDinamicos() {
        if (Build.VERSION.SDK_INT < 25) return;
        ShortcutManager gestor = getSystemService(ShortcutManager.class);
        // Android exige acción en los intents de los atajos: sin ella, la app se cerraba al abrirse (visto en el emulador).
        Intent intent = new Intent(Intent.ACTION_VIEW).setClass(this, MainActivity.class).putExtra("accion", "escuchar");
        ShortcutInfo atajo = new ShortcutInfo.Builder(this, "escuchar-aria")
                .setShortLabel(getString(R.string.atajo_escuchar))
                .setIcon(Icon.createWithResource(this, R.drawable.ic_stat_aria))
                .setIntent(intent).build();
        gestor.addDynamicShortcuts(java.util.Collections.singletonList(atajo));
        Intent asistente = new Intent(Intent.ACTION_VIEW).setClass(this, MainActivity.class).putExtra("accion", "asistente");
        ShortcutInfo atajoAsistente = new ShortcutInfo.Builder(this, "asistente-aria")
                .setShortLabel(getString(R.string.asistente_titulo))
                .setIcon(Icon.createWithResource(this, R.drawable.ic_stat_aria))
                .setIntent(asistente).build();
        gestor.addDynamicShortcuts(java.util.Collections.singletonList(atajoAsistente));
    }

    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); if (listo) gestionarIntent(intent); }

    @Override public void onBackPressed() {
        WebView web = getBridge().getWebView();
        if (web.canGoBack() && web.getUrl() != null
                && !web.getUrl().startsWith("https://localhost")) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    private void crearCanal() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager gestor = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            gestor.createNotificationChannel(new NotificationChannel(
                    "avisos", getString(R.string.avisos_canal), NotificationManager.IMPORTANCE_DEFAULT));
        }
    }

    private boolean esPaginaDeCasa(Uri pagina) {
        if (ariaUrl.isEmpty() || pagina.getHost() == null) {
            return false;
        }
        Uri base = Uri.parse(ariaUrl);
        String ruta = pagina.getPath() == null ? "" : pagina.getPath().toLowerCase();
        return base.getHost().equalsIgnoreCase(pagina.getHost())
                && !ruta.contains("login") && !ruta.contains("authorize");
    }
}
