import os
import json
import re
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import scrolledtext
import webbrowser

import paramiko

# ---------------- CONFIG ----------------
# Modifica questi valori per il tuo setup (o usa ENV vars)
HOST = os.getenv("ADSB_BACKEND_HOST", "your-mini-pc.example.com")
USER = os.getenv("ADSB_BACKEND_USER", "youruser")
KEY_PATH = os.getenv("ADSB_SSH_KEY", os.path.join(os.environ["USERPROFILE"], ".ssh", "id_rsa"))

REMOTE_CMD = os.getenv("ADSB_BACKEND_CMD", "./df_list_edit.py")
REMOTE_EDIT = f"{REMOTE_CMD} --stdin-json"

LIST_VALUES = ["mil", "gov", "pol", "flyingdocs", "civ"]

HELP = {
    "list": "Scegli dove salvare: mil/gov/pol/flyingdocs/civ.",
    "hex": "ICAO HEX (6 esadecimali), es: 33FD21. Accetta anche 0x33FD21.",
    "reg": "Registrazione, es: EI-HNH / MM62346 / 54+47.",
    "operator": "Ente/operatore (testo libero), es: Avincis, Aeronautica Militare.",
    "type": "Descrizione mezzo (testo libero), es: Airbus Helicopters H145.",
    "icao_type": "ICAO Type (codice), es: EC45, GLF6, A139, A400.",
    "cmpg": "Gruppo (auto in base alla lista).",
    "tag1": "Tag libero 1.",
    "tag2": "Tag libero 2 (es: HEMS/Elisoccorso).",
    "tag3": "Tag libero 3 (callsign), es: IAM3124 / GAF539.",
    "category": "Categoria generale (testo): EMS / Flying Doctors / Government.",
    "link": "Pagina di riferimento. Se manca schema, aggiunge https://",
    "img1": "URL diretto immagine (jpg/png).",
    "img2": "Seconda immagine.",
    "img3": "Terza immagine.",
    "img4": "Quarta immagine.",
}

FIELDS = [
    ("hex", "HEX (6 char)"),
    ("reg", "Registrazione"),
    ("operator", "Operator"),
    ("type", "Type (descrizione)"),
    ("icao_type", "ICAO Type"),
    ("cmpg", "CMPG"),
    ("tag1", "Tag 1"),
    ("tag2", "Tag 2"),
    ("tag3", "Tag 3 (callsign)"),
    ("category", "Category"),
    ("link", "Link"),
    ("img1", "ImageLink1"),
    ("img2", "ImageLink2"),
    ("img3", "ImageLink3"),
    ("img4", "ImageLink4"),
]

CMPG_DEFAULT = {
    "mil": "Mil",
    "pol": "Pol",
    "gov": "Gov",
    "flyingdocs": "",
    "civ": "Civ",
}

# ---------------- UTILS ----------------
def validate_hex(hx: str) -> bool:
    hx = (hx or "").strip().upper().replace("0X", "").replace("0x", "")
    return bool(re.fullmatch(r"[0-9A-F]{6}", hx))

def normalize_reg_for_fr24(reg: str) -> str:
    return (reg or "").strip().lower().replace("-", "")

def normalize_form(raw: dict) -> dict:
    v = dict(raw)

    hx = (v.get("hex") or "").strip()
    hx = hx.replace("0x", "").replace("0X", "").strip().upper()
    v["hex"] = hx

    lst = (v.get("list") or "mil").strip()

    if not (v.get("cmpg") or "").strip():
        v["cmpg"] = CMPG_DEFAULT.get(lst, "")

    cmpg = (v.get("cmpg") or "").strip()
    if cmpg.lower() == lst.lower():
        v["cmpg"] = CMPG_DEFAULT.get(lst, "")

    link = (v.get("link") or "").strip()
    if link and not (link.startswith("http://") or link.startswith("https://")):
        link = "https://" + link.lstrip("/")
    v["link"] = link

    for k in ["reg","operator","type","icao_type","cmpg","tag1","tag2","tag3","category","link","img1","img2","img3","img4"]:
        v[k] = (v.get(k) or "").strip()

    return v

def extract_backend_warnings(text: str):
    warns = []
    for line in (text or "").splitlines():
        if line.strip().startswith("WARNING:"):
            warns.append(line.strip())
    return warns

def extract_backend_error_line(out: str, err: str) -> str:
    for blob in [out or "", err or ""]:
        for line in blob.splitlines():
            if line.strip().startswith("ERROR:"):
                return line.strip()
    return ""

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        ttk.Label(tw, text=self.text, relief="solid", borderwidth=1, padding=6, justify="left").pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

