from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import smtplib
from email.message import EmailMessage
import os
import json
import random
import time
import re

app = FastAPI()

ADMANAGER_URL = os.getenv("ADMANAGER_URL")
AUTH_TOKEN = os.getenv("ADMANAGER_TOKEN")
DOMAIN_NAME = os.getenv("ADMANAGER_DOMAIN")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

otp_storage = {}
usuarios_validados = {}
EXPIRACION_OTP = 300  # 5 minutos

class CambioPasswordRequest(BaseModel):
    usuario: str
    nueva_password: str

class VerificarOTP(BaseModel):
    usuario: str
    otp: str
    
class HabilitarUsuarioRequest(BaseModel):
    usuario: str
    
def enviar_otp(destinatario, otp):
    msg = EmailMessage()
    msg.set_content(f"Tu código de verificación es: {otp}")
    msg["Subject"] = "Verificación de identidad"
    msg["From"] = SMTP_USER
    msg["To"] = destinatario.strip()

    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError("SMTP_USER o SMTP_PASSWORD no están definidos")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        raise RuntimeError(f"Error enviando correo: {e}")

def validar_password(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True

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
            return JSONResponse(content={
                "messages": [{"type": "to_user", "content": "❌ Usuario no encontrado."}],
                "status": "error"
            })

        correo = data["UsersList"][0].get("EMAIL_ADDRESS", "").strip()
        if not correo:
            return JSONResponse(content={
                "messages": [{"type": "to_user", "content": "❌ El usuario no tiene correo configurado."}],
                "status": "error"
            })

        otp = str(random.randint(100000, 999999))
        otp_storage[usuario] = {"otp": otp, "timestamp": time.time()}
        enviar_otp(correo, otp)

        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": "📧 Se ha enviado un código de verificación a tu correo."}],
            "status": "otp_enviado"
        })

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error del servidor: {str(e)}"}],
            "status": "error"
        }, status_code=500)

@app.post("/verificar-otp")
def verificar_otp(data: VerificarOTP):
    entrada = otp_storage.get(data.usuario)
    if not entrada:
        return {"status": "error", "mensaje": "No se encontró un OTP para este usuario"}

    if time.time() - entrada["timestamp"] > EXPIRACION_OTP:
        otp_storage.pop(data.usuario)
        return {"status": "error", "mensaje": "OTP expirado"}

    if data.otp != entrada["otp"]:
        return {"status": "error", "mensaje": "Código incorrecto"}

    usuarios_validados[data.usuario] = True
    otp_storage.pop(data.usuario)

    return {"status": "ok", "mensaje": "✅ Verificación exitosa. Puedes continuar."}

@app.post("/habilitar-usuario")
def habilitar_usuario(data: HabilitarUsuarioRequest):
    usuario = data.usuario

    if not usuarios_validados.get(usuario):
        return JSONResponse(content={"messages": [{"type": "to_user", "content": "🔒 No verificado. Inicia sesión primero."}]}, status_code=403)

    enable_url = ADMANAGER_URL.replace("/SearchUser", "/EnableUser")
    payload = {
        "AuthToken": AUTH_TOKEN,
        "PRODUCT_NAME": "ADManager Plus",
        "domainName": DOMAIN_NAME,
        "inputFormat": json.dumps([{"sAMAccountName": usuario}])
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(enable_url, data=payload, headers=headers, timeout=10)
        result = response.json()

        if isinstance(result, list) and result[0].get("status") == "1":
            return JSONResponse(content={
                "messages": [{"type": "to_user", "content": f"✅ Usuario {usuario} habilitado correctamente."}],
                "status": "ok"
            })

        mensaje_error = result[0].get("statusMessage", "Error desconocido").lower()
        mensaje = f"❌ No se pudo habilitar el usuario {usuario}. {mensaje_error}"

        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": mensaje}],
            "status": "error"
        })

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error del servidor: {str(e)}"}],
            "status": "error"
        }, status_code=500)

@app.get("/buscar-usuario")
def buscar_usuario(usuario: str):
    if not usuarios_validados.get(usuario):
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": "🔒 No verificado. Inicia sesión primero."}]
        }, status_code=403)

    # NO usamos el campo select
    params = {
        "domainName": DOMAIN_NAME,
        "AuthToken": AUTH_TOKEN,
        "range": "1",
        "startIndex": "1",
        "filter": f"(sAMAccountName:equal:{usuario})"
    }

    try:
        response = requests.get(ADMANAGER_URL, params=params, timeout=10)
        data = response.json()

        if data.get("count", 0) == 0 or data.get("status") != "SUCCESS":
            return JSONResponse(content={
                "messages": [{"type": "to_user", "content": "❌ El usuario no fue encontrado."}]
            })

        user = data["UsersList"][0]

        # Puedes imprimir para debugging si quieres:
        # print(json.dumps(user, indent=2))

        return JSONResponse(content={
    "messages": [
        {
            "type": "to_user",
            "content": (
                f"✅ Usuario encontrado:\n\n"
                f"👤 Nombre: {user.get('FIRST_NAME', '')} {user.get('LAST_NAME', '')}\n"
                f"📛 Display Name: {user.get('DISPLAY_NAME', '')}\n"
                f"📧 Correo: {user.get('EMAIL_ADDRESS', '')}\n"
                f"📍 Ciudad: {user.get('CITY', '')}\n"
                f"🏢 Unidad Organizativa: {user.get('OU_NAME', '')}\n"
                f"📱 Teléfono: {user.get('MOBILE', '-')}\n"
                f"🆔 GUID: {user.get('OBJECT_GUID', '')}\n"
                f"🔑 UPN: {user.get('userPrincipalName', user.get('LOGON_NAME', ''))}"
            )
        }
    ]
})

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error del servidor: {str(e)}"}]
        }, status_code=500)

@app.post("/cambiar-password")
def cambiar_password(data: CambioPasswordRequest):
    usuario = data.usuario
    nueva_password = data.nueva_password

    if not usuarios_validados.get(usuario):
        return JSONResponse(content={"messages": [{"type": "to_user", "content": "🔒 No verificado. Inicia sesión primero."}]}, status_code=403)

    if not validar_password(nueva_password):
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": "❌ La contraseña insegura"}],
            "status": "error"
        })

    reset_url = ADMANAGER_URL.replace("/SearchUser", "/ResetPwd")

    payload = {
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
        response = requests.post(reset_url, data=payload, headers=headers, timeout=10)
        result = response.json()

        if isinstance(result, list) and result[0].get("status") == "1":
            return JSONResponse(content={
                "messages": [{"type": "to_user", "content": f"✅ Contraseña actualizada correctamente para el usuario {usuario}."}],
                "status": "ok"
            })

        mensaje_error = result[0].get("statusMessage", "").lower()
        if "no such user matched" in mensaje_error:
            mensaje = f"❌ Error al cambiar la contraseña para el usuario {usuario}. Verifica el nombre o contacta a soporte."
        else:
            mensaje = "❌ Error al cambiar la contraseña. Inténtalo de nuevo o contacta a soporte."

        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": mensaje}],
            "status": "error"
        })

    except Exception as e:
        return JSONResponse(content={
            "messages": [{"type": "to_user", "content": f"⚠️ Error del servidor: {str(e)}"}],
            "status": "error"
        }, status_code=500)
