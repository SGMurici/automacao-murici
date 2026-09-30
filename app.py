
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def inicio():
    return jsonify({
        "projeto": "Automacao Murici",
        "status": "online",
        "mensagem": "Aplicacao inicial criada com sucesso."
    })

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