def bind_right_click_paste(entry: ttk.Entry):
    def paste(_event=None):
        try:
            entry.event_generate("<<Paste>>")
        except tk.TclError:
            pass
        return "break"
    entry.bind("<Button-3>", paste)
    entry.bind("<Control-Button-1>", paste)

def parse_last_json_blob(out: str):
    lines = [ln for ln in (out or "").splitlines() if ln.strip() and not ln.strip().startswith("WARNING:")]
    if not lines:
        return None
    try:
        return json.loads(lines[-1].strip())
    except Exception:
        return None

def show_backend_warnings(out: str, err: str):
    bw = extract_backend_warnings(out) + extract_backend_warnings(err)
    if bw:
        messagebox.showwarning("Warning backend", "\n".join(bw))

# ---------------- SSH JSON RPC ----------------
def ssh_run_json(req: dict):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(
        HOST,
        username=USER,
        key_filename=KEY_PATH,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )

    stdin, stdout, stderr = ssh.exec_command(REMOTE_EDIT)
    payload = json.dumps(req, ensure_ascii=False)
    stdin.write(payload)
    stdin.flush()
    stdin.channel.shutdown_write()

    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    ssh.close()
    return rc, out, err

# ---------------- GUI ----------------
root = tk.Tk()
root.title("DF ADSB Lists Publisher (ADS-B List Editor)")

vars_ = {"list": tk.StringVar(value="mil")}
vars_["move_to"] = tk.StringVar(value="")

for k, _ in FIELDS:
    vars_[k] = tk.StringVar()

top = ttk.Frame(root, padding=10)
top.grid(row=0, column=0, sticky="nsew")
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
top.columnconfigure(1, weight=1)

def log(msg: str):
    logbox.configure(state="normal")
    logbox.insert("end", msg + "\n")
    logbox.see("end")
    logbox.configure(state="disabled")

def clear_form():
    vars_["list"].set("mil")
    for k, _ in FIELDS:
        vars_[k].set("")
    vars_["cmpg"].set(CMPG_DEFAULT["mil"])
    vars_["move_to"].set("")

def get_values_normalized():
    raw = {k: vars_[k].get() for k, _ in FIELDS}
    raw["list"] = vars_["list"].get()
    v = normalize_form(raw)

    vars_["hex"].set(v["hex"])
    vars_["cmpg"].set(v.get("cmpg", ""))
    vars_["link"].set(v.get("link", ""))
    return v

def on_list_change(_=None):
    lst = (vars_["list"].get() or "").strip()
    vars_["cmpg"].set(CMPG_DEFAULT.get(lst, ""))

def do_copy_hex():
    v = get_values_normalized()
    hx = (v.get("hex") or "").strip().upper()
    if not validate_hex(hx):
        messagebox.showwarning("Warning", "HEX non valido.")
        return
    root.clipboard_clear()
    root.clipboard_append(hx)
    root.update()
    messagebox.showinfo("OK", f"HEX copiato negli appunti: {hx}")

def do_test():
    try:
        req = {"action": "ping"}
        rc, out, err = ssh_run_json(req)
        if rc == 0:
            messagebox.showinfo("OK", f"Connessione SSH OK!\nBackend: {REMOTE_CMD}")
        else:
            messagebox.showerror("Errore", (err or out or f"RC={rc}").strip())
    except Exception as e:
        messagebox.showerror("Errore", str(e))

def do_autofill():
    v = get_values_normalized()
    if not validate_hex(v["hex"]):
        messagebox.showerror("Errore", "HEX non valido (serve 6 esadecimali, es: 33FD21).")
        return

    req = {"action": "autofill", "json": True, **v}
    log(">>> autofill " + v["list"] + " " + v["hex"])

    try:
        rc, out, err = ssh_run_json(req)

        if out.strip():
            log(out.rstrip())
        if err.strip():
            log("STDERR:\n" + err.rstrip())

        show_backend_warnings(out, err)

        if rc != 0:
            messagebox.showwarning("Skip", "Autofill disabilitato nel backend pulito (privacy).")
            return

        data = parse_last_json_blob(out)
        if not data:
            messagebox.showwarning("Skip", "Autofill disabilitato.")
            return

        fields = ["reg", "tag3"]  # Solo base, no img per privacy
        updated = 0
        v = get_values_normalized()
        for field in fields:
            current = v.get(field, "").strip()
            if not current:
                new_val = data.get(field, "").strip()
                if new_val:
                    vars_[field].set(new_val)
                    updated += 1

        messagebox.showinfo("OK", f"Autofill: {updated} campi base compilati.")

    except Exception as e:
        messagebox.showerror("Errore", str(e))

