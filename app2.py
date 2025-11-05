import webbrowser
import threading
import json as js
import requests
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from pymongo import MongoClient
from model_utils import (
    load_model, pdf_to_text, build_prompt, generate_output,
    get_titulo, get_id, montar_JSON, connect_bd, insertar_bd, recalcular_version
)
from datetime import datetime

app = Flask(__name__)

# Cargar modelo
model, tokenizer, model_name = load_model()

json_total = ""
version = 1

CLIENT_ID = "APP-MB3NS9QEM2AOGKOG"
CLIENT_SECRET = "ac01f677-7aeb-40a6-acb2-5ac23b8c0db8"
REDIRECT_URI = "http://192.168.1.140:5000/callback"
ORCID_BASE = "https://orcid.org"

app.secret_key = "clave_secreta_segura"



# ---------------------- PANTALLA INICIAL ----------------------
@app.route("/")
def home():
    return render_template("home.html")


# ---------------------- DASHBOARD ----------------------
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")



@app.route("/login")
def login():
    auth_url = (
        f"{ORCID_BASE}/oauth/authorize?client_id={CLIENT_ID}"
        f"&response_type=code&scope=/authenticate&redirect_uri={REDIRECT_URI}"
    )
    return redirect(auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Error: no se recibió código de autenticación", 400

    token_url = f"{ORCID_BASE}/oauth/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Accept": "application/json"}

    # Intercambiar el código por el token
    response = requests.post(token_url, data=data, headers=headers)
    print("Token response:", response.text)

    try:
        token_data = response.json()
    except ValueError:
        return f"Error: respuesta no válida de ORCID: {response.text}", 500

    # Guardar en sesión lo importante
    session["orcid_token"] = token_data.get("access_token")
    session["orcid_id"] = token_data.get("orcid")
    session["name"] = token_data.get("name", "Usuario ORCID")

    # Ya no intentamos llamar al endpoint /person
    print("Usuario autenticado:", session["name"], session["orcid_id"])

    return redirect(url_for("dashboard"))




# ---------------------- ANALIZAR PDF ----------------------
@app.route("/analizar", methods=["GET", "POST"])
def analizar():
    global json_total, version
    result = None
    mensaje = ""

    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        accion = request.form.get("action")
        print("Acción recibida:", accion)

        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            if accion == "a":
                titulo = get_titulo(uploaded_file)
                version = recalcular_version(titulo)
                id_pdf = get_id(uploaded_file)
                fecha = str(datetime.now()).split(".")[0]
                text = pdf_to_text(uploaded_file)
                messages = build_prompt(text)
                result = generate_output(model, tokenizer, messages)

                json_aux = montar_JSON(result, id_pdf, titulo, fecha, version)
                json_aux_bd = js.loads(json_aux)

                collection = connect_bd()
                insertar_bd(json_aux_bd)

                json_total += json_aux
                mensaje = f"PDF '{titulo}' analizado correctamente (versión {version})."
                print("Analizado:", json_aux)
        else:
            mensaje = "Por favor, sube un archivo PDF válido."

    return render_template("index2.html", result=result, model_name=model_name, mensaje=mensaje)


# ---------------------- API: TÍTULOS ----------------------
@app.route("/api/titulos")
def api_titulos():
    """Devuelve todos los títulos únicos almacenados"""
    collection = connect_bd()
    titulos = collection.distinct("titulo")
    return jsonify(titulos)


# ---------------------- API: VERSIONES DE UN TÍTULO ----------------------
@app.route("/api/versiones/<titulo>")
def api_versiones(titulo):
    """Devuelve las versiones del título indicado"""
    collection = connect_bd()
    docs = collection.find({"titulo": titulo}, {"_id": 0, "version.numero": 1})
    versiones = sorted([d["version"]["numero"] for d in docs])
    return jsonify(versiones)


# ---------------------- API: DETALLE DE UNA VERSIÓN ----------------------
@app.route("/api/detalle/<titulo>/<int:version>")
def api_detalle(titulo, version):
    """Devuelve las preguntas y respuestas de una versión concreta"""
    collection = connect_bd()
    doc = collection.find_one({"titulo": titulo, "version.numero": version}, {"_id": 0})
    if not doc:
        return jsonify({"error": "No encontrado"}), 404
    return jsonify(doc["version"]["preguntas_respuestas"])


# ---------------------- ABRIR NAVEGADOR ----------------------
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
