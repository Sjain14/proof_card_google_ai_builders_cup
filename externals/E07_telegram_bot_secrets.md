# E07 · Telegram bot + secrets

**Deadline:** 15 Oct · **Unblocks:** P3 Proof Capsule share + verify in Telegram.

## Steps
1. In Telegram open **@BotFather** → `/newbot` → name "Proof Card" → username ending in `bot` ✅ [Bots: how to create](https://core.telegram.org/bots/features#creating-a-new-bot).
2. BotFather shows the token **once on screen**. Do not paste it anywhere except step 3.
3. Store it straight in Secret Manager ✅ [Create a secret](https://cloud.google.com/secret-manager/docs/creating-and-accessing-secrets):
   ```bash
   printf '%s' 'PASTE_TOKEN_HERE' | gcloud secrets create TG_BOT_TOKEN --data-file=-
   openssl rand -hex 32 | tr -d '\n' | gcloud secrets create TG_WEBHOOK_SECRET --data-file=-
   history -c   # clear the token from shell history
   ```
   `TG_WEBHOOK_SECRET` is sent by Telegram in the `X-Telegram-Bot-Api-Secret-Token` header on every webhook call, and the backend rejects calls without it ✅ [setWebhook secret_token](https://core.telegram.org/bots/api#setwebhook).
4. In BotFather:
   - `/setinline` → enable, placeholder "search a proof card" (lets anyone share a card into any chat with `@yourbot`) ✅ [Inline mode](https://core.telegram.org/bots/inline)
   - `/setdescription` → "Forward me any Proof Card. I tell you if it's real or ALTERED."
   - `/setcommands` → `start - open a proof` and `check - verify a forwarded card`
5. DM Agent the **bot username** (public, not a secret).

The webhook itself is set in E09 after the first deploy.

## Done when
Both secrets exist (`gcloud secrets list`), bot username shared, token never left BotFather + Secret Manager.
