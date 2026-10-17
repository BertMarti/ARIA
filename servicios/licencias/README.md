# Servidor de licencias

1. En Lemon Squeezy, crea la tienda y un producto de suscripción con las claves de licencia activadas y un máximo de 2 activaciones.
2. Crea el proyecto: `npx wrangler login` y `npx wrangler kv namespace create LICENCIAS`.
3. Copia `wrangler.toml.ejemplo` a `wrangler.toml`, pon los identificadores numéricos de tienda y producto, y sustituye el ID del namespace.
4. Carga la clave privada sin que salga en pantalla (va directa de openssl a Cloudflare):
   ```bash
   openssl pkey -in ~/homelab/.claves-premium/privada.pem -outform DER | base64 -w0 | npx wrangler secret put CLAVE_PRIVADA_PKCS8_B64
   ```
5. Comprueba las pruebas (`node --test prueba.mjs`) y publica con `npx wrangler deploy`.
6. En ARIA, configura `ARIA_PREMIUM_SERVIDOR=https://licencias.example.com` en `.env`.

El Worker no guarda datos de clientes: solo conserva en KV el `instance_id` de Lemon Squeezy y un contador temporal por IP.
