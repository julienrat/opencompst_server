# OpenCompost - Telemetrie MeshCore USB

Serveur Python pour lire la temperature et la batterie de noeuds MeshCore connectes en USB, stocker les mesures en SQLite et afficher une interface web responsive.

## Fonctionnalites

- Detection de noeuds via `meshcore-cli`
- Collecte periodique des mesures (temperature, tension batterie, pourcentage batterie)
- Stockage SQLite local
- Dashboard avec:
  - jauges par noeud
  - courbe temperature zoomable
- Administration:
  - activer/desactiver les noeuds
  - nommer les noeuds
  - regler la frequence de collecte
  - exporter une periode en CSV

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancer

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Puis ouvrir:

- `http://localhost:8000/` (dashboard)
- `http://localhost:8000/admin` (administration)

## Notes MeshCore
Le code tente plusieurs syntaxes de commande JSON (`meshcore-cli nodes --json` et `meshcore-cli --json nodes`) pour maximiser la compatibilite selon les versions de CLI.

## Commandes MeshCore CLI

L'application interagit avec vos nœuds Meshtastic via l'outil en ligne de commande `meshcli` (ou `meshcore-cli`). Voici les commandes principales utilisées et leur rôle :

- **`meshcli -s /dev/ttyACM0 rt <NODE_ID>`** :
  Cette commande est utilisée pour récupérer la télémétrie (température, batterie, etc.) d'un nœud spécifique (`NODE_ID`). `rt` est l'alias court de `req_telemetry`.

- **`meshcli -s /dev/ttyACM0 rs <NODE_ID>`** :
  Cette commande permet de lire les informations de signal (RSSI, SNR) d'un nœud spécifique (`NODE_ID`). `rs` est l'alias court de `read_signal`.

- **Commandes groupées (Bulk Telemetry)** :
  Pour optimiser la vitesse de collecte, l'application utilise une commande unique pour interroger tous les nœuds en même temps. Par exemple :
  `meshcli -s /dev/ttyACM0 rt <NODE_ID_1> rt <NODE_ID_2> ... rs <NODE_ID_1> rs <NODE_ID_2> ...`
  Cela permet de réduire le temps de communication série et d'améliorer la réactivité du système.
