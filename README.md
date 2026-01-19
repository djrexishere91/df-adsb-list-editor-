# DF ADS-B List Editor / Editor Liste ADS-B

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/github/license/djrexishere/df-adsb-list-editor.svg)](LICENSE)

---

## 🇬🇧 English

**DF ADS-B List Editor** is a Python CLI backend and Windows GUI to manage ADS-B aircraft lists stored as CSV files in a Git repository (e.g. GitHub).  
It is designed for aviation enthusiasts who maintain curated lists of military, government, police, and civil aircraft with photos and metadata.

### ✨ Features

- Manage multiple lists (mil/gov/pol/flyingdocs/civ)
- Add or update aircraft entries (HEX, registration, operator, type, photos, tags)
- Move aircraft between lists with automatic removal from the source list
- Delete an aircraft HEX from all lists in one operation
- Preview changes (diff) before commit and push
- Query where a given HEX is present across all lists
- Open external references (Planespotters, ADS-B Exchange, Flightradar24, Airframes.io)

### 🚀 Quick Start (CLI)

```bash
git clone https://github.com/YOURUSERNAME/df-adsb-list-editor
cd df-adsb-list-editor

# Point to your CSV lists repository
export ADSB_REPO_PATH="/path/to/your/adsb-lists-repo"

# Add an aircraft to the military list
python df_list_edit.py --list mil --hex 33FD21 --reg EI-ABC --operator "Aeronautica Militare" --push

# Delete an aircraft from all lists
python df_list_edit.py --hex ABC123 --delete --push
🪟 Windows GUI
text
pip install paramiko
set ADSB_BACKEND_HOST=your-server-ip
set ADSB_BACKEND_USER=your-ssh-username
python adsb_list_editor_gui.py
The GUI connects via SSH to the backend and sends JSON requests (publish/diff/where/delete) to edit the CSV lists stored in your Git repository.

⚙️ Configuration
Environment variables:

Variable	Default	Description
ADSB_REPO_PATH	./df-adsb-lists	Path to your ADS-B lists Git repo
ADSB_BACKEND_HOST	your-mini-pc.example.com	SSH host for the backend
ADSB_BACKEND_USER	youruser	SSH username
ADSB_SSH_KEY	~/.ssh/id_rsa	SSH private key path
Supported lists (example CSV filenames):

mil → plane-alert-mil-images.csv

gov → plane-alert-gov-images.csv

pol → plane-alert-pol-images.csv

flyingdocs → plane-alert-flyingdocs.csv

civ (alias of civcur) → plane-alert-civ-curated-images.csv

🛠 CSV Format
First column must be the ICAO HEX (6 hexadecimal chars, uppercase). A typical header could be:

text
HEX,Registration,Operator,Type,ICAO_Type,CMPG,Tag1,Tag2,Tag3,Category,Link,Image1,Image2,Image3,Image4
🔗 JSON API (for bots / other tools)
bash
# Ping
echo '{"action":"ping"}' | python df_list_edit.py --stdin-json

# Where is this HEX?
echo '{"action":"where","hex":"ABC123"}' | python df_list_edit.py --stdin-json

# Preview changes (diff)
echo '{"action":"diff","list":"mil","hex":"ABC123"}' | python df_list_edit.py --stdin-json

# Publish + push
echo '{"action":"publish","list":"mil","hex":"ABC123","push":true}' | python df_list_edit.py --stdin-json
🇮🇹 Italiano
DF ADS-B List Editor è un backend CLI Python con GUI Windows per gestire liste di aeromobili ADS-B memorizzate come file CSV in un repository Git (ad es. GitHub).
È pensato per appassionati di aviazione che mantengono liste curate di aeromobili militari, governativi, polizia e civili con foto e metadati.

✨ Funzionalità
Gestione di più liste (mil/gov/pol/flyingdocs/civ)

Aggiunta/aggiornamento di aeromobili (HEX, registrazione, operatore, tipo, foto, tag)

Spostamento di un aeromobile tra liste con rimozione automatica dalla lista di origine

Eliminazione di un HEX da tutte le liste con un solo comando

Anteprima delle modifiche (diff) prima di commit e push

Ricerca di un HEX per vedere in quali liste è presente

Apertura rapida di siti esterni (Planespotters, ADS-B Exchange, Flightradar24, Airframes.io)

🚀 Avvio Rapido (CLI)
bash
git clone https://github.com/YOURUSERNAME/df-adsb-list-editor
cd df-adsb-list-editor

# Imposta il percorso del tuo repository CSV
export ADSB_REPO_PATH="/percorso/del/tuo/repo-liste-adsb"

# Aggiungi un aeromobile alla lista militare
python df_list_edit.py --list mil --hex 33FD21 --reg EI-ABC --operator "Aeronautica Militare" --push

# Elimina un aeromobile da tutte le liste
python df_list_edit.py --hex ABC123 --delete --push
🪟 GUI Windows
text
pip install paramiko
set ADSB_BACKEND_HOST=tuo-server-ip
set ADSB_BACKEND_USER=tuo-utente-ssh
python adsb_list_editor_gui.py
La GUI si collega via SSH al backend e invia richieste JSON (publish/diff/where/delete) per modificare i CSV nel tuo repository Git.

⚙️ Configurazione
Variabili d’ambiente:

Variabile	Default	Descrizione
ADSB_REPO_PATH	./df-adsb-lists	Percorso del repository liste ADS-B
ADSB_BACKEND_HOST	your-mini-pc.example.com	Host SSH per il backend
ADSB_BACKEND_USER	youruser	Username SSH
ADSB_SSH_KEY	~/.ssh/id_rsa	Percorso chiave privata SSH
Liste supportate (esempio nomi file CSV):

mil → plane-alert-mil-images.csv

gov → plane-alert-gov-images.csv

pol → plane-alert-pol-images.csv

flyingdocs → plane-alert-flyingdocs.csv

civ (alias di civcur) → plane-alert-civ-curated-images.csv

🛠 Formato CSV
La prima colonna deve contenere l’HEX ICAO (6 caratteri esadecimali maiuscoli). Un header tipico è:

text
HEX,Registration,Operator,Type,ICAO_Type,CMPG,Tag1,Tag2,Tag3,Category,Link,Image1,Image2,Image3,Image4
🔗 API JSON (per bot / altri tool)
bash
# Ping
echo '{"action":"ping"}' | python df_list_edit.py --stdin-json

# Dove si trova questo HEX?
echo '{"action":"where","hex":"ABC123"}' | python df_list_edit.py --stdin-json

# Anteprima modifiche (diff)
echo '{"action":"diff","list":"mil","hex":"ABC123"}' | python df_list_edit.py --stdin-json

# Pubblica + push
echo '{"action":"publish","list":"mil","hex":"ABC123","push":true}' | python df_list_edit.py --stdin-json
📄 License / Licenza
This project is released under the MIT License.
Questo progetto è rilasciato sotto licenza MIT.
See LICENSE for details.
