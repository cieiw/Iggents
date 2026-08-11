"""Armazenamento local de credenciais do Zoho no Windows Credential Manager."""

import ctypes
import json
from ctypes import wintypes


TARGET_NAME = "IGGen.ZohoIMAP"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
CRED_FLAGS = 0


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.CredWriteW.argtypes = [PCREDENTIALW, wintypes.DWORD]
_advapi32.CredWriteW.restype = wintypes.BOOL
_advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIALW)]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_advapi32.CredDeleteW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]


def save(email: str, password: str, host: str) -> None:
    """Salva os dados como credencial genérica protegida pelo Windows."""
    content = json.dumps({"email": email, "password": password, "host": host}).encode("utf-16-le")
    blob = ctypes.create_string_buffer(content, len(content))
    credential = CREDENTIALW(
        Flags=CRED_FLAGS,
        Type=CRED_TYPE_GENERIC,
        TargetName=TARGET_NAME,
        Comment="Acesso IMAP do Zoho configurado pelo IGGen",
        CredentialBlobSize=len(content),
        CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte)),
        Persist=CRED_PERSIST_LOCAL_MACHINE,
        AttributeCount=0,
        Attributes=None,
        TargetAlias=None,
        UserName=email,
    )
    if not _advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def load() -> dict[str, str] | None:
    """Lê a credencial; retorna None quando ainda não foi configurada."""
    pointer = PCREDENTIALW()
    if not _advapi32.CredReadW(TARGET_NAME, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return None
        raise ctypes.WinError(error)
    try:
        credential = pointer.contents
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return json.loads(raw.decode("utf-16-le"))
    finally:
        _advapi32.CredFree(pointer)


def clear() -> None:
    """Remove a credencial salva, caso o usuário queira trocar de conta."""
    if not _advapi32.CredDeleteW(TARGET_NAME, CRED_TYPE_GENERIC, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise ctypes.WinError(error)
