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
import org.json.JSONArray;
import org.json.JSONObject;

public class AvisosWorker extends Worker {
    public AvisosWorker(@NonNull Context context, @NonNull WorkerParameters params) { super(context, params); }
    @NonNull @Override public Result doWork() {
        String base = getApplicationContext().getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE).getString("aria_url", "");
        if (base.isEmpty()) return Result.success();
        HttpURLConnection conn = null;
        try {
            URL url = new URL(base + "api/avisos"); conn = (HttpURLConnection) url.openConnection(); conn.setConnectTimeout(8000); conn.setReadTimeout(8000); String cookies = CookieManager.getInstance().getCookie(base); if (cookies != null) conn.setRequestProperty("Cookie", cookies);
            String contentType = conn.getContentType(); if (conn.getResponseCode() != 200 || contentType == null || !contentType.toLowerCase().contains("json")) return Result.success();
            BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream())); StringBuilder body = new StringBuilder(); String line; while ((line = reader.readLine()) != null) body.append(line);
            JSONArray avisos = new JSONObject(body.toString()).optJSONArray("avisos"); if (avisos == null) return Result.success();
            android.content.SharedPreferences seen = getApplicationContext().getSharedPreferences("avisos", Context.MODE_PRIVATE); android.content.SharedPreferences.Editor edit = seen.edit();
            for (int i = 0; i < avisos.length(); i++) { JSONObject aviso = avisos.optJSONObject(i); if (aviso == null || aviso.optBoolean("leido", true)) continue; String id = aviso.optString("id"); if (id.isEmpty() || seen.contains(id)) continue; publicar(base, aviso); edit.putBoolean(id, true); }
            edit.apply(); return Result.success();
        } catch (Exception e) { return Result.success(); } finally { if (conn != null) conn.disconnect(); }
    }
    private void publicar(String base, JSONObject aviso) {
        Intent open = new Intent(getApplicationContext(), MainActivity.class); open.setData(android.net.Uri.parse(base + "#avisos")); PendingIntent pi = PendingIntent.getActivity(getApplicationContext(), aviso.optString("id").hashCode(), open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder n = new NotificationCompat.Builder(getApplicationContext(), "avisos").setSmallIcon(R.drawable.ic_stat_aria).setContentTitle("ARIA").setContentText(aviso.optString("titulo", aviso.optString("texto", "Nuevo aviso"))).setAutoCancel(true).setContentIntent(pi); androidx.core.app.NotificationManagerCompat.from(getApplicationContext()).notify(aviso.optString("id").hashCode(), n.build());
    }
}
