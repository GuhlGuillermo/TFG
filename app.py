import webbrowser
import threading
import requests
import configparser
import logging
from flask import Flask, render_template, request, redirect, session, url_for, flash
from model_utils import (
    load_model, pdf_to_text, build_prompt, generate_output, get_id, insertar_bd, recalcular_version,
    comprobar_existencia_submision, crear_submision, modificar_submision, buscar_en_bd, buscar_titulos_bd,
    subir_nueva_version, buscar_versiones_bd, convertir_objectids, buscar_version_bd
)
from datetime import datetime

config = configparser.ConfigParser()
config.read("properties.txt")

app = Flask(__name__)

# Leemos la clave secreta desde el archivo properties.txt para mayor seguridad
app.secret_key = config["FLASK"]["app.secret_key"]

# Configuración del logging para resgistrar eventos para depuracion 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


# Cargar modelo
model, tokenizer, model_name = load_model()

json_total = ""
json_total_bd = ""
version = 1

# Leemos las configuraciones del Orcid desde el archivo properties.txt para aumentar la seguridad
CLIENT_ID = config["ORCID"]["orcid.client_id"]
CLIENT_SECRET = config["ORCID"]["orcid.client_secret"]
REDIRECT_URI = config["ORCID"]["orcid.redirect_uri"]
ORCID_BASE = config["ORCID"]["orcid.base_url"]



# PANTALLA INICIAL
@app.route("/")
def home():
    return render_template("home.html")


# DASHBOARD 
@app.route("/dashboard", methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        action = request.form.get("action")
        print("Acción recibida en dashboard:", action)
        if(action == "nueva_submision"):    
            return redirect(url_for("nueva_submission"))
        if(action == "nueva_version"):    
            return redirect(url_for("nueva_version"))
        if(action == "explorar_resultados"):    
            return redirect(url_for("ver_historial"))
    return render_template("menu.html")


# LOGOUT
@app.route("/logout")
def logout():
    token = session.get("orcid_token")
    
    # Revocar el token de acceso en ORCID
    if token:
        try:
            revoke_url = f"{ORCID_BASE}/oauth/revoke"
            requests.post(
                revoke_url,
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "token": token
                },
                headers={"Accept": "application/json"}
            )
        except Exception as e:
            print(f"Error al revocar token: {e}")
    
    # Limpiar los datos de la sesión localmente
    session.clear()
    
    # Renderizar página intermedia que hace logout en ORCID y redirige al home
    return render_template("intermedio.html")

# LOGIN
@app.route("/login")
def login():
    # Redirigir al usuario a la página de autorización de ORCID
    auth_url = (
        "https://orcid.org/oauth/authorize?"
        f"client_id={CLIENT_ID}&response_type=code&scope=/authenticate"
        f"&prompt=login&max_age=0&redirect_uri={REDIRECT_URI}"
    )
    return redirect(auth_url)

# CALLBACK DE ORCID
@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Error: no se recibió código de autenticación", 400
    # Intercambiar el código por un token de acceso
    token_url = f"{ORCID_BASE}/oauth/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Accept": "application/json"}

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

    print("Usuario autenticado:", session["name"], session["orcid_id"])
    # Redirigir al dashboard
    return redirect(url_for("dashboard"))

# NUEVA SUBMISIÓN
@app.route("/nueva_submision", methods=['GET', 'POST'])
def nueva_submission():
    global json_total, version
    result = None
    mensaje = ""
    if "orcid_id" not in session:
        logging.warning("Intento de acceso a nueva_submision sin estar autenticado.")
        return redirect(url_for("home")) 
    user = session["orcid_id"]
    id_submision = get_id()

    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        accion = request.form.get("action")
        print("Acción recibida:", accion)
        
        # comprobar que se ha subido un archivo PDF válido
        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            if accion == "nueva_submision":
                titulo = request.form.get("titulo")
                version = 1
                fecha = str(datetime.now()).split(".")[0]
                # Comprobar si ya existe una sumisión con ese título para el usuario en el caso de existencia => error
                if(comprobar_existencia_submision(titulo, user) == False):
                    # Procesar el PDF y generar el output
                    logger.info(f"Iniciando el procesamiento del PDF subido por {user} con título '{titulo}'")
                    text = pdf_to_text(uploaded_file)
                    messages = build_prompt(text)
                    logger.info(f"Generado correctamente el prompt. Llamando al modelo para generar la salida'")
                    result = generate_output(model, tokenizer, messages)
                    logger.info(f"Salida generada correctamente por el modelo para la sumisión '{titulo}'")
                    print("Creando nueva sumisión")
                    # Crear el JSON completo y guardarlo en la base de datos
                    json_total = crear_submision(titulo, user, id_submision)
                    json_total = modificar_submision(json_total, version, result, fecha)
                    logger.info(f"Insertando la sumisión '{titulo}' en la base de datos para el usuario {user}")
                    insertar_bd(json_total)
                    logger.info(f"Sumisión '{titulo}' insertada correctamente en la base de datos para el usuario {user}")
                    print(json_total)
                    json_total = convertir_objectids(json_total)
                    print("JSON TOTAL CONVERTIDO:", json_total)
                    # Mostrar los resultados en la pantalla
                    logger.info(f"Sumisión '{titulo}' creada correctamente para el usuario {user}, mostrando resultados")
                    return render_template("resultados.html", json_result=json_total)
                else:
                    logger.warning(f"El usuario {user} ha intentado subir una sumisión con título '{titulo}' que ya existe.")
                    flash("That submission already exists, please try uploading a new version", "error")
                print(json_total)
        else:
            mensaje = "Por favor, sube un archivo PDF válido."

    return render_template("new_submission.html", result=result, model_name=model_name, mensaje=mensaje)

