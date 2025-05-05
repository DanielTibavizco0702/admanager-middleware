from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
import os

app = FastAPI()

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
                content={
                    "messages": [
                        {
                            "type": "to_user",
                            "content": "❌ El usuario no fue encontrado. Verifica el nombre o contacta a soporte."
                        }
                    ]
                }
            )

        user = data["UsersList"][0]

        return JSONResponse(
            content={
                "messages": [
                    {
                        "type": "to_user",
                        "content": (
                            f"✅ Usuario encontrado:\n\n"
                            f"👤 Nombre: {user.get('FIRST_NAME', '')}\n"
                            f"📛 Display Name: {user.get('DISPLAY_NAME', '')}"
                        )
                    }
                ]
            }
        )

    except Exception as e:
        return JSONResponse(
            content={
                "messages": [
                    {
                        "type": "to_user",
                        "content": f"⚠️ Error del servidor: {str(e)}"
                    }
                ]
            },
            status_code=500
        )


@app.get("/cambiar-password")
def cambiar_password(usuario: str, nueva_password: str):
    import json  # agregar si no está arriba

    reset_url = ADMANAGER_URL.replace("/SearchUser", "/ResetPwd")

    params = {
        "AuthToken": AUTH_TOKEN,
        "PRODUCT_NAME": "ADManager Plus",
        "domainName": DOMAIN_NAME,
        "pwd": nueva_password,
        "inputFormat": json.dumps([{"sAMAccountName": usuario}])
    }

    try:
        response = requests.post(reset_url, params=params, timeout=10)
        result = response.json()

        if result.get("status") == "Success":
            return JSONResponse(content={
                "messages": [
                    {
                        "type": "to_user",
                        "content": f"✅ Contraseña actualizada correctamente para el usuario {usuario}."
                    }
                ]
            })
        else:
            return JSONResponse(content={
                "messages": [
                    {
                        "type": "to_user",
                        "content": f"❌ Error al cambiar la contraseña: {result.get('statusMessage', 'Desconocido')}."
                    }
                ]
            })

    except Exception as e:
        return JSONResponse(content={
            "messages": [
                {
                    "type": "to_user",
                    "content": f"⚠️ Error del servidor: {str(e)}"
                }
            ]
        }, status_code=500)
