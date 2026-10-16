package io.github.bertmarti.aria.lite;

import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import androidx.appcompat.app.AppCompatActivity;

public class ConfigActivity extends AppCompatActivity {
    private static final String PREFS = "aria_lite";
    private static final String ADDRESS = "address";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_config);
        EditText address = findViewById(R.id.address);
        String saved = getSharedPreferences(PREFS, MODE_PRIVATE).getString(ADDRESS, "");
        address.setText(saved);
        Button connect = findViewById(R.id.connect);
        connect.setOnClickListener(view -> {
            String value = address.getText().toString().trim();
            if (!isValidAddress(value)) {
                address.setError(getString(R.string.config_invalid));
                return;
            }
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(ADDRESS, normalize(value)).apply();
            startActivity(new Intent(this, LauncherActivity.class));
            finish();
        });
    }

    private static boolean isValidAddress(String value) {
        try {
            Uri uri = Uri.parse(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null && !uri.getHost().isEmpty()
                    && uri.getUserInfo() == null && uri.getQuery() == null
                    && uri.getFragment() == null
                    && (uri.getPath() == null || uri.getPath().isEmpty() || "/".equals(uri.getPath()));
        } catch (IllegalArgumentException error) {
            return false;
        }
    }

    private static String normalize(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
