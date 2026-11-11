"""Cerca server: prova a creare il server GRATUITO su Oracle finche' non trova posto,
poi ti avvisa su Telegram.

- Usa SOLO forme "Always Free": Ampere A1 (1 OCPU, 6 GB) oppure AMD E2.1.Micro.
  Non crea nient'altro che costi.
- Prova ogni ~5 minuti (Oracle libera i posti a orari imprevedibili).
- Se manca, crea la rete (VCN + sottorete pubblica) e la chiave di accesso SSH.
- Quando ci riesce: salva l'indirizzo per CARICA_SUL_SERVER.bat e ti scrive su Telegram.

Accesso: chiave API di Oracle in deploy/oci/ (config + chiave privata), creata da te.
La password di Oracle non viene mai usata.
"""
import os
import random
import sys
import time
from datetime import datetime

QUI = os.path.dirname(os.path.abspath(__file__))
PROGETTO = os.path.dirname(QUI)
CARTELLA_OCI = os.path.join(QUI, "oci")
CONFIG = os.path.join(CARTELLA_OCI, "config")
CHIAVE_API = os.path.join(CARTELLA_OCI, "oci_api_key.pem")
CHIAVE_SSH = os.path.join(QUI, "server_ssh.key")
CHIAVE_SSH_PUB = os.path.join(QUI, "server_ssh.pub")      # sul telefono c'e' solo la parte pubblica
MEMORIA_SERVER = os.path.join(QUI, "server.txt")
PC_CHIAVE = os.path.join(QUI, "pc_chiave.txt")            # dove sta la chiave privata sul PC
SUL_TELEFONO = "com.termux" in os.environ.get("PREFIX", "")
# Su GitHub: un solo giro di tentativi per esecuzione (GitHub lo rilancia ogni 10 minuti)
UNA_VOLTA = os.environ.get("CERCA_UNA_VOLTA") == "1"
PROVA_MANUALE = os.environ.get("AVVISO_PROVA") == "1"

NOME = "mio-capitale"
NOME_RETE = "mio-capitale-rete"
FORME = [
    ("VM.Standard.A1.Flex", {"ocpus": 1, "memory_in_gbs": 6}),     # Ampere: la migliore
    ("VM.Standard.E2.1.Micro", None),                             # AMD: piu' piccola, va bene uguale
]
ATTESA = 300                    # secondi tra un giro di tentativi e il successivo
STATI_VIVI = ("PROVISIONING", "STARTING", "RUNNING", "STOPPING", "STOPPED")


def stampa(testo):
    print(f"[{datetime.now():%d/%m %H:%M}] {testo}", flush=True)


