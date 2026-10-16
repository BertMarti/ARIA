package io.github.bertmarti.aria;

import android.content.Intent;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

public class AriaEscuchaTileService extends TileService {
    @Override public void onClick() {
        Intent intent = new Intent(this, MainActivity.class).putExtra("accion", "escuchar");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivityAndCollapse(intent);
    }

    @Override public void onStartListening() {
        super.onStartListening();
        getQsTile().setState(EscuchaService.estaActiva(this) ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        getQsTile().updateTile();
    }
}
