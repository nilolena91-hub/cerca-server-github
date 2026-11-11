# Cerca server Oracle gratuito

Ogni 10 minuti GitHub prova a creare un server **Always Free** su Oracle Cloud
(Ampere A1 con 1 OCPU e 6 GB, oppure AMD E2.1.Micro). Appena ci riesce, manda un
messaggio su Telegram con l'indirizzo del server. Dopo non fa più niente.

- Usa solo forme gratuite, quindi non può generare costi.
- Le chiavi sono nei **Secrets** del progetto (cifrati, invisibili anche a chi guarda il codice):
  `OCI_CONFIG`, `OCI_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
- `server_ssh.pub` è la parte **pubblica** della chiave del server. Non è segreta: la parte
  privata resta solo sul PC.

Per fermarlo: scheda **Actions** → "Cerca server Oracle gratuito" → menu **⋯** → **Disable workflow**.
