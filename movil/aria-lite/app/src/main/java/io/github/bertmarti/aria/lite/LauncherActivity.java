package io.github.bertmarti.aria.lite;

import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;

public class LauncherActivity extends com.google.androidbrowserhelper.trusted.LauncherActivity {
    private static final String PREFS = "aria_lite";
    private static final String ADDRESS = "address";
    private String launchingUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        SharedPreferences preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (preferences.getString(ADDRESS, null) == null) {
            startActivity(new Intent(this, ConfigActivity.class));
            finish();
            return;
        }
        launchingUrl = buildUrl(preferences.getString(ADDRESS, ""), getIntent());
        super.onCreate(savedInstanceState);
    }

    @Override
    protected Uri getLaunchingUrl() {
        return Uri.parse(launchingUrl != null ? launchingUrl : "about:blank");
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent.getData() != null && "cambiar".equals(intent.getData().getFragment())) {
            startActivity(new Intent(this, ConfigActivity.class));
        }
    }

    private static String buildUrl(String address, Intent intent) {
        Uri data = intent.getData();
        if (data != null && data.getFragment() != null) {
            if ("cambiar".equals(data.getFragment())) {
                return address;
            }
            return address + "#" + data.getFragment();
        }
        if (Intent.ACTION_SEND.equals(intent.getAction())) {
            Uri.Builder builder = Uri.parse(address).buildUpon();
            String text = intent.getStringExtra(Intent.EXTRA_TEXT);
            String subject = intent.getStringExtra(Intent.EXTRA_SUBJECT);
            if (text != null && !text.isEmpty()) {
                if (text.startsWith("http://") || text.startsWith("https://")) {
                    builder.appendQueryParameter("url", text);
                } else {
                    builder.appendQueryParameter("text", text);
                }
            }
            if (subject != null && !subject.isEmpty()) {
                builder.appendQueryParameter("text", subject);
            }
            return builder.build().toString();
        }
        return address;
    }
}
