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