def fill_gui_from_record(rec: dict):
    for k, _ in FIELDS:
        if k in rec:
            vars_[k].set((rec.get(k) or "").strip())

    v = get_values_normalized()
    vars_["hex"].set(v["hex"])
    vars_["cmpg"].set(v.get("cmpg", ""))
    vars_["link"].set(v.get("link", ""))

def do_where_hex():
    v = get_values_normalized()
    hx = (v.get("hex") or "").strip().upper()
    if not validate_hex(hx):
        messagebox.showerror("Errore", "HEX non valido.")
        return

    req = {"action": "where", "hex": hx}
    log(">>> where " + hx)

    try:
        rc, out, err = ssh_run_json(req)

        if out.strip():
            log(out.rstrip())
        if err.strip():
            log("STDERR:\n" + err.rstrip())

        show_backend_warnings(out, err)

        if rc != 0:
            messagebox.showerror("Errore", f"Where fallito (RC={rc}).")
            return

        data = parse_last_json_blob(out)
        if not data:
            messagebox.showinfo("Dove sta HEX", "HEX non presente in nessuna lista.")
            return

        locs = data.get("locations", [])
        if not locs:
            messagebox.showinfo("Dove sta HEX", "HEX non presente.")
            return

        wanted = (vars_["list"].get() or "").strip().lower()
        rec = next((x["record"] for x in locs if x.get("list", "").lower() == wanted), locs[0]["record"] if locs else {})

        fill_gui_from_record(rec)

        msg = "Trovato in:\n" + "\n".join([f"- {x.get('list')} ({x.get('file')})" for x in locs])
        messagebox.showinfo("Dove sta HEX", msg + "\n\nGUI compilata!")

    except Exception as e:
        messagebox.showerror("Errore", str(e))

def format_diff_preview(diff_json: dict) -> str:
    hx = diff_json.get("hex", "")
    tgt = diff_json.get("target_list", "")
    changes = diff_json.get("changes", [])
    moves = diff_json.get("will_move_from", [])

    parts = [f"HEX: {hx}", f"Target: {tgt}"]

    if moves:
        parts.append("")
        parts.append("Spostamento da:")
        for m in moves:
            lst = m.get("list", "")
            fil = m.get("file", "")
            parts.append(f"- {lst} ({fil})")

    parts.append("")
    if not changes:
        parts.append("Nessuna modifica (identico).")
        return "\n".join(parts)

    parts.append("Modifiche:")
    for c in changes:
        field = c.get("field", "")
        old = c.get("old", "")
        new = c.get("new", "")
        parts.append(f"- {field}: '{old}' -> '{new}'")

    return "\n".join(parts)

def do_publish():
    v = get_values_normalized()
    if not validate_hex(v["hex"]):
        messagebox.showerror("Errore", "HEX non valido (6 esadecimali, es: 33FD21).")
        return

    clean_v = {k: val for k, val in v.items() if (val or "").strip()}
    req_diff = {"action": "diff", **clean_v}
    log(">>> diff " + clean_v.get("list", "") + " " + clean_v.get("hex", ""))

    try:
        rc, out, err = ssh_run_json(req_diff)

        if out.strip():
            log(out.rstrip())
        if err.strip():
            log("STDERR:\n" + err.rstrip())

        show_backend_warnings(out, err)

        if rc != 0:
            messagebox.showerror("Errore", f"Diff fallito (RC={rc}).")
            return

        dj = parse_last_json_blob(out)
        if not dj:
            messagebox.showerror("Errore", "Backend non ha restituito JSON valido (diff).")
            return

        log("JSON diff ricevuto:")
        log(json.dumps(dj, indent=2, ensure_ascii=False))

        changes = dj.get("changes", [])
        if not changes:
            messagebox.showinfo("Nessuna modifica", "Identico: niente da aggiornare.")
            return

        preview = format_diff_preview(dj)
        if not messagebox.askyesno("Conferma publish", preview + "\n\nProcedere?"):
            return

        do_publish_direct(v)

    except Exception as e:
        messagebox.showerror("Errore", str(e))

