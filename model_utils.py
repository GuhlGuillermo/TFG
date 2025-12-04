from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from PyPDF2 import PdfReader
import torch, json
import shortuuid
import configparser
from pymongo import MongoClient
from bson import ObjectId

config = configparser.ConfigParser()
config.read("properties.txt")

# Leemos las configuraciones de la base de datos desde el archivo properties.txt para aumentar la seguridad
URL_BD = config["MONGODB"]["mongo.url"]
DATABASE_NAME = config["MONGODB"]["mongo.database"]
COLLECTION_NAME = config["MONGODB"]["mongo.collection"]

# Nombre del modelo LLM desde properties.txt
LLM_MODEL_NAME = config["LLM"]["model_name"]

# Cargar el modelo y el tokenizador
def load_model():
    model_name = LLM_MODEL_NAME
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    bnb_config = BitsAndBytesConfig(load_in_8bit=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        quantization_config=bnb_config,  
        dtype=torch.float16
    )
    return model, tokenizer, model_name

# Extraer texto del PDF
def pdf_to_text(file):
    reader = PdfReader(file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()

# Construir el prompt para la revisión científica, para ello usamos el texto extraído del PDF
def build_prompt(texto_pdf):
    return [
        {
            "role": "system",
            "content": (
                "You are a scientific reviewer specialized in experimental software engineering. "
                "Respond ONLY in valid JSON format. Do not include explanations or markdown."
            )
        },
        {
            "role": "user",
            "content": (
                "You are a scientific reviewer specialized in experimental software engineering. "
                "Your task is to evaluate a scientific article based on a 10-question checklist (Q1.1 to Q10). "
                "For each question, provide your answer and a brief justification.\n\n"
                "The output must be in JSON format, where each question is a key with an object containing:\n"
                "- 'answer': Must be exactly 'Yes', 'No', or 'N/A'\n"
                "- 'justification': A brief explanation (maximum 2 sentences) based on the article content.\n\n"
                "Example output format:\n"
                "{\n"
                "    \"Q1.1\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"The null hypothesis is explicitly stated in section 2.1 of the methodology.\"\n"
                "    },\n"
                "    \"Q1.2\": {\n"
                "        \"answer\": \"No\",\n"
                "        \"justification\": \"The document does not mention any alternative hypothesis.\"\n"
                "    },\n"
                "    \"Q2\": {\n"
                "        \"answer\": \"N/A\",\n"
                "        \"justification\": \"Sample size calculation is not applicable to this type of qualitative research.\"\n"
                "    },\n"
                "    \"Q3\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"Random selection is described in section 3.2.\"\n"
                "    },\n"
                "    \"Q4\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"Random assignment to treatment groups is clearly documented.\"\n"
                "    },\n"
                "    \"Q5\": {\n"
                "        \"answer\": \"No\",\n"
                "        \"justification\": \"Test assumptions such as normality are not discussed.\"\n"
                "    },\n"
                "    \"Q6\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"Linear models are defined and discussed in section 4.\"\n"
                "    },\n"
                "    \"Q7\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"Results are interpreted with reference to p-values and confidence intervals.\"\n"
                "    },\n"
                "    \"Q8\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"The authors do not calculate or discuss post hoc power.\"\n"
                "    },\n"
                "    \"Q9\": {\n"
                "        \"answer\": \"No\",\n"
                "        \"justification\": \"Multiple testing corrections like Bonferroni are not mentioned.\"\n"
                "    },\n"
                "    \"Q10\": {\n"
                "        \"answer\": \"Yes\",\n"
                "        \"justification\": \"Descriptive statistics including means and counts are reported in Table 1.\"\n"
                "    }\n"
                "}\n\n"
                "Checklist:\n"
                "Q1.1 Are null hypotheses explicitly defined?\n"
                "Q1.2 Are alternative hypotheses explicitly defined?\n"
                "Q2 Has the required sample size been calculated?\n"
                "Q3 Have subjects been randomly selected?\n"
                "Q4 Have subjects been randomly assigned to treatments?\n"
                "Q5 Have the test assumptions (i.e., normality and heteroskedasticity) been checked or, at least, discussed?\n"
                "Q6 Has the definition of linear models been discussed?\n"
                "Q7 Have the analysis results been interpreted by making reference to relevant statistical concepts, such as p-values, confidence intervals, and power?\n"
                "Q8 Do researchers avoid calculating and discussing post hoc power?\n"
                "Q9 Is multiple testing, e.g., Bonferroni correction, reported and accounted for?\n"
                "Q10 Are descriptive statistics, such as means and counts, reported?\n\n"
                "IMPORTANT: Respond ONLY with the JSON object. Do not add any text before or after the JSON.\n\n"
                "Now evaluate this article text:\n\n" + texto_pdf
            )
        }
    ]

# Generar la salida del modelo en formato JSON con un limite de 1500 tokens
def generate_output(model, tokenizer, messages, max_tokens=1500):
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
    generated_ids = model.generate(
        max_new_tokens=max_tokens,
        temperature=0.1, #grado de libertad en la generación
        top_p=0.8,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
        **model_inputs
    )

    output = tokenizer.decode(
        generated_ids[0][model_inputs.input_ids.shape[1]:],
        skip_special_tokens=True
    )

    try:
        data = json.loads(output)
    except:
        data = {"error": "Invalid JSON output", "raw": output}
    return data

# Generar un ID único para cada submisión
def get_id():
    return shortuuid.uuid()

# Conectar a la base de datos MongoDB
def connect_bd():
    client = MongoClient(URL_BD)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]
    return collection

