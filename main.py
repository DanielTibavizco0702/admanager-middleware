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

# Configuración
ADMANAGER_URL = os.getenv("ADMANAGER_URL")
AUTH_TOKEN = os.getenv("ADMANAGER_TOKEN")
DOMAIN_NAME = os.getenv("ADMANAGER_DOMAIN")
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = "SMTP.LATAM@melabs.onmicrosoft.com"
SMTP_PASSWORD = "TU_CONTRASEÑA_AQUI"

EXPIRACION_OTP = 180
otp_storage = {}  # OTP por usuario
solicitudes_pendientes = {}  # Contraseñas en espera por usuario


def generar_otp():
    return str(random.randint(100000, 999999))


def enviar_otp_correo(destinatario: str, otp: str):
    msg = EmailMessage()
    msg.set_content(f"Tu código de verificación es: {otp}")
    msg["Subject"] = "Código de verificación - Cambio de contraseña"
    msg["From"] = SMTP_USER
    msg["To"] = destinatario
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


@app.get("/cambiar-password")
def cambiar_password(usuario: str, nueva_password: str):
    # Buscar correo en AD para enviar OTP
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
                content={"messages": [{"type": "to_user", "content": "❌ Usuario no encontrado en ADManager"}],
                         "status": "error", "motivo_error": "usuario_no_encontrado"},
                status_code=404
            )

        user = data["UsersList"][0]
        correo = user.get("EMAIL_ADDRESS", "")
        if not correo:
            return JSONResponse(
                content={"messages": [{"type": "to_user", "content": "❌ El usuario no tiene correo configurado."}],
                         "status": "error", "motivo_error": "correo_no_disponible"},
                status_code=400
            )

        otp = generar_otp()
        otp_storage[usuario] = {"otp": otp, "timestamp": time.time()}
        solicitudes_pendientes[usuario] = {"nueva_password": nueva_password, "timestamp": time.time()}
        enviar_otp_correo(correo, otp)

        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"📧 Código enviado al correo de {usuario}. Ingresa el código para continuar."}],
            "status": "pendiente_mfa"
        })

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error al preparar el cambio: {str(e)}"}],
            "status": "error", "motivo_error": "fallo_envio"
        }, status_code=500)


class VerificarOTP(BaseModel):
    usuario: str
    otp: str


@app.post("/verificar-otp-y-aplicar-cambio")
def verificar_otp(data: VerificarOTP):
    info_otp = otp_storage.get(data.usuario)
    solicitud = solicitudes_pendientes.get(data.usuario)

    if not info_otp or not solicitud:
        return {"status": "error", "motivo_error": "datos_incompletos"}

    if time.time() - info_otp["timestamp"] > EXPIRACION_OTP:
        otp_storage.pop(data.usuario, None)
        solicitudes_pendientes.pop(data.usuario, None)
        return {"status": "error", "motivo_error": "otp_expirado"}

    if data.otp != info_otp["otp"]:
        return {"status": "error", "motivo_error": "otp_incorrecto"}

    # Ejecutar cambio
    reset_url = ADMANAGER_URL.replace("/SearchUser", "/ResetPwd")
    payload = {
        "AuthToken": AUTH_TOKEN,
        "PRODUCT_NAME": "ADManager Plus",
        "domainName": DOMAIN_NAME,
        "pwd": solicitud["nueva_password"],
        "inputFormat": json.dumps([{"sAMAccountName": data.usuario}])
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(reset_url, data=payload, headers=headers, timeout=10)
        result = response.json()
        otp_storage.pop(data.usuario, None)
        solicitudes_pendientes.pop(data.usuario, None)

        if isinstance(result, list) and result[0].get("status") == "1":
            return {"status": "ok", "mensaje": "✅ Contraseña cambiada correctamente."}
        else:
            return {"status": "error", "motivo_error": result[0].get("statusMessage", "Error desconocido")}
    except Exception as e:
        return {"status": "error", "motivo_error": str(e)}

