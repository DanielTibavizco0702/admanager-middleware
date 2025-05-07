from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import smtplib
from email.message import EmailMessage
import random
import time
import os
import json

app = FastAPI()

# Configuración de entorno
ADMANAGER_URL = os.getenv("ADMANAGER_URL")
AUTH_TOKEN = os.getenv("ADMANAGER_TOKEN")
DOMAIN_NAME = os.getenv("ADMANAGER_DOMAIN")

SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = "SMTP.LATAM@melabs.onmicrosoft.com"
SMTP_PASSWORD = "TU_CONTRASEÑA_AQUI"  # Usa variable de entorno en producción

EXPIRACION_OTP = 180  # 3 minutos
otp_storage = {}  # Almacén temporal en memoria


# Funciones auxiliares
def generar_otp():
    return str(random.randint(100000, 999999))


def enviar_otp_correo(destinatario: str, otp: str):
    msg = EmailMessage()
    msg.set_content(f"Tu código de verificación es: {otp}")
    msg["Subject"] = "Código de verificación - Servicio de autoservicio"
    msg["From"] = SMTP_USER
    msg["To"] = destinatario

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


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
                        {"type": "to_user", "content": "❌ El usuario no fue encontrado. Verifica el nombre o contacta a soporte."}
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
            content={"messages": [{"type": "to_user", "content": f"⚠️ Error del servidor: {str(e)}"}]},
            status_code=500
        )


@app.get("/iniciar-mfa")
def iniciar_mfa(usuario: str):
    params = {
        "domainName": DOMAIN_NAME,
        "AuthToken": AUTH_TOKEN,
        "range": "1",
        "startIndex": "1",
        "filter": f"(sAMAccountName:equal:{usuario})",
        "select": "mail"
    }

    try:
        response = requests.get(ADMANAGER_URL, params=params, timeout=10)
        data = response.json()

        if data.get("count", 0) == 0 or data.get("status") != "SUCCESS":
            return JSONResponse(
                content={"messages": [{"type": "to_user", "content": "❌ Usuario no encontrado para MFA"}],
                         "status": "error", "motivo_error": "usuario_no_encontrado"},
                status_code=404
            )

        user = data["UsersList"][0]
        correo = user.get("EMAIL", "")

        if not correo:
            return JSONResponse(
                content={"messages": [{"type": "to_user", "content": "❌ El usuario no tiene correo configurado."}],
                         "status": "error", "motivo_error": "correo_no_disponible"},
                status_code=400
            )

        otp = generar_otp()
        otp_storage[usuario] = {"otp": otp, "timestamp": time.time()}
        enviar_otp_correo(correo, otp)

        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"📧 Código enviado al correo de {usuario}"}],
            "status": "ok"
        })

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error al iniciar MFA: {str(e)}"}],
            "status": "error", "motivo_error": "fallo_envio"
        }, status_code=500)


class VerificarRequest(BaseModel):
    usuario: str
    otp: str


@app.post("/verificar-mfa")
def verificar_mfa(data: VerificarRequest):
    info = otp_storage.get(data.usuario)

    if not info:
        return {"status": "error", "motivo_error": "otp_no_generado"}

    if time.time() - info["timestamp"] > EXPIRACION_OTP:
        del otp_storage[data.usuario]
        return {"status": "error", "motivo_error": "otp_expirado"}

    if data.otp == info["otp"]:
        del otp_storage[data.usuario]
        return {"status": "ok", "mensaje": "✅ MFA verificado correctamente."}
    else:
        return {"status": "error", "motivo_error": "otp_incorrecto"}


@app.get("/cambiar-password")
def cambiar_password(usuario: str, nueva_password: str):
    reset_url = ADMANAGER_URL.replace("/SearchUser", "/ResetPwd")

    data_payload = {
        "AuthToken": AUTH_TOKEN,
        "PRODUCT_NAME": "ADManager Plus",
        "domainName": DOMAIN_NAME,
        "pwd": nueva_password,
        "inputFormat": json.dumps([{"sAMAccountName": usuario}])
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(reset_url, data=data_payload, headers=headers, timeout=10)
        result = response.json()

        print("DEBUG CAMBIO PASSWORD:", result)

        if isinstance(result, list) and result[0].get("status") == "1":
            return JSONResponse(content={
                "messages": [
                    {"type": "to_user", "content": f"✅ Contraseña actualizada correctamente para el usuario {usuario}."}
                ],
                "status": "ok"
            })

        mensaje_error = result[0].get("statusMessage", "").lower()

        if "no such user matched" in mensaje_error:
            motivo = "usuario_no_encontrado"
        else:
            motivo = "cambio_password_fallido"

        return JSONResponse(content={
            "messages": [
                {"type": "to_user", "content": f"❌ Error al cambiar la contraseña: {result[0].get('statusMessage', 'Desconocido')}."}
            ],
            "status": "error",
            "motivo_error": motivo
        })

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error del servidor: {str(e)}"}],
            "status": "error",
            "motivo_error": "error_servidor"
        }, status_code=500)

