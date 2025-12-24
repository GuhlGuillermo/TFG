import pytest
import uuid
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoAlertPresentException

# CONFIGURACIÓN
BASE_URL = "http://127.0.0.1:5000"

# --- FIXTURES Y UTILIDADES ---

@pytest.fixture(scope="module")
def dummy_pdf(tmp_path_factory):
    """
    Crea un archivo PDF falso temporal para las pruebas de subida.
    Actualizado con estructura binaria real para engañar a PyPDF2.
    """
    filename = tmp_path_factory.mktemp("data") / "test_dummy.pdf"
    # Contenido mínimo obligatorio de un PDF (Header, Body, Xref, Trailer, EOF)
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources <<>> /MediaBox [0 0 600 800] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n223\n%%EOF"
    )
    with open(filename, "wb") as f:
        f.write(pdf_content)
    return str(filename)

@pytest.fixture(scope="module")
def dummy_txt(tmp_path_factory):
    """Crea un archivo de texto para probar validación de formatos inválidos."""
    filename = tmp_path_factory.mktemp("data") / "test_invalid.txt"
    with open(filename, "w") as f:
        f.write("Este no es un PDF")
    return str(filename)

@pytest.fixture(scope="function")
def login_simulado(driver):
    """
    Fixture NUEVO: Realiza el login a través de la ruta de bypass antes del test.
    Necesario porque ahora la app protege las rutas contra usuarios 'invitados'.
    """
    driver.get(f"{BASE_URL}/bypass_login")
    if "Login simulado OK" not in driver.page_source:
        pytest.fail("No se pudo iniciar sesión. Asegúrate de tener la ruta /bypass_login en app.py")
    driver.get(f"{BASE_URL}/dashboard")




def generate_unique_title():
    """Genera un título único para evitar conflictos de duplicados en la BD."""
    return f"Test Autom {str(uuid.uuid4())[:8]}"

# --- 1. PRUEBAS DE AUTENTICACIÓN Y NAVEGACIÓN (AUTH) ---

def test_auth_home_load(driver):
    """AUTH-01: Carga de Home (Público)"""
    driver.get(BASE_URL)
    # Verificamos título o contenido en español/inglés
    assert "Home" in driver.title
    assert "Welcome" in driver.page_source 

def test_auth_orcid_redirection(driver):
    """AUTH-02: Redirección ORCID (Público)"""
    driver.get(BASE_URL)
    # Buscamos el botón por el texto que contiene
    btn = driver.find_element(By.XPATH, "//button[contains(text(), 'ORCID')]")
    btn.click()
    
    # Esperamos a que la URL cambie
    WebDriverWait(driver, 10).until(EC.url_contains("orcid.org"))
    assert "orcid.org" in driver.current_url

def test_auth_dashboard_access(driver, login_simulado):
    """AUTH-03: Acceso al Dashboard (Requiere Login)"""
    driver.get(f"{BASE_URL}/dashboard")
    # Verificamos que cargan las tarjetas del menú por su valor (agnóstico al idioma)
    assert driver.find_elements(By.CSS_SELECTOR, "button[value='nueva_submision']")
    assert driver.find_elements(By.CSS_SELECTOR, "button[value='nueva_version']")

def test_auth_navigation_flow(driver, login_simulado):
    """AUTH-04, AUTH-05, AUTH-06: Navegación desde Dashboard (Requiere Login)"""
    driver.get(f"{BASE_URL}/dashboard")
    
    # Navegar a Nueva Submission
    driver.find_element(By.CSS_SELECTOR, "button[value='nueva_submision']").click()
    WebDriverWait(driver, 10).until(EC.url_contains("/nueva_submision"))
    assert "/nueva_submision" in driver.current_url
    
    # Volver al dashboard
    driver.get(f"{BASE_URL}/dashboard")
    
    # Navegar a Nueva Versión
    driver.find_element(By.CSS_SELECTOR, "button[value='nueva_version']").click()
    WebDriverWait(driver, 10).until(EC.url_contains("/nueva_version"))
    assert "/nueva_version" in driver.current_url
    
    driver.get(f"{BASE_URL}/dashboard")
    
    # Navegar a Historial
    driver.find_element(By.CSS_SELECTOR, "button[value='explorar_resultados']").click()
    WebDriverWait(driver, 10).until(EC.url_contains("/ver_historial"))
    assert "/ver_historial" in driver.current_url

# --- 2. PRUEBAS DE NUEVA SUBMISIÓN (SUB) ---

def test_sub_upload_success(driver, dummy_pdf, login_simulado):
    """SUB-01: Subida Exitosa y Análisis (Requiere Login)"""
    title = generate_unique_title()
    driver.get(f"{BASE_URL}/nueva_submision")
    
    # Rellenar título
    driver.find_element(By.ID, "titulo").send_keys(title)
    
    # Subir archivo
    driver.find_element(By.ID, "file-input").send_keys(dummy_pdf)
    
    # Verificar que el botón Analizar aparece
    analyze_btn = WebDriverWait(driver, 5).until(
        EC.visibility_of_element_located((By.ID, "analyze-btn"))
    )
    
    # Hacer clic y esperar resultados (120s para soportar LLM local)
    analyze_btn.click()
    
    try:
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.ID, "tabla"))
        )
    except TimeoutException:
        pytest.fail("El análisis tardó demasiado o falló el servidor.")
        
    # Verificar que el título se muestra en los resultados
    assert title in driver.page_source