def do_publish_direct(v: dict):
    clean_v = {k: val for k, val in v.items() if (val or "").strip()}
    req = {"action": "publish", "push": True, **clean_v}

    log(">>> publish " + clean_v.get("list", "") + " " + clean_v.get("hex", ""))

    try:
        rc, out, err = ssh_run_json(req)

        if out.strip():
            log(out.rstrip())
        if err.strip():
            log("STDERR:\n" + err.rstrip())

        show_backend_warnings(out, err)

        if rc == 0:
            messagebox.showinfo("OK", "Salvato e pubblicato!")
        elif rc == 2:
            msg = extract_backend_error_line(out, err) or "Già presente e identico."
            messagebox.showwarning("Nessuna modifica", msg)
        else:
            messagebox.showerror("Errore", f"Comando fallito (RC={rc}).")

    except Exception as e:
        messagebox.showerror("Errore", str(e))

def do_move_to_list():
    v = get_values_normalized()
    if not validate_hex(v["hex"]):
        messagebox.showerror("Errore", "HEX non valido.")
        return

    dest = (vars_["move_to"].get() or "").strip()
    if not dest:
        messagebox.showwarning("Warning", "Seleziona destinazione (Sposta in).")
        return

    if dest not in LIST_VALUES:
        messagebox.showwarning("Warning", "Lista destinazione non valida.")
        return

    if not messagebox.askyesno("Conferma spostamento", f"Spostare {v['hex']} in '{dest}'?"):
        return

    v2 = dict(v)
    v2["list"] = dest

    clean_v2 = {k: val for k, val in v2.items() if (val or "").strip()}
    req_diff = {"action": "diff", **clean_v2}
    log(">>> diff(move) " + dest + " " + v["hex"])

    try:
        rc, out, err = ssh_run_json(req_diff)

        if out.strip():
            log(out.rstrip())
        if err.strip():
            log("STDERR:\n" + err.rstrip())

        show_backend_warnings(out, err)

        if rc != 0:
            messagebox.showerror("Errore", f"Diff(move) fallito (RC={rc}).")
            return

        dj = parse_last_json_blob(out)
        if not dj:
            messagebox.showerror("Errore", "Backend non ha restituito JSON (diff(move)).")
            return

        log("JSON diff(move):")
        log(json.dumps(dj, indent=2, ensure_ascii=False))

        changes = dj.get("changes", [])
        if not changes:
            messagebox.showwarning("Nessuna modifica", "Identico in destinazione.")
            return

        preview = format_diff_preview(dj)
        if not messagebox.askyesno("Conferma", preview + "\n\nProcedere?"):
            return

        req = {"action": "publish", "push": True, **clean_v2}
        log(f">>> move/publish {dest} {v['hex']}")

        rc2, out2, err2 = ssh_run_json(req)

        if out2.strip():
            log(out2.rstrip())
        if err2.strip():
            log("STDERR:\n" + err2.rstrip())

        show_backend_warnings(out2, err2)

        if rc2 == 0:
            messagebox.showinfo("OK", f"Spostato in '{dest}'!")
        elif rc2 == 2:
            msg = extract_backend_error_line(out2, err2) or "Già corretto."
            messagebox.showwarning("Nessuna modifica", msg)
        else:
            messagebox.showerror("Errore", f"Move fallito (RC={rc2}).")

    except Exception as e:
        messagebox.showerror("Errore", str(e))

def do_delete():
    v = get_values_normalized()
    hx = (v.get("hex") or "").strip().upper()
    if not validate_hex(hx):
        messagebox.showerror("Errore", "HEX non valido!")
        return

    lst = v.get("list") or "mil"
    if not messagebox.askyesno("⚠️ ELIMINAZIONE", 
        f"ELIMINARE {hx} da '{lst}'?\n\n"
        f"• Rimuove da tutte le liste\n"
        f"• Push automatico\n\n"
        f"❌ IRREVERSIBILE!", icon="warning"):
        log(f"Delete {hx} annullato")
        return
    
    req = {"action": "delete", "hex": hx, "push": True}
    log(">>> delete " + hx)

    try:
        rc, out, err = ssh_run_json(req)

        if out.strip():
            log(out.rstrip())
        if err.strip():
            log("STDERR:\n" + err.rstrip())

        show_backend_warnings(out, err)

        if rc == 0:
            messagebox.showinfo("OK", f"{hx} eliminato da tutte le liste!")
        else:
            messagebox.showerror("Errore", f"Delete fallito (RC={rc}).")

    except Exception as e:
        messagebox.showerror("Errore", str(e))

# External sites
def do_open_planespotters():
    v = get_values_normalized()
    hx = (v.get("hex") or "").strip().upper()
    reg = (v.get("reg") or "").strip().upper()

    if reg:
        url = f"https://www.planespotters.net/aircraft/{reg}"
    else:
        if not validate_hex(hx):
            messagebox.showwarning("Warning", "Reg o HEX valido per Planespotters.")
            return
        url = f"https://www.planespotters.net/hex/{hx}"
    webbrowser.open_new_tab(url)

