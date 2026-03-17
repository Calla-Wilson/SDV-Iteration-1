import os
from datetime import datetime, timezone
from flask import Flask, jsonify
import requests

app = Flask(__name__)

# Config: Where the Digital Twin lives (env var for Docker, fallback for local)
DITTO_URL = os.environ.get("DITTO_URL", "http://localhost:8080/api/2/things/vehicle-21")
AUTH = ('devops', 'foobar')

# =============================================================================
# OpenSOVD Endpoints
# =============================================================================

@app.route('/sovd/v1/vehicles/vehicle-21', methods=['GET'])
def get_vehicle_metadata():
    """Standard OpenSOVD Vehicle Discovery endpoint."""
    return jsonify({
        "id": "vehicle-21",
        "description": "Software-Defined Vehicle Digital Twin",
        "links": {
            "data": "/sovd/v1/vehicles/vehicle-21/data",
            "diagnostics": "/sovd/v1/vehicles/vehicle-21/diagnostics",
            "faults": "/sovd/v1/vehicles/vehicle-21/faults"
        }
    })


@app.route('/sovd/v1/vehicles/vehicle-21/data/<path:signal>', methods=['GET'])
def get_sovd_data(signal):
    """
    Standard OpenSOVD Data Access endpoint.

    Reads from Ditto features (not attributes).
    Ditto Thing structure:
      features -> OBD -> properties -> VehicleSpeed -> value
      features -> Safety -> properties -> OverheatActive -> value
      features -> Diagnostics -> properties -> SystemHealth -> value

    Usage examples:
      GET /sovd/v1/vehicles/vehicle-21/data/OBD          -> all OBD properties
      GET /sovd/v1/vehicles/vehicle-21/data/OBD/VehicleSpeed -> single signal
      GET /sovd/v1/vehicles/vehicle-21/data/Safety        -> all safety properties
    """
    try:
        response = requests.get(DITTO_URL, auth=AUTH, timeout=5)
        if response.status_code != 200:
            return jsonify({"error": "Cloud Link Offline", "status": response.status_code}), 500

        data = response.json()
        features = data.get('features', {})

        # Split signal path: e.g. "OBD/VehicleSpeed" -> ["OBD", "VehicleSpeed"]
        parts = signal.strip('/').split('/')

        # Navigate into the features structure
        if len(parts) == 1:
            # Requesting an entire feature (e.g., /data/OBD)
            feature_name = parts[0]
            feature = features.get(feature_name)
            if feature is not None:
                return jsonify({
                    "feature": feature_name,
                    "properties": feature.get("properties", {}),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }), 200
            return jsonify({"error": f"Feature '{feature_name}' not found"}), 404

        elif len(parts) == 2:
            # Requesting a specific property (e.g., /data/OBD/VehicleSpeed)
            feature_name, prop_name = parts
            feature = features.get(feature_name)
            if feature is None:
                return jsonify({"error": f"Feature '{feature_name}' not found"}), 404

            props = feature.get("properties", {})
            prop = props.get(prop_name)
            if prop is not None:
                # prop is either {"value": X} or a raw value
                value = prop.get("value", prop) if isinstance(prop, dict) else prop

                # Determine unit based on property name
                units = {
                    "VehicleSpeed": "km/h",
                    "CoolantTemperature": "celsius",
                    "EngineSpeed": "rpm",
                    "ThrottlePosition": "percent"
                }
                unit = units.get(prop_name, "unknown")

                return jsonify({
                    "name": prop_name,
                    "value": value,
                    "unit": unit,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }), 200
            return jsonify({"error": f"Property '{prop_name}' not found in '{feature_name}'"}), 404

        return jsonify({"error": "Invalid signal path"}), 400

    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot reach Ditto backend"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/sovd/v1/vehicles/vehicle-21/diagnostics', methods=['GET'])
def get_diagnostics():
    """
    OpenSOVD Diagnostics endpoint.
    Returns system health, update count, and fault history from Ditto.
    """
    try:
        response = requests.get(DITTO_URL, auth=AUTH, timeout=5)
        if response.status_code != 200:
            return jsonify({"error": "Cloud Link Offline"}), 500

        data = response.json()
        features = data.get('features', {})
        diagnostics = features.get('Diagnostics', {}).get('properties', {})
        safety = features.get('Safety', {}).get('properties', {})

        return jsonify({
            "vehicleId": "vehicle-21",
            "systemHealth": _extract(diagnostics, "SystemHealth", "UNKNOWN"),
            "dataUpdateCount": _extract(diagnostics, "DataUpdateCount", 0),
            "lastDataUpdateTime": _extract(diagnostics, "LastDataUpdateTime", None),
            "faultHistory": _extract(diagnostics, "FaultHistory", []),
            "activeFaults": {
                "overheatActive": _extract(safety, "OverheatActive", False),
                "faultCode": _extract(safety, "FaultCode", ""),
                "safetyConstraintActive": _extract(safety, "SafetyConstraintActive", False),
                "lastFaultTime": _extract(safety, "LastFaultTime", None),
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot reach Ditto backend"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/sovd/v1/vehicles/vehicle-21/faults', methods=['GET'])
def get_active_faults():
    """
    OpenSOVD Fault Inspection endpoint.
    Returns currently active faults and their severity.
    """
    try:
        response = requests.get(DITTO_URL, auth=AUTH, timeout=5)
        if response.status_code != 200:
            return jsonify({"error": "Cloud Link Offline"}), 500

        data = response.json()
        features = data.get('features', {})
        safety = features.get('Safety', {}).get('properties', {})
        obd = features.get('OBD', {}).get('properties', {})

        overheat = _extract(safety, "OverheatActive", False)
        fault_code = _extract(safety, "FaultCode", "")
        temp = _extract(obd, "CoolantTemperature", {})
        temp_value = temp.get("value") if isinstance(temp, dict) else temp

        faults = []
        if overheat:
            faults.append({
                "code": fault_code,
                "severity": "CRITICAL",
                "description": f"Engine coolant temperature ({temp_value} C) exceeds safe threshold (110 C)",
                "detectedAt": _extract(safety, "LastFaultTime", None),
                "status": "ACTIVE"
            })

        return jsonify({
            "vehicleId": "vehicle-21",
            "activeFaultCount": len(faults),
            "faults": faults,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot reach Ditto backend"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _extract(props: dict, key: str, default):
    """Safely extract a value from Ditto properties (handles {value: X} wrapper)."""
    val = props.get(key, default)
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("OpenSOVD Diagnostic Gateway - Active on Port 20002")
    print(f"Ditto backend: {DITTO_URL}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=20002)
