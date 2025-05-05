from fastapi import FastAPI
import requests
import os  # Importa el módulo os para leer variables de entorno

app = FastAPI()

# Leer variables de entorno definidas en Render
ADMANAGER_URL = os.getenv("ADMANAGER_URL")
AUTH_TOKEN = os.getenv("ADMANAGER_TOKEN")
DOMAIN_NAME = os.getenv("ADMANAGER_DOMAIN")


@app.get("/buscar-usuario")
def buscar_usuario(usuario: str):
    params = {
        "domainName": DOMAIN_NAME,
        "AuthToken": AUTH_TOKEN,
        "range": "1",
        "startIndex": "1",
        "filter": f"(sAMAccountName:equal:{usuario})",
        "select": "givenName,displayName"
    }

    try:
        response = requests.get(ADMANAGER_URL, params=params, timeout=10)
        data = response.json()

        if data.get("count", 0) == 0 or data.get("status") != "SUCCESS":
            return {"ok": False, "message": "Usuario no encontrado"}

        user = data["UsersList"][0]
        return {
            "ok": True,
            "first_name": user.get("FIRST_NAME", ""),
            "display_name": user.get("DISPLAY_NAME", "")
        }
    except Exception as e:
        return {"ok": False, "message": f"Error: {str(e)}"}
