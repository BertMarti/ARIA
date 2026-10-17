package io.github.bertmarti.aria;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.net.http.SslCertificate;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.webkit.CookieManager;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Plan B ante bloqueos del operador (LaLiga bloquea IP de Cloudflare durante el fútbol): ARIA dentro de casa o por
 * la VPN HEIMDALL, en sus direcciones locales y con el certificado de la autoridad propia de la casa (Caddy).
 *
 * Seguridad: solo se acepta un certificado local si (1) el host es una de las direcciones que dio la propia ARIA y
 * (2) su cadena completa se ha validado contra el certificado raíz de casa en una conexión aparte. Para el resto de
 * webs, la WebView sigue rechazando cualquier certificado no válido.
 */
final class Casa {
    private static final String PREFS = "casa_aria";
    private static final String DIRECCIONES = "direcciones";
    private static final String RAIZ = "certificado";
    private static final String HUELLAS = "huellas";

    private Casa() { }

    /** Pide a ARIA (con la sesión de la WebView) sus direcciones de casa y el certificado raíz. En segundo plano. */
    static void actualizar(Context context, String base) {
        if (base == null || base.isEmpty()) return;
        Context app = context.getApplicationContext();
        new Thread(() -> {
            HttpURLConnection conexion = null;
            try {
                conexion = (HttpURLConnection) new URL(base + "api/app/casa").openConnection();
                conexion.setConnectTimeout(8000);
                conexion.setReadTimeout(8000);
                String cookies = CookieManager.getInstance().getCookie(base);
                if (cookies != null) conexion.setRequestProperty("Cookie", cookies);
                if (conexion.getResponseCode() != HttpURLConnection.HTTP_OK) return;
                JSONObject datos = new JSONObject(leer(conexion));
                String pem = datos.optString("certificado", "");
                JSONArray lista = datos.optJSONArray("direcciones");
                if (!pem.contains("BEGIN CERTIFICATE") || lista == null) return;
                raiz(pem);   // que se pueda leer antes de guardarlo
                JSONArray buenas = new JSONArray();
                for (int i = 0; i < lista.length() && buenas.length() < 5; i++) {
                    Uri uri = Uri.parse(lista.optString(i, ""));
                    if ("https".equals(uri.getScheme()) && uri.getHost() != null) {
                        buenas.put("https://" + uri.getHost() + "/");
                    }
                }
                prefs(app).edit().putString(DIRECCIONES, buenas.toString()).putString(RAIZ, pem).apply();
            } catch (Exception ignorada) {
                // Sin datos nuevos se conserva lo anterior.
            } finally {
                if (conexion != null) conexion.disconnect();
            }
        }, "aria-casa").start();
    }

    static List<String> direcciones(Context context) {
        List<String> salida = new ArrayList<>();
        try {
            JSONArray lista = new JSONArray(prefs(context).getString(DIRECCIONES, "[]"));
            for (int i = 0; i < lista.length(); i++) salida.add(lista.getString(i));
        } catch (Exception ignorada) {
            // Lista vacía.
        }
        return salida;
    }

    static boolean esCasa(Context context, Uri uri) {
        if (uri == null || uri.getHost() == null || !"https".equals(uri.getScheme())) return false;
        for (String d : direcciones(context)) {
            if (uri.getHost().equalsIgnoreCase(Uri.parse(d).getHost())) return true;
        }
        return false;
    }

    /**
     * Busca una dirección de casa que responda con un certificado de esta casa. Bloquea: llamar en un hilo.
     * Devuelve la dirección (p. ej. «https://aria.local/») o null si no hay ninguna (fuera de casa sin VPN).
     */
    static String buscar(Context context) {
        String pem = prefs(context).getString(RAIZ, "");
        if (pem.isEmpty()) return null;
        SSLContext tls;
        try {
            tls = contexto(raiz(pem));
        } catch (Exception e) {
            return null;
        }
        for (String direccion : direcciones(context)) {
            HttpsURLConnection conexion = null;
            try {
                conexion = (HttpsURLConnection) new URL(direccion + "health").openConnection();
                conexion.setSSLSocketFactory(tls.getSocketFactory());   // cadena validada contra la raíz de casa
                conexion.setConnectTimeout(3000);
                conexion.setReadTimeout(4000);
                if (conexion.getResponseCode() != HttpURLConnection.HTTP_OK) continue;
                Certificate[] cadena = conexion.getServerCertificates();
                if (cadena.length == 0) continue;
                recordar(context, huella(cadena[0].getEncoded()));
                return direccion;
            } catch (Exception ignorada) {
                // Esta dirección no responde (o no es de esta casa): la siguiente.
            } finally {
                if (conexion != null) conexion.disconnect();
            }
        }
        return null;
    }