def do_open_adsbx():
    v = get_values_normalized()
    hx = (v.get("hex") or "").strip().upper()
    if not validate_hex(hx):
        messagebox.showwarning("Warning", "HEX valido per ADSBx.")
        return
    webbrowser.open_new_tab(f"https://globe.adsbexchange.com/?icao={hx.lower()}")

def do_open_airframes():
    webbrowser.open_new_tab("https://tbg.airframes.io/search/dashboard/search")

def do_open_fr24():
    v = get_values_normalized()
    reg = (v.get("reg") or "").strip()
    hx  = (v.get("hex") or "").strip().upper().replace("0X", "").replace("0x", "")

    if reg:
        reg_norm = normalize_reg_for_fr24(reg)
        webbrowser.open_new_tab(f"https://www.flightradar24.com/data/aircraft/{reg_norm}")
        return

    if not validate_hex(hx):
        messagebox.showwarning("Warning", "Reg o HEX per FR24.")
        return

    webbrowser.open_new_tab(f"https://www.flightradar24.com/search?query={hx}")

# UI Layout
r = 0
ttk.Label(top, text="Lista").grid(row=r, column=0, sticky="w")
cb = ttk.Combobox(top, textvariable=vars_["list"], values=LIST_VALUES, width=14, state="readonly")
cb.grid(row=r, column=1, sticky="w")
cb.bind("<<ComboboxSelected>>", on_list_change)
Tooltip(cb, HELP["list"])
r += 1

entries = {}
for k, label in FIELDS:
    ttk.Label(top, text=label).grid(row=r, column=0, sticky="w", pady=1)
    e = ttk.Entry(top, textvariable=vars_[k], width=70)
    e.grid(row=r, column=1, sticky="we", pady=1)
    entries[k] = e
    Tooltip(e, HELP.get(k, ""))
    bind_right_click_paste(e)
    r += 1

btns = ttk.Frame(top)
btns.grid(row=r, column=0, columnspan=2, sticky="we", pady=(8, 4))

ttk.Button(btns, text="Test conn.", command=do_test).grid(row=0, column=0, padx=4)
ttk.Button(btns, text="Autofill", command=do_autofill).grid(row=0, column=1, padx=4)
ttk.Button(btns, text="Copia HEX", command=do_copy_hex).grid(row=0, column=2, padx=4)
ttk.Button(btns, text="Pubblica", command=do_publish).grid(row=0, column=3, padx=4)
ttk.Button(btns, text="Pulisci", command=clear_form).grid(row=0, column=4, padx=4)

ttk.Button(btns, text="Planespotters", command=do_open_planespotters).grid(row=1, column=0, padx=4, pady=(6, 0))
ttk.Button(btns, text="ADSBx", command=do_open_adsbx).grid(row=1, column=1, padx=4, pady=(6, 0))
ttk.Button(btns, text="Airframes", command=do_open_airframes).grid(row=1, column=2, padx=4, pady=(6, 0))
ttk.Button(btns, text="FR24", command=do_open_fr24).grid(row=1, column=3, padx=4, pady=(6, 0))

ttk.Button(btns, text="Trova HEX", command=do_where_hex).grid(row=2, column=0, padx=4, pady=(8, 0))

ttk.Label(btns, text="Sposta in:").grid(row=2, column=1, padx=4, pady=(8, 0), sticky="e")
mv = ttk.Combobox(btns, textvariable=vars_["move_to"], values=LIST_VALUES, width=12, state="readonly")
mv.grid(row=2, column=2, padx=4, pady=(8, 0), sticky="w")

ttk.Button(btns, text="Sposta", command=do_move_to_list).grid(row=2, column=3, padx=4, pady=(8, 0))
ttk.Button(btns, text="Elimina", command=do_delete, style="Accent.TButton").grid(row=2, column=4, padx=(0,8), pady=(8, 0))

logbox = scrolledtext.ScrolledText(top, height=12, state="disabled")
logbox.grid(row=r+1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
top.rowconfigure(r+1, weight=1)

ttk.Label(top, text=f"SSH: {USER}@{HOST} | Backend: {REMOTE_CMD} | Key: {KEY_PATH}").grid(
    row=r+2, column=0, columnspan=2, sticky="w", pady=(6, 0)
)

vars_["cmpg"].set(CMPG_DEFAULT["mil"])

root.mainloop()
