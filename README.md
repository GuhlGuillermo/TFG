# **PAPERS REVISION SYSTEM**
Este repositorio contiene un **sistema web** diseñado para la revisión preliminar automatizada de manuscritos científicos. La aplicación permite a los investigadores subir sus documentos PDF, los cuales son analizados por un modelo de Inteligencia Artificial (SLM) para verificar el cumplimiento de criterios metodológicos esenciales.

# Requisitos previos
Antes de comenzar, asegúrate de tener instalado:
* **Python 3.10+**
* **MongoDB**: Debe estar ejecutándose localmente o tener acceso a un clúster en la nube.
* **NVIDIA GPU (Recomendado)**: El sistema utiliza modelos cuantizados de 8-bits. Se recomienda una tarjeta gráfica con al menos 6-8 GB de VRAM para ejecutar el modelo de forma fluida.
* **Microsoft Edge**: Necesario si planeas ejecutar los tests automáticos (E2E), ya que la configuración actual utiliza `EdgeDriver`.

# Cómo usar este repositorio
## 1. Clonar el repositorio

```bash
git clone https://github.com/GuhlGuillermo/TFG.git
cd TFG
```

## 2. Crear un entorno virtual (recomendado)

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

## 3. Instalar dependencias
El proyecto requiere versiones específicas de PyTorch con soporte para CUDA.
```bash
pip install -r requirements.txt
```

## 4. Configuración del proyecto
Para que la aplicación funcione, es necesario configurar las credenciales de acceso a los servicios externos.

### 1. Preparación del archivo
Duplica la plantilla de configuración y renómbrala:
- Copia y pega `properties_ej.txt` con el nombre `properties.txt`.
  
### 2. Obtención de credenciales (properties.txt)
Edita el archivo `properties.txt` con los siguientes datos:

#### Sección `[ORCID]`
1.  Regístrate en [ORCID Developer Tools](https://orcid.org/developer-tools).
2.  Crea una **Public API client**.
3.  En **Datos de aplicación - URL de aplicación**, añade la ruta de callback de la aplicación `http://127.0.0.1:5000/callback`.
4.  En **URI de redireccionamiento**, añade `http://<tu_ipv4>:5000/callback`
5.  Copia el `Client ID`, el `Client Secret` y la `URI de redireccionamiento` al archivo `properties.txt`.
   
#### Sección `[MONGODB]`
* **mongo.url**: Para obtener correctamente esta variable hay que seguir los siguientes pasos:
    - Iniciar sesión en [MongoDB Atlas](https://www.mongodb.com/).
    - En el apartado de `Clusters` seleccionamos el cluster que queramos usar y pulsamos el botón `Connect`.
    - Seleccionamos `Drivers` y en la configuración elegimos el Driver que deseamos usar (`Python`).
    - Pulsamos el botón `Done`.
    - Copiamos el link que aparece en el punto 3 de la configuración.
    - Este link lo pegamos en el archivo `properties.txt` y lo editamos poniendo nuestro usuario y contraseña de MongoDB Atlas. 
* **mongo.database** y **mongo.collection**: Nombre que se le asigna a la base de datos y a la colección.

#### Sección `[FLASK]`
* **app.secret_key**: Genera una cadena aleatoria segura para firmar las sesiones.
    * Puedes generar una con python: `import secrets; print(secrets.token_hex(16))`

#### Sección `[LLM]`
* **model_name**: Modelo de Hugging Face a utilizar. Por defecto: `Qwen/Qwen2.5-3B-Instruct`.

## 5. Ejecución
    ```bash
    python app.py
    ```
*Nota: La primera ejecución puede tardar unos minutos mientras se descarga el modelo.*

# Testing
El proyecto incluye pruebas automatizadas (End-to-End) utilizando **Pytest** y **Selenium**.
1.  Asegúrate de tener Microsoft Edge instalado (o modifica `tests/conftest.py` para usar Chrome/Firefox).
2.  Ejecuta las pruebas:
    ```bash
    python -m pytest tests/
    ```
    *Las pruebas simulan un flujo completo de usuario, incluyendo subida de archivos y navegación, utilizando un login simulado para evitar bloqueos de ORCID.*

# Estructura del proyecto
📁 TFG  
├ 📂 templates/                 
├ 📂 tests/                      
├ app.py                        
├ model_utils.py               
├ properties.txt            
├ requirements.txt         
└ README.md
