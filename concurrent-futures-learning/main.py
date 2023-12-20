import requests
import timeit
import concurrent.futures
import time
import json

url = "https://api.correios.com.br/token/v1/autentica"
headers = {"accept": "application/json", "Authorization": "Basic "}

def teste_api_correios_autentica_simples():
    for i in range(15):
        print(requests.post(url=url, headers=headers).json().keys())

# timeit.timeit(lambda: teste_api_correios_autentica_simples(), number=10)

def teste_api_correios_autentica_futures():
    def teste_api_correios_autentica():
        return requests.post(url=url, headers=headers).json()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(teste_api_correios_autentica) for i in range(15)]
        for future in concurrent.futures.as_completed(futures):
            print(future.result().keys())

for function in teste_api_correios_autentica_simples, teste_api_correios_autentica_futures:
     t1 = time.perf_counter(), time.process_time()
     function()
     t2 = time.perf_counter(), time.process_time()
     print(f"{function.__name__}()")
     print(f" Real time: {t2[0] - t1[0]:.2f} seconds")
     print(f" CPU time: {t2[1] - t1[1]:.2f} seconds")
     print()