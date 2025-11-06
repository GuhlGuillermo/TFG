from transformers import AutoTokenizer, AutoModelForCausalLM
from PyPDF2 import PdfReader
import torch, json
import shortuuid
from pymongo import MongoClient


def load_model():
    model_name = "Qwen/Qwen2.5-3B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        load_in_8bit=True,  
        torch_dtype=torch.float16
    )
    return model, tokenizer, model_name


def pdf_to_text(file):

    reader = PdfReader(file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()


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
                "For each question, provide your answer in the format 'Yes', 'No', or 'N/A', based on the content of the provided article text.\n\n"
                "The output must be in JSON format, with each question as a key (e.g., 'Q1', 'Q2', ..., 'Q10') and the corresponding answer as the value.\n\n"
                "For example, the output should look like this:\n"
                "{\n"
                "    'Q1.1': 'Yes',\n"
                "    'Q1.2': 'No',\n"
                "    'Q2': 'N/A',\n"
                "    'Q3': 'Yes',\n"
                "    'Q4': 'Yes',\n"
                "    'Q5': 'No',\n"
                "    'Q6': 'Yes',\n"
                "    'Q7': 'No',\n"
                "    'Q8': 'Yes',\n"
                "    'Q9': 'No'\n"
                "    'Q10': 'Yes'\n"
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
                "Now evaluate this article text:\n\n" + texto_pdf
            )
        }
    ]


def generate_output(model, tokenizer, messages, max_tokens=700):

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

def get_titulo(file):
    reader = PdfReader(file)
    metadata = reader.metadata
    titulo = metadata.get('/Title')
    if titulo is None:
        titulo = "Sin título"
    return titulo

def get_id():
    return shortuuid.uuid()


def montar_JSON(resultado, id, titulo, fecha, version):
    json_data = {
        "ID_PDF": id,
        "titulo": titulo,
        "version": {
            "numero": version,
            "fecha": fecha,
            "preguntas_respuestas": resultado
        }
    }

    return json.dumps(json_data, indent=4)


def connect_bd():
    client = MongoClient("mongodb://localhost:27017/")
    db = client["pdf_revisados"]
    collection = db["revisiones"]
    return collection

def insertar_bd(json_doc):
    collection = connect_bd()
    collection.insert_one(json_doc)


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


def comprobar_existencia_submision(titulo, user):
    collection = connect_bd()
    filtro = {"titulo": titulo, "id_user": user}
    doc = collection.find_one(filtro)

    print("comprobar_existencia_submision:", doc)
    return doc is not None
    

def crear_submision(titulo, user, id_submision, id_pdf):
    collection = connect_bd()
    data = {
        "id_sub": id_submision,
        "id_user": user,
        "id_pdf": id_pdf,
        "titulo": titulo
    }
    #collection.insert_one(data)
    return json.dumps(data, indent=4)


#hay que añadir un usuario para que no se cargue las submisiones de otros usuarios
def modificar_submision(json_total, version, resultado, fecha):
    # Aceptar dict o JSON string
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

    return json_data  # ← devuelve dict

def buscar_en_bd(titulo, user):
    collection = connect_bd()
    doc = collection.find_one({"titulo": titulo, "id_user": user})
    if doc:
        print("buscar_en_bd: encontrado", doc)
        print("Tipo:", type(doc))
        return json.dumps(doc, indent=4, default=str)  # Convertir ObjectId a str
    else:
        return None
   
    
def borrar_bd(titulo):
    collection = connect_bd()
    result = collection.delete_many({"titulo": titulo})
    print(f"Borrados {result.deleted_count} documentos con título '{titulo}'")