# ----------------------------------------------------------------------
#  Telegram (stesse chiavi del bot, dal file .env)
# ----------------------------------------------------------------------
def leggi_env():
    """Sul PC: il .env del progetto. Sul telefono: telegram.env del pacchetto."""
    valori = {}
    for p in (os.path.join(PROGETTO, ".env"), os.path.join(QUI, "telegram.env")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for riga in f:
                    riga = riga.strip()
                    if riga and not riga.startswith("#") and "=" in riga:
                        k, v = riga.split("=", 1)
                        valori.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return valori


def telegram(testo):
    env = leggi_env()
    token = env.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN")        # su GitHub: dai Secrets
    chat = env.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": testo}, timeout=15)
    except Exception as e:
        stampa(f"Telegram non raggiungibile: {e}")


# ----------------------------------------------------------------------
#  configurazione guidata della chiave API
# ----------------------------------------------------------------------
def crea_config_da_anteprima(testo, cartella=CARTELLA_OCI):
    """Dal riquadro 'Anteprima file di configurazione' di Oracle al file config."""
    campi = {}
    for riga in testo.splitlines():
        if "=" in riga:
            k, v = riga.split("=", 1)
            campi[k.strip()] = v.strip()
    mancanti = [k for k in ("user", "fingerprint", "tenancy", "region") if not campi.get(k)]
    if mancanti:
        raise ValueError("Nel testo incollato mancano: " + ", ".join(mancanti))
    for k in ("user", "tenancy"):
        if not campi[k].startswith("ocid1."):
            raise ValueError(f"Il valore di '{k}' non sembra un OCID di Oracle.")
    os.makedirs(cartella, exist_ok=True)
    with open(os.path.join(cartella, "config"), "w", encoding="utf-8") as f:
        f.write("[DEFAULT]\n")
        for k in ("user", "fingerprint", "tenancy", "region"):
            f.write(f"{k}={campi[k]}\n")
        f.write(f"key_file={os.path.join(cartella, 'oci_api_key.pem')}\n")
    return campi


def configurazione_guidata():
    print()
    print("=== Prima configurazione: chiave API di Oracle (solo una volta) ===")
    print("1. Su cloud.oracle.com: icona del profilo in alto a destra > 'Il mio profilo'.")
    print("2. In basso a sinistra: 'Chiavi API' > 'Aggiungi chiave API'.")
    print("3. Lascia 'Genera coppia di chiavi API' e clicca 'Scarica chiave privata'.")
    print(f"4. Sposta il file scaricato in questa cartella e rinominalo esattamente:")
    print(f"      {CHIAVE_API}")
    print("5. Su Oracle clicca 'Aggiungi'. Compare 'Anteprima file di configurazione':")
    print("   copia TUTTO il testo del riquadro e incollalo qui sotto,")
    print("   poi premi Invio su una riga vuota.")
    print()
    righe = []
    while True:
        try:
            r = input()
        except EOFError:
            break
        if not r.strip() and righe:
            break
        righe.append(r)
    crea_config_da_anteprima("\n".join(righe))
    print("Configurazione salvata.")


def pronto():
    return os.path.exists(CONFIG) and os.path.exists(CHIAVE_API)


def config_da_ambiente():
    """Su GitHub la configurazione arriva dai Secrets OCI_CONFIG e OCI_KEY."""
    testo, chiave = os.environ.get("OCI_CONFIG"), os.environ.get("OCI_KEY")
    if not (testo and chiave):
        return False
    crea_config_da_anteprima(testo, CARTELLA_OCI)
    with open(CHIAVE_API, "w", encoding="utf-8") as f:
        f.write(chiave.strip() + "\n")
    try:
        os.chmod(CHIAVE_API, 0o600)
    except OSError:
        pass
    return True


def trova_chiave_scaricata(cartelle=None):
    """Sul telefono la chiave scaricata da Oracle finisce in Download: la cerco da solo."""
    import glob
    import shutil
    cartelle = cartelle or [os.path.expanduser("~/storage/downloads"),
                            os.path.expanduser("~/storage/shared/Download")]
    candidati = []
    for c in cartelle:
        for p in glob.glob(os.path.join(c, "**", "*.pem"), recursive=True):
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    if "PRIVATE KEY" in f.read(200):
                        candidati.append(p)
            except OSError:
                pass
    if not candidati:
        return None
    migliore = max(candidati, key=os.path.getmtime)
    os.makedirs(CARTELLA_OCI, exist_ok=True)
    shutil.copyfile(migliore, CHIAVE_API)
    try:
        os.chmod(CHIAVE_API, 0o600)
    except OSError:
        pass
    return migliore


# ----------------------------------------------------------------------
#  Oracle
# ----------------------------------------------------------------------
def e_mancanza_posto(errore):
    msg = (getattr(errore, "message", "") or str(errore)).lower()
    return "capacity" in msg or getattr(errore, "status", 0) == 500


def e_troppe_richieste(errore):
    return getattr(errore, "status", 0) == 429 or "toomanyrequests" in str(getattr(errore, "code", "")).lower()


def chiave_ssh():
    """Coppia di chiavi per entrare nel server (la privata resta solo sul tuo PC)."""
    if not os.path.exists(CHIAVE_SSH) and os.path.exists(CHIAVE_SSH_PUB):
        with open(CHIAVE_SSH_PUB, encoding="utf-8") as f:      # telefono: la privata resta sul PC
            return f.read().strip()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    if not os.path.exists(CHIAVE_SSH):
        k = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        with open(CHIAVE_SSH, "wb") as f:
            f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                    serialization.NoEncryption()))
    with open(CHIAVE_SSH, "rb") as f:
        k = serialization.load_ssh_private_key(f.read(), password=None)
    return k.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                       serialization.PublicFormat.OpenSSH).decode() + " mio-capitale"