# Insertar documento JSON en la base de datos
def insertar_bd(json_doc):
    collection = connect_bd()
    collection.insert_one(json_doc)

# Recalcular la versión para una nueva versión de una submisión existente
def recalcular_version(titulo, user):
    collection = connect_bd()
    docs = collection.find({"titulo": titulo, "id_user": user}, {"versiones.numero": 1, "_id": 0})
    max_version = 0
    for doc in docs:
        if "versiones" in doc:
            for v in doc["versiones"]:
                if v["numero"] > max_version:
                    max_version = v["numero"]

    return max_version + 1

# Compueba si ese usuario ya tiene una submisión con ese título
def comprobar_existencia_submision(titulo, user):
    collection = connect_bd()
    filtro = {"titulo": titulo, "id_user": user}
    doc = collection.find_one(filtro)

    print("comprobar_existencia_submision:", doc)
    return doc is not None
    
# Crear la estructura básica de una nueva submisión
def crear_submision(titulo, user, id_submision, id_pdf):
    data = {
        "id_sub": id_submision,
        "id_user": user,
        "id_pdf": id_pdf,
        "titulo": titulo
    }
    return json.dumps(data, indent=4)


# Modificar la submisión para añadir una nueva versión con los resultados
def modificar_submision(json_total, version, resultado, fecha):
    if isinstance(json_total, str):
        json_data = json.loads(json_total)
    else:
        json_data = json_total

    nueva_version = {
        "numero": version,
        "fecha": fecha,
        "preguntas_respuestas": resultado
    }

    if "versiones" not in json_data:
        json_data["versiones"] = []

    json_data["versiones"].append(nueva_version)

    return json_data  

# Subir una nueva versión de una submisión existente
def subir_nueva_version(titulo, id_user, respuestas_dict, fecha, version):
    collection = connect_bd()

    nueva_version = {
        "numero": version,
        "fecha": fecha,
        "preguntas_respuestas": respuestas_dict
    }

    result = collection.update_one(
        {"titulo": titulo, "id_user": id_user},
        {"$push": {"versiones": nueva_version}}
    )
    print("RESULT", result)

# Buscar un documento en la base de datos por título y usuario
def buscar_en_bd(titulo, user):
    collection = connect_bd()
    doc = collection.find_one({"titulo": titulo, "id_user": user})
    if doc:
        print("buscar_en_bd: encontrado", doc)
        print("Tipo:", type(doc))
        return json.dumps(doc, indent=4, default=str)  # Convertir ObjectId a str
    else:
        return None

# Buscar todos los títulos de las submisiones de un usuario
def buscar_titulos_bd(user):
    collection = connect_bd()
    titulos = collection.distinct("titulo", {"id_user": user})
    return titulos

# Buscar todas las versiones de una submisión para un usuario
def buscar_versiones_bd(titulo, user):
    collection = connect_bd()
    doc = collection.find_one({"titulo": titulo, "id_user": user}, {"versiones": 1, "_id": 0})
    if doc and "versiones" in doc:
        return doc["versiones"]
    else:
        return []

# Transforma ObjectId a str recursivamente en toda la estructura de datos
def convertir_objectids(obj):
    if isinstance(obj, dict):
        return {k: convertir_objectids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convertir_objectids(i) for i in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj
    
# Buscar una versión específica de una submisión para un usuario
def buscar_version_bd(titulo, user, version_num):
    coleccion = connect_bd()

    doc = coleccion.find_one(
        {"titulo": titulo, "id_user": user},
        {
            "id_sub": 1,
            "id_user": 1,
            "id_pdf": 1,
            "titulo": 1,
            "versiones": {"$elemMatch": {"numero": version_num}}
        }
    )

    if not doc:
        print("No se encontró el documento o la versión.")
        return None

    doc["_id"] = str(doc["_id"]) 
    return doc