package io.github.bertmarti.aria;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.BatteryManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import androidx.core.content.ContextCompat;
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import org.json.JSONArray;
import org.json.JSONObject;
import org.vosk.KaldiRecognizer;
import org.vosk.Model;

public class EscuchaService extends Service {
    private static final String PREFS = "escucha_aria";
    private static final String ACTIVA = "activa";
    private static final String CANAL = "escucha";
    private static final int NOTIFICACION = 320;
    private static final String MODELO_URL = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip";
    private volatile boolean ejecutando;
    private AudioRecord grabadora;
    private Model modelo;

    static boolean estaActiva(Context context) {
        return context.getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean(ACTIVA, false);
    }

    static void iniciar(Context context) {
        Intent intent = new Intent(context, EscuchaService.class);
        ContextCompat.startForegroundService(context, intent);
    }

    @Override public void onCreate() {
        super.onCreate();
        crearCanal();
        startForeground(NOTIFICACION, notificacion(getString(R.string.escucha_notificacion)));
        if (bateriaBaja() || ahorroDeBateria()) {
            stopSelf();
            return;
        }
        ejecutando = true;
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(ACTIVA, true).apply();
        new Thread(this::preparar).start();
    }

    private void preparar() {
        try {
            File directorio = obtenerModelo();
            modelo = new Model(directorio.getAbsolutePath());
            escuchar();
        } catch (Exception ignorada) {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(ACTIVA, false).apply();
            stopSelf();
        }
    }

    private File obtenerModelo() throws Exception {
        File destino = new File(getFilesDir(), "vosk-es");
        if (destino.isDirectory()) return destino;
        File zip = new File(getFilesDir(), "vosk-es.zip");
        descargar(zip);
        if (zip.length() <= 20L * 1024L * 1024L) throw new IllegalStateException("modelo pequeño");
        File temporal = new File(getFilesDir(), "vosk-es-tmp");
        borrar(temporal);
        descomprimir(zip, temporal);
        File[] hijos = temporal.listFiles();
        File raiz = hijos != null && hijos.length == 1 && hijos[0].isDirectory() ? hijos[0] : temporal;
        if (!raiz.renameTo(destino)) throw new IllegalStateException("modelo no disponible");
        zip.delete();
        return destino;
    }

    private void descargar(File destino) throws Exception {
        HttpURLConnection conexion = (HttpURLConnection) new URL(MODELO_URL).openConnection();
        conexion.setConnectTimeout(15000);
        conexion.setReadTimeout(30000);
        int total = conexion.getContentLength();
        try (InputStream entrada = new BufferedInputStream(conexion.getInputStream());
             BufferedOutputStream salida = new BufferedOutputStream(new FileOutputStream(destino))) {
            byte[] buffer = new byte[8192];
            int leidos;
            long acumulado = 0L;
            int anterior = -1;
            while ((leidos = entrada.read(buffer)) != -1) {
                salida.write(buffer, 0, leidos);
                acumulado += leidos;
                int progreso = total > 0 ? (int) (acumulado * 100L / total) : anterior;
                if (progreso != anterior) {
                    anterior = progreso;
                    actualizar(getString(R.string.escucha_descargando, progreso));
                }
            }
        } finally {
            conexion.disconnect();
        }
    }

    private void descomprimir(File zip, File destino) throws Exception {
        String canonico = destino.getCanonicalPath() + File.separator;
        try (ZipInputStream entrada = new ZipInputStream(new FileInputStream(zip))) {
            ZipEntry entradaZip;
            byte[] buffer = new byte[8192];
            while ((entradaZip = entrada.getNextEntry()) != null) {
                File salida = new File(destino, entradaZip.getName());
                if (!salida.getCanonicalPath().startsWith(canonico)) throw new SecurityException("zip slip");
                if (entradaZip.isDirectory()) {
                    salida.mkdirs();
                } else {
                    File padre = salida.getParentFile();
                    if (padre != null) padre.mkdirs();
                    try (BufferedOutputStream flujo = new BufferedOutputStream(new FileOutputStream(salida))) {
                        int leidos;
                        while ((leidos = entrada.read(buffer)) != -1) flujo.write(buffer, 0, leidos);
                    }
                }
            }
        }
    }