def sottorete_pubblica(oci, rete, compartimento):
    """Usa una sottorete pubblica esistente o crea la rete da zero."""
    m = oci.core.models
    for vcn in rete.list_vcns(compartimento).data:
        if vcn.lifecycle_state != "AVAILABLE":
            continue
        for s in rete.list_subnets(compartimento, vcn_id=vcn.id).data:
            if s.lifecycle_state == "AVAILABLE" and not s.prohibit_public_ip_on_vnic:
                return s.id
    stampa("Creo la rete del server (una volta sola)...")
    vcn = rete.create_vcn(m.CreateVcnDetails(compartment_id=compartimento, cidr_blocks=["10.0.0.0/16"],
                                             display_name=NOME_RETE, dns_label="miocapitale")).data
    oci.wait_until(rete, rete.get_vcn(vcn.id), "lifecycle_state", "AVAILABLE", max_wait_seconds=300)
    gw = rete.create_internet_gateway(m.CreateInternetGatewayDetails(
        compartment_id=compartimento, vcn_id=vcn.id, is_enabled=True, display_name=NOME_RETE + "-internet")).data
    oci.wait_until(rete, rete.get_internet_gateway(gw.id), "lifecycle_state", "AVAILABLE", max_wait_seconds=300)
    rete.update_route_table(vcn.default_route_table_id, m.UpdateRouteTableDetails(route_rules=[
        m.RouteRule(destination="0.0.0.0/0", destination_type="CIDR_BLOCK", network_entity_id=gw.id)]))
    sub = rete.create_subnet(m.CreateSubnetDetails(
        compartment_id=compartimento, vcn_id=vcn.id, cidr_block="10.0.0.0/24", display_name=NOME_RETE + "-pubblica",
        dns_label="pubblica", prohibit_public_ip_on_vnic=False)).data
    oci.wait_until(rete, rete.get_subnet(sub.id), "lifecycle_state", "AVAILABLE", max_wait_seconds=300)
    return sub.id


def immagine_ubuntu(calcolo, compartimento, forma):
    imgs = calcolo.list_images(compartimento, operating_system="Canonical Ubuntu", operating_system_version="24.04",
                               shape=forma, sort_by="TIMECREATED", sort_order="DESC").data
    imgs = [i for i in imgs if "minimal" not in (i.display_name or "").lower()]
    return imgs[0].id if imgs else None


def server_esistente(calcolo, compartimento):
    for i in calcolo.list_instances(compartimento, display_name=NOME).data:
        if i.lifecycle_state in STATI_VIVI:
            return i
    return None


def ip_pubblico(oci, calcolo, rete, compartimento, id_server):
    for a in calcolo.list_vnic_attachments(compartimento, instance_id=id_server).data:
        if a.lifecycle_state == "ATTACHED":
            ip = rete.get_vnic(a.vnic_id).data.public_ip
            if ip:
                return ip
    return None


