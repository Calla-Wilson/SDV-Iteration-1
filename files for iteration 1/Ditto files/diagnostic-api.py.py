from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

# Config: Where the Digital Twin lives
DITTO_URL = "http://localhost:8080/api/2/things/vehicle-21"
AUTH = ('devops', 'foobar')

@app.route('/sovd/v1/vehicles/vehicle-21', methods=['GET'])
def get_vehicle_metadata():
    """Standard OpenSOVD Vehicle Discovery endpoint."""
    return jsonify({
        "id": "vehicle-21",
        "description": "Software-Defined Vehicle Digital Twin",
        "links": {
            "data": "/sovd/v1/vehicles/vehicle-21/data",
            "logs": "/sovd/v1/vehicles/vehicle-21/logs"
        }
    })

@app.route('/sovd/v1/vehicles/vehicle-21/data/<path:signal>', methods=['GET'])
def get_sovd_data(signal):
    """Standard OpenSOVD Data Access endpoint."""
    try:
        response = requests.get(DITTO_URL, auth=AUTH)
        if response.status_code == 200:
            data = response.json()
            # Navigate Ditto's internal 'attributes' structure
            attributes = data.get('attributes', {})
            value = attributes.get(signal)
            
            if value is not None:
                return jsonify({
                    "name": signal,
                    "value": value,
                    "unit": "Celsius" if "Temperature" in signal else "None",
                    "timestamp": "2026-03-16T20:15:00Z" # In a real app, use live timestamp
                }), 200
            return jsonify({"error": "Signal Not Found"}), 404
        return jsonify({"error": "Cloud Link Offline"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("OpenSOVD Standard Gateway Active on Port 20002")
    app.run(host='0.0.0.0', port=20002)