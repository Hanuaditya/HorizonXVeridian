import os
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "media"}), 200


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "healthy", "service": "media"}), 200


if __name__ == "__main__":
    port = int(os.getenv("MEDIA_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
