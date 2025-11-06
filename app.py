import webbrowser
import threading
import json as js
import requests
from flask import Flask, render_template, request, jsonify, redirect, session, url_for, flash
from pymongo import MongoClient
from model_utils import (
    load_model, pdf_to_text, build_prompt, generate_output,
    get_titulo, get_id, montar_JSON, connect_bd, insertar_bd, recalcular_version, comprobar_existencia_submision, crear_submision
    ,modificar_submision, buscar_en_bd, borrar_bd
)
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clave_secreta_segura"

# Cargar modelo
model, tokenizer, model_name = load_model()

json_total = ""
json_total_bd = ""
version = 1


CLIENT_ID = "APP-MB3NS9QEM2AOGKOG"
CLIENT_SECRET = "ac01f677-7aeb-40a6-acb2-5ac23b8c0db8"
REDIRECT_URI = "http://192.168.1.140:5000/callback"
ORCID_BASE = "https://orcid.org"




# ---------------------- PANTALLA INICIAL ----------------------
@app.route("/")
def home():
    return render_template("home.html")


# ---------------------- DASHBOARD ----------------------
@app.route("/dashboard", methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        action = request.form.get("action")
        if(action == "nueva_submision"):    
            return redirect(url_for("nueva_submission"))
    return render_template("prueba.html")



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



#GENERAR NUEVA SUBMISIÓN
@app.route("/nueva_submision", methods=['GET', 'POST'])
def nueva_submission():
    global json_total, version
    result = None
    mensaje = ""
    user=session.get("orcid_id", "invitado")
    id_submision = get_id()

    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        accion = request.form.get("action")
        print("Acción recibida:", accion)

        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            if accion == "nueva_submision":
                titulo = request.form.get("titulo")
                version = 1
                id_pdf = get_id()
                fecha = str(datetime.now()).split(".")[0]

                if(comprobar_existencia_submision(titulo, user) == False):
                    text = pdf_to_text(uploaded_file)
                    messages = build_prompt(text)
                    result = generate_output(model, tokenizer, messages)
                    print("Creando nueva sumisión")
                    json_total = crear_submision(titulo, user, id_submision,id_pdf)
                    json_total = modificar_submision(json_total, version, result, fecha) 
                    insertar_bd(json_total) 
                else:
                    flash("Esa submission ya existe, pruebe a subir una nueva versión", "error")
                    print("La submisión ya existe") 
                print(json_total)
            #TODO arreglar el boton de atras
            elif accion == "atras":
                return redirect(url_for("dashboard"))
        else:
            mensaje = "Por favor, sube un archivo PDF válido."

    return render_template("new_submission.html", result=result, model_name=model_name, mensaje=mensaje)


# ---------------------- ANALIZAR PDF ----------------------
@app.route("/analizar", methods=["GET", "POST"])
def analizar():
    global json_total, version
    result = None
    mensaje = ""
    user=session.get("orcid_id", "invitado")
    id_submision = get_id()

    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        accion = request.form.get("action")
        print("Acción recibida:", accion)

        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            if accion == "a":

                titulo = get_titulo(uploaded_file)
                version = recalcular_version(titulo, user)
                id_pdf = get_id()
                fecha = str(datetime.now()).split(".")[0]

                text = pdf_to_text(uploaded_file)
                messages = build_prompt(text)
                result = generate_output(model, tokenizer, messages)



                #si subo 1 primera submision de un pdf luego subo una version nueva de ese pdf,
                #  luego subo otro pdf nuevo, me crea bien la nueva submision pero si subo otra
                #  nueva version del primer pdf me borra la segunda version que subi del primer pdf
                if(comprobar_existencia_submision(titulo, user)==False):
                    print("Creando nueva sumisión")
                    json_total = crear_submision(titulo, user, id_submision,id_pdf)
                    json_total = modificar_submision(json_total, version, result, fecha) #TODO hay que añadir un usuario para que no se cargue las submisiones de otros usuarios
                    insertar_bd(json_total) 
                else:
                    json_total = buscar_en_bd(titulo, user)  
                    json_total = modificar_submision(json_total, version, result, fecha)  

                    #TODO
                    #comprobar como borrar la submision antigua
                    borrar_bd(titulo) 
                    insertar_bd(json_total)    
                print(json_total)
        else:
            mensaje = "Por favor, sube un archivo PDF válido."

    return render_template("index.html", result=result, model_name=model_name, mensaje=mensaje)


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