    private void escuchar() throws Exception {
        int tamaño = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT);
        grabadora = new AudioRecord(MediaRecorder.AudioSource.MIC, 16000, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, Math.max(tamaño, 8192));
        try (KaldiRecognizer reconocedor = new KaldiRecognizer(modelo, 16000, "[\"aria\", \"[unk]\"]")) {
            byte[] buffer = new byte[4096];
            grabadora.startRecording();
            while (ejecutando && !bateriaBaja() && !ahorroDeBateria()) {
                int leidos = grabadora.read(buffer, 0, buffer.length);
                if (leidos > 0 && reconocedor.acceptWaveForm(buffer, leidos) && esAria(reconocedor.getResult())) {
                    detectar();
                    Thread.sleep(3000L);
                }
            }
            if (ejecutando) stopSelf();
        } finally {
            grabadora.stop();
            grabadora.release();
        }
    }

    private boolean esAria(String resultado) {
        try {
            JSONObject json = new JSONObject(resultado);
            if (!"aria".equalsIgnoreCase(json.optString("text"))) return false;
            JSONArray resultados = json.optJSONArray("result");
            return resultados != null && resultados.length() > 0
                    && resultados.getJSONObject(0).optDouble("conf", 0.0) >= 0.55;
        } catch (Exception ignorada) {
            return false;
        }
    }

    private void detectar() {
        Vibrator vibrador = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) vibrador.vibrate(VibrationEffect.createOneShot(80, VibrationEffect.DEFAULT_AMPLITUDE));
        Intent intent = new Intent(this, MainActivity.class).putExtra("accion", "hablar");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        try {
            startActivity(intent);
        } catch (Exception ignorada) {
            Intent pantalla = new Intent(this, MainActivity.class).putExtra("accion", "hablar");
            PendingIntent pending = PendingIntent.getActivity(this, 321, pantalla,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification.Builder aviso = constructorNotificacion()
                    .setSmallIcon(R.drawable.ic_stat_aria).setContentTitle(getString(R.string.app_name))
                    .setContentText(getString(R.string.escucha_notificacion)).setFullScreenIntent(pending, true)
                    .setAutoCancel(true);
            getSystemService(NotificationManager.class).notify(NOTIFICACION + 1, aviso.build());
        }
    }

    private Notification notificacion(String texto) {
        Intent parar = new Intent(this, EscuchaService.class).setAction("parar");
        PendingIntent accion = PendingIntent.getService(this, 322, parar,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder aviso = constructorNotificacion().setSmallIcon(R.drawable.ic_stat_aria)
                .setContentTitle(getString(R.string.app_name)).setContentText(texto).setOngoing(true)
                .addAction(new Notification.Action.Builder(null, getString(R.string.escucha_parar), accion).build());
        return aviso.build();
    }

    private Notification.Builder constructorNotificacion() {
        if (Build.VERSION.SDK_INT >= 26) return new Notification.Builder(this, CANAL);
        return new Notification.Builder(this);
    }

    private void actualizar(String texto) {
        getSystemService(NotificationManager.class).notify(NOTIFICACION, notificacion(texto));
    }

    private boolean bateriaBaja() {
        BatteryManager bateria = (BatteryManager) getSystemService(BATTERY_SERVICE);
        return bateria.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) < 15;
    }

    private boolean ahorroDeBateria() {
        PowerManager energia = (PowerManager) getSystemService(POWER_SERVICE);
        return Build.VERSION.SDK_INT >= 21 && energia.isPowerSaveMode();
    }

    private void crearCanal() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel canal = new NotificationChannel(CANAL, getString(R.string.escucha_notificacion),
                    NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(canal);
        }
    }

    private void borrar(File archivo) {
        if (archivo.isDirectory()) {
            File[] hijos = archivo.listFiles();
            if (hijos != null) for (File hijo : hijos) borrar(hijo);
        }
        archivo.delete();
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        if (intent != null && "parar".equals(intent.getAction())) stopSelf();
        return START_NOT_STICKY;
    }

    @Override public void onDestroy() {
        ejecutando = false;
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean(ACTIVA, false).apply();
        if (modelo != null) modelo.close();
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
