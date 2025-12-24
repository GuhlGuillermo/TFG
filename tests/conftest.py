import pytest
from selenium import webdriver

@pytest.fixture(scope="function")
def driver():
    """
    Inicializa Microsoft Edge con tiempos de espera extendidos
    para soportar la lentitud del modelo de IA local.
    """
    options = webdriver.EdgeOptions()
    options.add_argument("--headless") 

    try:
        driver = webdriver.Edge(options=options)
    except Exception as e:
        pytest.fail(f"Error al iniciar Edge: {e}. Asegúrate de tenerlo instalado.")

    # 1. TIMEOUTS DE NAVEGACIÓN (Pestaña del navegador)
    # 600 segundos (10 min) para que cargue la página o scripts JS
    driver.set_page_load_timeout(600) 
    driver.set_script_timeout(600)

    # 2. TIMEOUT DE CONEXIÓN (Python <-> Navegador)
    driver.command_executor._client_config.timeout = 600
    
    # Espera implícita para encontrar elementos en el DOM
    driver.implicitly_wait(10)
    
    yield driver
    
    driver.quit()