from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
import os

app = FastAPI()

# Leer variables de entorno desde Render
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
            return JSONResponse(
                content={"ok": False, "message": "Usuario no encontrado"},
                status_code=200
            )

        user = data["UsersList"][0]
        return JSONResponse(
            content={
                "ok": True,
                "data": {
                    "first_name": user.get("FIRST_NAME", ""),
                    "display_name": user.get("DISPLAY_NAME", "")
                }
            },
            status_code=200
        )

    except Exception as e:
        return JSONResponse(
            content={"ok": False, "message": f"Error: {str(e)}"},
            status_code=500
        )

