from fastapi import FastAPI
import requests

app = FastAPI()

ADMANAGER_URL = "https://proyecto.melabs.tech:8443/RestAPI/SearchUser"
AUTH_TOKEN = "d894b0a9-7c9a-4c89-85e6-4cc97fa695ed"
DOMAIN_NAME = "cybersex.com"

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