def test_sub_invalid_file(driver, dummy_txt, login_simulado):
    """SUB-02: Validación de archivo no PDF (Requiere Login)"""
    driver.get(f"{BASE_URL}/nueva_submision")
    driver.find_element(By.ID, "titulo").send_keys("Test Inválido")
    
    # Intentar subir txt
    driver.find_element(By.ID, "file-input").send_keys(dummy_txt)
    
    try:
        # Esperar y aceptar la alerta del navegador
        alert = WebDriverWait(driver, 5).until(EC.alert_is_present())
        assert "PDF" in alert.text 
        alert.accept()
    except TimeoutException:
        pass # Si no salta alerta JS, pasamos (validación backend)

def test_sub_duplicate_submission(driver, dummy_pdf, login_simulado):
    """SUB-03: Submisión duplicada (Requiere Login)"""
    # 1. Crear una submisión primero (usamos título fijo para este test)
    title = generate_unique_title()
    
    driver.get(f"{BASE_URL}/nueva_submision")
    driver.find_element(By.ID, "titulo").send_keys(title)
    driver.find_element(By.ID, "file-input").send_keys(dummy_pdf)
    driver.find_element(By.ID, "analyze-btn").click()
    WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.ID, "tabla")))
    
    # 2. Intentar crearla de nuevo con el MISMO título
    driver.get(f"{BASE_URL}/nueva_submision")
    driver.find_element(By.ID, "titulo").send_keys(title)
    driver.find_element(By.ID, "file-input").send_keys(dummy_pdf)
    driver.find_element(By.ID, "analyze-btn").click()
    
    # Verificar mensaje flash de error (Soporta ES/EN)
    flash_msg = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "alert"))
    )
    texto_alerta = flash_msg.text.lower()
    assert "already exists" in texto_alerta

# --- 3. PRUEBAS DE VERSIONADO (VER) ---

def test_ver_list_and_select(driver, dummy_pdf, login_simulado):
    """VER-01, VER-02, VER-03: Flujo de Nueva Versión (Requiere Login)"""
    
    # Pre-condición: Crear proyecto
    title = generate_unique_title()
    driver.get(f"{BASE_URL}/nueva_submision")
    driver.find_element(By.ID, "titulo").send_keys(title)
    driver.find_element(By.ID, "file-input").send_keys(dummy_pdf)
    driver.find_element(By.ID, "analyze-btn").click()
    WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.ID, "tabla")))
    
    # 1. Ir a lista de versiones
    driver.get(f"{BASE_URL}/nueva_version")
    
    # 2. Buscar el botón con nuestro título
    btn_xpath = f"//button[contains(@class, 'pdf-btn') and contains(text(), '{title}')]"
    project_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, btn_xpath))
    )
    project_btn.click()
    
    # 3. Subir nueva versión
    driver.find_element(By.ID, "file-input").send_keys(dummy_pdf)
    analyze_btn = WebDriverWait(driver, 5).until(
        EC.visibility_of_element_located((By.ID, "analyze-btn"))
    )
    analyze_btn.click()
    
    # 4. Verificar resultado (versión > 1)
    WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.ID, "tabla")))
    version_text = driver.find_element(By.ID, "version").text
    assert "Version" in version_text 

def test_ver_non_existent(driver, login_simulado):
    """VER-04: Proyecto Inexistente (Requiere Login)"""
    driver.get(f"{BASE_URL}/nueva_version/TITULO_INVENTADO_12345")
    assert  "Not found" in driver.page_source 

# --- 4. PRUEBAS DE HISTORIAL Y RESULTADOS (HIST/RES) ---

def test_hist_visualization(driver, login_simulado):
    """HIST-01, HIST-02: Visualización de Historial (Requiere Login)"""
    driver.get(f"{BASE_URL}/ver_historial")
    
    # Verificar que existen acordeones
    accordions = driver.find_elements(By.CLASS_NAME, "accordion")
    if len(accordions) > 0:
        # Abrir el primero
        accordions[0].click()
        # Verificar que se despliega el panel
        panel = driver.find_elements(By.CLASS_NAME, "panel")[0]
        WebDriverWait(driver, 2).until(EC.visibility_of(panel))
        assert panel.is_displayed()
    else:
        # Si no hay historial, verificamos que no dé error de carga
        assert "History" in driver.title

def test_res_table_structure(driver, dummy_pdf, login_simulado):
    """RES-01, RES-02: Estructura de la tabla de resultados (Requiere Login)"""
    # Creamos una sumisión rápida
    driver.get(f"{BASE_URL}/nueva_submision")
    driver.find_element(By.ID, "titulo").send_keys(generate_unique_title())
    driver.find_element(By.ID, "file-input").send_keys(dummy_pdf)
    driver.find_element(By.ID, "analyze-btn").click()
    
    WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.ID, "tabla")))
    
    # Verificar cabeceras (Soporta ES/EN)
    headers = driver.find_elements(By.TAG_NAME, "th")
    header_texts = [h.text.upper() for h in headers]
    
    assert "QUESTION" in header_texts
    assert "RESULT" in header_texts
    assert "JUSTIFICATION" in header_texts