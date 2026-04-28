from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any


class MeshcoreClient:
    def __init__(self, binary: str | None = None) -> None:
        # Auto-détection du binaire : meshcore-cli ou meshcli
        self.binary = binary or shutil.which("meshcli") or shutil.which("meshcore-cli") or "meshcli"
        self.port: str | None = None
        self.connected: bool = False
        self.last_error: str = ""
        self.last_ok_at: str = ""
        self.last_attempt_at: str = ""
        self.reconnect_attempts: int = 0
        self.last_command: str = ""
        self.last_output: str = ""
        self.last_execution_at: str = ""

    def set_port(self, port: str | None) -> None:
        self.port = port or None
        self.connected = False
        self.last_error = ""

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "port": self.port,
            "last_error": self.last_error,
            "last_ok_at": self.last_ok_at,
            "last_attempt_at": self.last_attempt_at,
            "reconnect_attempts": self.reconnect_attempts,
            "last_command": self.last_command,
            "last_output": self.last_output,
            "last_execution_at": self.last_execution_at,
        }

    def mark_disconnected(self, message: str = "USB deconnecte") -> None:
        self.connected = False
        self.last_error = message

    def _prefix(self) -> str:
        if self.port:
            return f"{self.binary} -s {shlex.quote(self.port)}"
        env_port = os.getenv("MESHCORE_PORT")
        if env_port:
            return f"{self.binary} -s {shlex.quote(env_port)}"
        return self.binary

    def _run_command(self, command: str, timeout: int = 10) -> subprocess.CompletedProcess:
        """Exécute une commande meshcore-cli et retourne l'objet CompletedProcess."""
        self.last_command = command
        self.last_execution_at = datetime.now(timezone.utc).isoformat()
        completed = subprocess.run(
            shlex.split(command),
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,  # Fusionne stderr dans stdout pour faciliter le parsing
            text=True,
            timeout=timeout,
            check=False,  # On gère le code de retour manuellement
        )
        self.last_output = completed.stdout
        return completed

    def _parse_json_output(self, completed: subprocess.CompletedProcess) -> Any:
        """Tente de parser la sortie d'une commande en JSON, gérant les logs parasites."""
        output = completed.stdout.strip()
        if not output:
            raise json.JSONDecodeError("Empty output from command", "", 0)

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            extracted = self._extract_json_from_output(output)
            if extracted is None:
                raise json.JSONDecodeError(f"No valid JSON found in output: {output}", output, 0)
            return extracted

    def _parse_text_output(self, completed: subprocess.CompletedProcess) -> str:
        """Retourne la sortie texte d'une commande."""
        return completed.stdout.strip()

    def _run_json(self, command: str, timeout: int = 10) -> Any:
        completed = self._run_command(command, timeout)
        return self._parse_json_output(completed)

    def _run_text(self, command: str, timeout: int = 10) -> str:
        completed = self._run_command(command, timeout)
        return self._parse_text_output(completed)

    def ensure_connection(self, preferred_port: str | None = None) -> bool:
        """Auto-reconnect to preferred USB port, then fallback to detected ports."""
        if preferred_port and preferred_port != self.port:
            self.set_port(preferred_port)
        if not self.port and preferred_port:
            self.port = preferred_port

        # Pas de verification agressive si deja connecte sur le bon port.
        if self.connected and self.port:
            if preferred_port is None or preferred_port == self.port:
                return True

        now = datetime.now(timezone.utc).isoformat()
        self.last_attempt_at = now
        self.reconnect_attempts += 1

        candidate_ports: list[str] = []
        if self.port:
            candidate_ports.append(self.port)
        for p in self.list_devices():
            if p not in candidate_ports:
                candidate_ports.append(p)

        if not candidate_ports:
            self.connected = False
            self.last_error = "Aucun port USB meshcore detecte"
            return False

        for candidate in candidate_ports:
            self.port = candidate
            if self.test_connection():
                self.connected = True
                self.last_error = ""
                self.last_ok_at = datetime.now(timezone.utc).isoformat()
                return True

        self.connected = False
        if not self.last_error:
            self.last_error = "Impossible de se reconnecter au meshcore USB"
        return False

    def discover_nodes(self) -> list[dict[str, str]]:
        prefix = self._prefix()
        # Commande valide fournie: meshcli -s /dev/ttyACM0 lc
        for cmd in (f"{prefix} lc", f"{prefix} contacts"):
            try:
                completed = self._run_command(cmd, timeout=15)
                if completed.returncode == 0:  # La commande doit réussir
                    output = self._parse_text_output(completed)
                    nodes = self._parse_contacts_text(output)
                    if nodes:
                        self.connected = True
                        self.last_error = ""
                        self.last_ok_at = datetime.now(timezone.utc).isoformat()
                        return nodes
            except Exception as e:
                self.last_error = str(e)  # Stocke la dernière erreur pour le statut
                continue  # Essaie la commande suivante
        return []

    def read_telemetry(
        self,
        mesh_id: str,
        node_type: str = "CLI",
        repeater_login_node: str | None = None,
        repeater_password: str | None = None,
    ) -> dict[str, float | None]:
        prefix = self._prefix()
        ids = self._candidate_node_ids(mesh_id)
        node_kind = (node_type or "CLI").upper()

        parsed = {
            "temperature_external_c": None,
            "temperature_internal_c": None,
            "battery_v": None,
            "battery_pct": None,
            "signal_rssi": None,
        }

        # 1. Tentatives de Telemetrie (RT)
        rt_attempts: list[str] = []
        if node_kind == "REP":
            login_node = (repeater_login_node or "").strip()
            password = (repeater_password or "").strip()
            if login_node and password:
                q_login = shlex.quote(login_node)
                q_pwd = shlex.quote(password)
                rt_attempts.extend([f"{prefix} login {q_login} {q_pwd} rt {nid}" for nid in ids])

        rt_attempts.extend([f"{prefix} rt {nid}" for nid in ids])
        rt_attempts.extend([f"{prefix} -j rt {nid}" for nid in ids])
        rt_attempts.extend([f"{prefix} req_telemetry {nid}" for nid in ids])
        rt_attempts.extend([f"{prefix} -j req_telemetry {nid}" for nid in ids])

        for cmd in rt_attempts:
            try:
                completed = self._run_command(cmd)
                if completed.returncode == 0:  # La commande doit réussir pour la télémétrie
                    payload = self._parse_json_output(completed)
                    data = self._parse_telemetry(payload)
                    if any(v is not None for v in data.values()):
                        parsed.update({k: v for k, v in data.items() if v is not None})
                        self.connected = True; self.last_error = ""; self.last_ok_at = datetime.now(timezone.utc).isoformat()
                        break  # Arrête après la première commande RT réussie
            except Exception as e:
                self.last_error = str(e)
                continue  # Essaie la commande RT suivante

        # 2. Tentatives de Signal (RS) si le RSSI est manquant
        if parsed["signal_rssi"] is None:
            rs_attempts: list[str] = []
            if node_kind == "REP" and repeater_login_node and repeater_password:
                q_login = shlex.quote(repeater_login_node.strip())
                q_pwd = shlex.quote(repeater_password.strip())
                rs_attempts.extend([f"{prefix} login {q_login} {q_pwd} rs {nid}" for nid in ids])
            
            rs_attempts.extend([f"{prefix} rs {nid}" for nid in ids])
            rs_attempts.extend([f"{prefix} -j rs {nid}" for nid in ids])

            for cmd in rs_attempts:
                try:
                    completed = self._run_command(cmd)
                    if completed.returncode == 0:  # La commande doit réussir pour le signal
                        # rs peut renvoyer du JSON ou du texte simple
                        try:
                            payload = self._parse_json_output(completed)
                        except json.JSONDecodeError:
                            payload = self._parse_text_output(completed)

                        sig_data = self._parse_telemetry(payload)
                        if sig_data["signal_rssi"] is not None:
                            parsed["signal_rssi"] = sig_data["signal_rssi"]
                            self.connected = True; self.last_error = ""; self.last_ok_at = datetime.now(timezone.utc).isoformat()
                            break  # Arrête après la première commande RS réussie
                except Exception as e:
                    self.last_error = str(e)
                    continue  # Essaie la commande RS suivante
        return parsed

    def list_devices(self) -> list[str]:
        """List available BLE/serial devices via meshcore-cli -l."""
        attempts = [
            f"{self.binary} -l",
            f"{self.binary} -l -T 3",
        ]
        for cmd in attempts:
            try:
                completed = self._run_command(cmd, timeout=10)
                if completed.returncode == 0:  # La commande doit réussir
                    return self._parse_devices_output(self._parse_text_output(completed))
            except Exception as e:
                self.last_error = str(e)
                continue
        return []

    def test_connection(self) -> bool:
        """Try light commands to validate selected USB link."""
        prefix = self._prefix()
        attempts = [
            # Commandes reelles connues comme stables sur ton setup.
            f"{prefix} lc",
            f"{prefix} contacts",
            # Fallback JSON eventuel selon version firmware/CLI.
            f"{prefix} -j infos",
        ]
        for cmd in attempts:
            try:
                completed = self._run_command(cmd, timeout=5)
                if completed.returncode == 0:  # La commande doit réussir
                    if " -j " in cmd:
                        result = self._parse_json_output(completed)
                        if result:  # Si on a du JSON valide, c'est un succès
                            self.connected = True
                            self.last_error = ""
                            self.last_ok_at = datetime.now(timezone.utc).isoformat()
                            return True
                    else:
                        output = self._parse_text_output(completed)
                        # Pour 'lc' ou 'contacts', on s'attend à une sortie non vide et structurée
                        if " " in output and len(output.splitlines()) > 1:
                            self.connected = True
                            self.last_error = ""
                            self.last_ok_at = datetime.now(timezone.utc).isoformat()
                            return True
            except Exception as e:
                self.last_error = str(e)  # Stocke la dernière erreur rencontrée
                continue  # Essaie la commande suivante
        self.connected = False
        if not self.last_error:
            self.last_error = "Echec test connexion USB meshcore"
        return False

    def _parse_devices_output(self, output: str) -> list[str]:
        devices: list[str] = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Typical serial Linux names.
            if "/dev/ttyUSB" in stripped or "/dev/ttyACM" in stripped or "/dev/serial/" in stripped:
                parts = stripped.split()
                for part in parts:
                    if part.startswith("/dev/"):
                        devices.append(part)
                        break
        # De-duplicate while preserving order.
        seen = set()
        unique = []
        for d in devices:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    def _parse_telemetry(self, payload: Any) -> dict[str, float | None]:
        # Cas où payload est déjà un nombre (issu d'une commande rs propre)
        if isinstance(payload, (int, float)):
            return {
                "temperature_external_c": None,
                "temperature_internal_c": None,
                "battery_v": None,
                "battery_pct": None,
                "signal_rssi": int(payload),
            }

        # Support du texte brut (ex: logs + JSON ou "RSSI: -85")
        if isinstance(payload, str):
            # On tente d'extraire le JSON si la CLI a bavardé (comme dans ton exemple)
            extracted = self._extract_json_from_output(payload)
            if extracted is not None:
                return self._parse_telemetry(extracted)

            # Sinon on cherche un pattern spécifique pour ne pas prendre les chiffres des logs
            m = re.search(r"(?:rssi|last_rssi|signal)[:\s]*(-?\d+)", payload, re.IGNORECASE)
            if not m:
                m = re.search(r"(-?\d+)", payload)

            return {
                "temperature_external_c": None,
                "temperature_internal_c": None,
                "battery_v": None,
                "battery_pct": None,
                "signal_rssi": int(m.group(1)) if m else None,
            }

        if isinstance(payload, dict):
            lpp = payload.get("lpp")
            if isinstance(lpp, list):
                from_lpp = self._parse_lpp(lpp)
                if any(v is not None for v in from_lpp.values()):
                    return from_lpp

        # Extrait des valeurs meme dans des payloads imbriques.
        candidates = self._flatten_values(payload) if isinstance(payload, (dict, list)) else {}

        temperature = (
            candidates.get("temperature_c")
            or candidates.get("temperature")
            or candidates.get("temp")
            or candidates.get("sensor_temperature")
            or candidates.get("temperaturec")
            or candidates.get("air_temperature")
        )
        battery_v = (
            candidates.get("battery_v")
            or candidates.get("battery_voltage")
            or candidates.get("battery")
            or candidates.get("voltage")
            or candidates.get("batt_v")
        )
        battery_pct = (
            candidates.get("battery_pct")
            or candidates.get("battery_percent")
            or candidates.get("battery_percentage")
            or candidates.get("batt_pct")
        )
        signal_rssi = (
            candidates.get("last_rssi")
            or candidates.get("rssi")
            or candidates.get("signal")
            or candidates.get("last_snr")
            or candidates.get("snr")
        )

        try:
            temperature = float(temperature) if temperature is not None else None
        except (TypeError, ValueError):
            temperature = None
        try:
            battery_v = float(battery_v) if battery_v is not None else None
        except (TypeError, ValueError):
            battery_v = None
        try:
            battery_pct = float(battery_pct) if battery_pct is not None else None
        except (TypeError, ValueError):
            battery_pct = None
        try:
            signal_rssi = int(float(signal_rssi)) if signal_rssi is not None else None
        except (TypeError, ValueError):
            signal_rssi = None

        return {
            "temperature_external_c": temperature,
            "temperature_internal_c": None,
            "battery_v": battery_v,
            "battery_pct": battery_pct,
            "signal_rssi": signal_rssi,
        }

    def _parse_lpp(self, lpp: list[Any]) -> dict[str, float | None]:
        temperatures: list[float] = []
        result = {
            "temperature_external_c": None,
            "temperature_internal_c": None,
            "battery_v": None,
            "battery_pct": None,
            "signal_rssi": None,
        }
        for item in lpp:
            if not isinstance(item, dict):
                continue
            typ = str(item.get("type", "")).strip().lower()
            value = item.get("value")
            try:
                num_value = float(value)
            except (TypeError, ValueError):
                continue
            if typ == "temperature":
                temperatures.append(num_value)
            elif typ == "voltage":
                result["battery_v"] = num_value
        if temperatures:
            # Convention demandee:
            # 1ere temperature = capteur exterieur, 2eme = boitier.
            result["temperature_external_c"] = temperatures[0]
            if len(temperatures) > 1:
                result["temperature_internal_c"] = temperatures[1]
        # Estimation du pourcentage batterie Li-ion 1S.
        if result["battery_v"] is not None:
            v = result["battery_v"]
            pct = (v - 3.2) / (4.2 - 3.2) * 100.0
            result["battery_pct"] = max(0.0, min(100.0, round(pct, 1)))
        return result

    def _candidate_node_ids(self, mesh_id: str) -> list[str]:
        raw = str(mesh_id).strip()
        variants = [raw, raw.lower(), raw.upper()]
        if raw.upper().startswith("0X"):
            variants.append(raw[2:])
        else:
            variants.append(f"0x{raw}")
        unique: list[str] = []
        for v in variants:
            quoted = shlex.quote(v)
            if quoted not in unique:
                unique.append(quoted)
        return unique

    def _flatten_values(self, payload: Any) -> dict[str, Any]:
        flat: dict[str, Any] = {}

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    normalized = str(key).strip().lower().replace(" ", "_")
                    if normalized not in flat and isinstance(value, (str, int, float)):
                        flat[normalized] = value
                    walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(payload)
        return flat

    def _extract_json_from_output(self, output: str) -> Any | None:
        start_obj = output.find("{")
        start_arr = output.find("[")
        starts = [i for i in (start_obj, start_arr) if i >= 0]
        if not starts:
            return None
        start = min(starts)
        end_obj = output.rfind("}")
        end_arr = output.rfind("]")
        end = max(end_obj, end_arr)
        if end < start:
            return None
        candidate = output[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    def _parse_contacts_text(self, output: str) -> list[dict[str, str]]:
        nodes: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Ignore metadata lines.
            if stripped.startswith("INFO:") or stripped.startswith(">"):
                continue

            # Formats:
            # SONDE3A      CLI   ... Flood
            # NODE_TEMP    REP   ... 0 hop
            m = re.match(r"^(\S+)\s+(CLI|REP)\b", stripped)
            if m:
                contact_name = m.group(1).strip()
                node_type = m.group(2).strip().upper()
                if contact_name and contact_name not in seen:
                    seen.add(contact_name)
                    nodes.append({"mesh_id": contact_name, "name": contact_name, "node_type": node_type})
                continue

            # Fallback: first token as contact-like name.
            first = stripped.split()[0]
            if first and first not in seen:
                seen.add(first)
                nodes.append({"mesh_id": first, "name": first, "node_type": "CLI"})
        return nodes