def tieni_sveglio():
    """Windows: niente sospensione finche' la ricerca e' in corso (si annulla da solo alla chiusura)."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM_REQUIRED
        except Exception:
            pass


def main():
    tieni_sveglio()
    try:
        import oci
    except ImportError:
        sys.exit("Manca la libreria di Oracle: lancia CERCA_SERVER.bat (la installa da solo).")
    if not pronto() and not config_da_ambiente():
        if not os.path.exists(CONFIG):
            configurazione_guidata()
        if not os.path.exists(CHIAVE_API):
            trovata = trova_chiave_scaricata() if SUL_TELEFONO else None
            if trovata:
                stampa(f"Chiave Oracle trovata in Download: {os.path.basename(trovata)}")
            else:
                sys.exit(f"Manca la chiave privata: mettila qui con questo nome esatto:\n  {CHIAVE_API}"
                         + ("\n(Sul telefono: scaricala da Oracle con 'Scarica chiave privata' e rilancia.)"
                            if SUL_TELEFONO else ""))

    config = oci.config.from_file(CONFIG)
    oci.config.validate_config(config)
    compartimento = config["tenancy"]
    identita = oci.identity.IdentityClient(config)
    calcolo = oci.core.ComputeClient(config)
    rete = oci.core.VirtualNetworkClient(config)

    stampa("Collegato a Oracle (regione " + config["region"] + ").")
    gia = server_esistente(calcolo, compartimento)
    if gia:
        stampa(f"Il server '{NOME}' esiste già ({gia.lifecycle_state}): non ne creo un altro.")
        if UNA_VOLTA and not PROVA_MANUALE:
            return                                  # GitHub: gia' trovato, nessun messaggio ripetuto
        id_server = gia.id
    else:
        zone = [z.name for z in identita.list_availability_domains(compartimento).data]
        sottorete = sottorete_pubblica(oci, rete, compartimento)
        pubblica = chiave_ssh()
        immagini = {f: immagine_ubuntu(calcolo, compartimento, f) for f, _ in FORME}
        if UNA_VOLTA:
            stampa("Un giro di tentativi (GitHub riprova da solo tra 10 minuti).")
            if PROVA_MANUALE:
                telegram("✅ Cerca server su GitHub: configurazione corretta! Provo ogni 10 minuti e "
                         "ti scrivo appena trovo il server.")
        else:
            stampa("Inizio la ricerca di un posto libero. Lascia questa finestra aperta e il PC acceso.")
            telegram("🔎 Ho iniziato a cercare un server gratuito su Oracle. Ti scrivo appena lo trovo.")
        tentativi, ultimo_avviso, id_server = 0, time.time(), None
        while not id_server:
            tentativi += 1
            for forma, dimensioni in FORME:
                if not immagini.get(forma):
                    continue
                for zona in zone:
                    m = oci.core.models
                    dettagli = m.LaunchInstanceDetails(
                        availability_domain=zona, compartment_id=compartimento, display_name=NOME, shape=forma,
                        shape_config=m.LaunchInstanceShapeConfigDetails(**dimensioni) if dimensioni else None,
                        source_details=m.InstanceSourceViaImageDetails(image_id=immagini[forma],
                                                                       boot_volume_size_in_gbs=50),
                        create_vnic_details=m.CreateVnicDetails(subnet_id=sottorete, assign_public_ip=True),
                        metadata={"ssh_authorized_keys": pubblica})
                    try:
                        id_server = calcolo.launch_instance(dettagli).data.id
                        stampa(f"POSTO TROVATO: {forma} in {zona}!")
                        break
                    except oci.exceptions.ServiceError as e:
                        if e_troppe_richieste(e):
                            stampa("Oracle chiede di rallentare: aspetto un po' di più.")
                            time.sleep(120)
                        elif e_mancanza_posto(e):
                            stampa(f"Tentativo {tentativi}: {forma} esaurito.")
                        elif "limit" in (e.message or "").lower():
                            stampa(f"{forma}: limite gratuito già usato, la salto.")
                            immagini[forma] = None
                        else:
                            stampa(f"Errore da Oracle ({e.status}): {e.message}")
                            if not UNA_VOLTA or PROVA_MANUALE:     # su GitHub: niente messaggi ogni 10 minuti
                                telegram(f"⚠️ Cerca server: errore da Oracle ({e.status}): {e.message}")
                            raise
                if id_server:
                    break
            if not id_server and UNA_VOLTA:
                stampa("Nessun posto libero per ora.")
                return
            if not id_server:
                if time.time() - ultimo_avviso > 12 * 3600:
                    telegram(f"⏳ Cerco ancora il server gratuito: {tentativi} tentativi finora. Continuo.")
                    ultimo_avviso = time.time()
                time.sleep(ATTESA + random.randint(-60, 60))

    stampa("Attendo che il server si accenda...")
    oci.wait_until(calcolo, calcolo.get_instance(id_server), "lifecycle_state", "RUNNING", max_wait_seconds=1200)
    ip = None
    for _ in range(30):
        ip = ip_pubblico(oci, calcolo, rete, compartimento, id_server)
        if ip:
            break
        time.sleep(10)
    stampa(f"Server acceso! Indirizzo: {ip}")
    if os.path.exists(CHIAVE_SSH):          # sul PC: salvo tutto per CARICA_SUL_SERVER.bat
        with open(MEMORIA_SERVER, "w", encoding="utf-8") as f:
            f.write(f"{ip}\n{CHIAVE_SSH}\nubuntu\n")
        passo = "sul PC fai doppio clic su CARICA_SUL_SERVER.bat e premi Invio (indirizzo e chiave sono già salvati)."
    else:                                   # sul telefono: istruzioni per il PC
        chiave_pc = open(PC_CHIAVE, encoding="utf-8").read().strip() if os.path.exists(PC_CHIAVE) else "deploy\\server_ssh.key"
        passo = ("sul PC fai doppio clic su CARICA_SUL_SERVER.bat e rispondi così:\n"
                 f"• Indirizzo IP: {ip}\n• Chiave: {chiave_pc}\n• Utente: premi Invio (ubuntu)\n\n"
                 "Poi sul telefono puoi chiudere Termux.")
    telegram(f"✅ Server gratuito creato e acceso!\nIndirizzo: {ip}\n\nProssimo passo: {passo}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        stampa("Ricerca interrotta.")