    /**
     * Abre `ruta` (p. ej. «api/app/resumen») en la primera dirección de casa que responda, con la cadena validada
     * contra la raíz de casa. El llamante añade cabeceras y lee; devuelve null si no hay ninguna. Bloquea.
     */
    static HttpsURLConnection abrir(Context context, String ruta, String autorizacion) {
        String pem = prefs(context).getString(RAIZ, "");
        if (pem.isEmpty()) return null;
        SSLContext tls;
        try {
            tls = contexto(raiz(pem));
        } catch (Exception e) {
            return null;
        }
        for (String direccion : direcciones(context)) {
            HttpsURLConnection conexion = null;
            try {
                conexion = (HttpsURLConnection) new URL(direccion + ruta).openConnection();
                conexion.setSSLSocketFactory(tls.getSocketFactory());
                conexion.setConnectTimeout(3000);
                conexion.setReadTimeout(8000);
                if (autorizacion != null) conexion.setRequestProperty("Authorization", autorizacion);
                conexion.getResponseCode();   // conecta (y valida el certificado) ya
                return conexion;
            } catch (Exception ignorada) {
                if (conexion != null) conexion.disconnect();
            }
        }
        return null;
    }

    /** ¿Puede la WebView aceptar este certificado? Solo el de una dirección de casa ya validada por buscar(). */
    static boolean aceptar(Context context, SslError error) {
        try {
            if (!esCasa(context, Uri.parse(error.getUrl()))) return false;
            byte[] der = der(error.getCertificate());
            return der != null && prefs(context).getStringSet(HUELLAS, new HashSet<>()).contains(huella(der));
        } catch (Exception e) {
            return false;
        }
    }

    /** ¿Responde la dirección pública con un certificado válido? (para volver a ella cuando se levante el bloqueo). */
    static boolean publicaAccesible(String base) {
        HttpsURLConnection conexion = null;
        try {
            conexion = (HttpsURLConnection) new URL(base + "health").openConnection();
            conexion.setConnectTimeout(5000);
            conexion.setReadTimeout(5000);
            conexion.setInstanceFollowRedirects(false);
            int codigo = conexion.getResponseCode();   // con certificado falso lanza excepción
            return codigo < 500;
        } catch (Exception e) {
            return false;
        } finally {
            if (conexion != null) conexion.disconnect();
        }
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void recordar(Context context, String huella) {
        Set<String> huellas = new HashSet<>(prefs(context).getStringSet(HUELLAS, new HashSet<>()));
        if (huellas.size() > 20) huellas.clear();   // Caddy renueva los certificados locales a menudo
        huellas.add(huella);
        prefs(context).edit().putStringSet(HUELLAS, huellas).apply();
    }

    private static X509Certificate raiz(String pem) throws Exception {
        return (X509Certificate) CertificateFactory.getInstance("X.509")
                .generateCertificate(new ByteArrayInputStream(pem.getBytes(StandardCharsets.US_ASCII)));
    }

    private static SSLContext contexto(X509Certificate raiz) throws Exception {
        KeyStore almacen = KeyStore.getInstance(KeyStore.getDefaultType());
        almacen.load(null, null);
        almacen.setCertificateEntry("casa", raiz);
        TrustManagerFactory fabrica = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        fabrica.init(almacen);
        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, fabrica.getTrustManagers(), null);
        return tls;
    }

    private static byte[] der(SslCertificate certificado) {
        if (certificado == null) return null;
        if (Build.VERSION.SDK_INT >= 29) {
            X509Certificate x509 = certificado.getX509Certificate();
            try {
                return x509 == null ? null : x509.getEncoded();
            } catch (Exception e) {
                return null;
            }
        }
        Bundle estado = SslCertificate.saveState(certificado);
        return estado == null ? null : estado.getByteArray("x509-certificate");
    }

    private static String huella(byte[] der) throws Exception {
        StringBuilder hex = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(der)) hex.append(String.format("%02x", b));
        return hex.toString();
    }

    private static String leer(HttpURLConnection conexion) throws Exception {
        StringBuilder texto = new StringBuilder();
        try (BufferedReader lector = new BufferedReader(new InputStreamReader(conexion.getInputStream(), StandardCharsets.UTF_8))) {
            String linea;
            while ((linea = lector.readLine()) != null && texto.length() < 64_000) texto.append(linea).append('\n');
        }
        return texto.toString();
    }
}
