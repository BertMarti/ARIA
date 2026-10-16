package io.github.bertmarti.aria;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Environment;
import android.provider.Settings;
import androidx.core.content.FileProvider;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;

final class Actualizaciones {
    private static final String API = "https://api.github.com/repos/BertMarti/ARIA/releases?per_page=15";
    static void comprobar(Activity activity, boolean forzar) {
        android.content.SharedPreferences p = activity.getPreferences(Context.MODE_PRIVATE); long hoy = System.currentTimeMillis() / 86400000L;
        if (!forzar && p.getLong("actualizacion_dia", -1) == hoy) return; p.edit().putLong("actualizacion_dia", hoy).apply();
        new Thread(() -> { try { HttpURLConnection c = (HttpURLConnection) new URL(API).openConnection(); c.setConnectTimeout(6000); c.setReadTimeout(6000); BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream())); StringBuilder s = new StringBuilder(); String l; while ((l = r.readLine()) != null) s.append(l); JSONArray releases = new JSONArray(s.toString()); String version = null, download = null; for (int i=0;i<releases.length();i++) { JSONObject rel = releases.getJSONObject(i); Matcher m = Pattern.compile("app-v(\\d+\\.\\d+\\.\\d+)").matcher(rel.optString("tag_name")); if (!m.matches()) continue; JSONArray assets = rel.optJSONArray("assets"); for (int j=0; assets != null && j<assets.length(); j++) { JSONObject a=assets.getJSONObject(j); if (a.optString("name").equals("aria-" + m.group(1) + ".apk")) { version=m.group(1); download=a.optString("browser_download_url"); break; } } if (version != null && mayor(version, BuildConfig.VERSION_NAME)) break; } if (version != null) { String v=version, d=download; activity.runOnUiThread(() -> dialogo(activity, v, d)); } c.disconnect(); } catch (Exception ignored) {} }).start();
    }
    private static boolean mayor(String a, String b) { String[] x=a.split("\\."), y=b.split("\\."); for(int i=0;i<3;i++){int n=Integer.parseInt(x[i]),m=Integer.parseInt(y[i]);if(n!=m)return n>m;}return false; }
    private static void dialogo(Activity a, String version, String url) { new android.app.AlertDialog.Builder(a).setTitle(a.getString(R.string.actualizacion_titulo, version)).setPositiveButton(R.string.actualizar, (d,w) -> descargar(a, url)).setNegativeButton(R.string.mas_tarde, null).show(); }
    private static void descargar(Activity a, String url) { DownloadManager.Request q = new DownloadManager.Request(Uri.parse(url)).setTitle("ARIA " + url.substring(url.indexOf("aria-")+5, url.length()-4)).setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED).setDestinationInExternalFilesDir(a, Environment.DIRECTORY_DOWNLOADS, "aria-update.apk"); DownloadManager dm=(DownloadManager)a.getSystemService(Context.DOWNLOAD_SERVICE); long id=dm.enqueue(q); androidx.core.content.ContextCompat.registerReceiver(a,new android.content.BroadcastReceiver(){public void onReceive(Context c,Intent i){if(i.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID,-1)!=id)return;Uri file=dm.getUriForDownloadedFile(id);if(file!=null) instalar(a,file);}},new android.content.IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED); }
    private static void instalar(Activity a, Uri file) { if (android.os.Build.VERSION.SDK_INT >= 26 && !a.getPackageManager().canRequestPackageInstalls()) { a.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:"+a.getPackageName()))); return; } Intent i=new Intent(Intent.ACTION_VIEW, FileProvider.getUriForFile(a,a.getPackageName()+".fileprovider",new java.io.File(a.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),"aria-update.apk"))); i.setDataAndType(FileProvider.getUriForFile(a,a.getPackageName()+".fileprovider",new java.io.File(a.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),"aria-update.apk")),"application/vnd.android.package-archive"); i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); a.startActivity(i); }
}
