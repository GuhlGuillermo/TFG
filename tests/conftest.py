import pytest
from selenium import webdriver

#   Esta fixture inicializa Microsoft Edge con tiempos de espera largos
#   para soportar la lentitud del modelo de IA.
@pytest.fixture(scope="function")
def driver():
    options = webdriver.EdgeOptions()
    options.add_argument("--headless") 

    try:
        driver = webdriver.Edge(options=options)
    except Exception as e:
        pytest.fail(f"Error al iniciar Edge: {e}.")

    driver.set_page_load_timeout(600) 
    driver.set_script_timeout(600)

    driver.command_executor._client_config.timeout = 600
    
    driver.implicitly_wait(10)
    
    yield driver
    
    driver.quit()