# NUEVA VERSIÓN - SELECCIÓN DE TÍTULO
@app.route("/nueva_version", methods=['GET', 'POST'])
def nueva_version():
    # Buscar los títulos de las sumisiones previas del usuario para mostrarlos en un desplegable
    if "orcid_id" not in session:
        return redirect(url_for("home")) 
    user = session["orcid_id"]
    titulos = buscar_titulos_bd(user)
    print("Títulos encontrados para el usuario:", titulos)
    return render_template("new_version.html", titulos=titulos)

# NUEVA VERSIÓN - SUBIR ARCHIVO
@app.route("/nueva_version/<titulo>", methods=['GET', 'POST'])
def ver_archivo(titulo):
    if "orcid_id" not in session:
        return redirect(url_for("home")) 
    user = session["orcid_id"]
    doc = buscar_en_bd(titulo, user)
    if not doc:
        return f"Not found '{titulo}'", 404

    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        accion = request.form.get("action")
        if "orcid_id" not in session:
            return redirect(url_for("home")) 
        user = session["orcid_id"]
        print("Acción recibida:", accion)
        # comprobar que se ha subido un archivo PDF válido
        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            if accion == "nueva_version":
                # Actualizar la información de la nueva versión
                version = recalcular_version(titulo, user)
                fecha = str(datetime.now()).split(".")[0]
                # Procesar el PDF y generar el output
                text = pdf_to_text(uploaded_file)
                messages = build_prompt(text)
                result = generate_output(model, tokenizer, messages)
                # Subir la nueva versión a la base de datos
                subir_nueva_version(titulo, user, result, fecha, version)
                json_data = buscar_version_bd(titulo, user, version)
                json_data = convertir_objectids(json_data)
                print("JSON de la nueva versión:", json_data)
                # Mostrar los resultados en la pantalla
                return render_template("resultados.html", json_result=json_data)

    return render_template("index.html", model_name = model_name)

# VER HISTORIAL DE SUBMISIÓNES Y VERSIONES
@app.route("/ver_historial",methods = ['GET', 'POST'])
def ver_historial():
    # Almacenar en un diccionario los títulos y sus respectivas versiones previamente subidas
    dict = []
    if "orcid_id" not in session:
        return redirect(url_for("home")) 
    user = session["orcid_id"]
    titulos = buscar_titulos_bd(user)
    for titulo in titulos:
        versiones = buscar_versiones_bd(titulo, user)
        entrada = {"titulo": titulo, "versiones": versiones}
        dict.append(entrada)
    if request.method == "POST":
        print("POST en ver_historial")
        accion = request.form.get("action")
        print("Acción recibida:", accion)
    # Mostrar en un desplegable los títulos y versiones previas
    return render_template("mostrador_versiones_previas.html", versiones = dict)

# VER VERSIÓN ESPECÍFICA
@app.route("/ver_version", methods=["POST"])
def ver_version():
    # Consulta en la base de datos la versión específica solicitada
    titulo = request.form.get("titulo")
    numero = request.form.get("numero")
    if "orcid_id" not in session:
        return redirect(url_for("home")) 
    user = session["orcid_id"]
    json_datos = buscar_version_bd(titulo, user, int(numero))

    print("JSON DATOS DE LA VERSIÓN SOLICITADA:", json_datos)
    print("Tipo de JSON DATOS:", type(json_datos))

    # Mostrar los resultados en la pantalla
    return render_template("resultados.html", json_result=convertir_objectids(json_datos))


# RUTA SOLO PARA TESTING
# NOS SALTAMOS EL LOGIN DE ORCID PARA HACER EL TESTING YA QUE ORCID TIENE PUEDE DETECTAR AUTOMATIZACIÓN
#TODO Asegurarnos que nadie tiene acceso a esta ruta
@app.route("/bypass_login")
def bypass_login():
    session["orcid_id"] = "0000-0000-0000-0000" 
    session["name"] = "Usuario Test"
    return "Login simulado OK"

#  ABRIR NAVEGADOR AUTOMÁTICAMENTE
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    app.run(host="0.0.0.0", port=5000, debug=False)