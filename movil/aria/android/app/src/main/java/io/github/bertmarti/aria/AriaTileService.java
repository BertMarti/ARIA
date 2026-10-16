package io.github.bertmarti.aria;

import android.content.Intent;
import android.service.quicksettings.TileService;

public class AriaTileService extends TileService {
    @Override
    public void onClick() {
        super.onClick();
        String url = getSharedPreferences("CapacitorStorage", MODE_PRIVATE)
                .getString("aria_url", "");
        if (!url.isEmpty()) {
            Intent intent = new Intent(this, MainActivity.class);
            intent.putExtra("accion", "hablar");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivityAndCollapse(intent);
        }
    }
}
