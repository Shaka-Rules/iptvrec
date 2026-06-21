"""Excepciones del proyecto iptvrec."""


class IPTVRecError(Exception):
    """Error base de iptvrec."""


class ConfigError(IPTVRecError):
    """Configuración inválida o incompleta."""


class ResolveError(IPTVRecError):
    """No se pudo resolver el canal o la URL del stream."""


class AuthError(IPTVRecError):
    """Credenciales rechazadas o caducadas (Xtream / YouTube)."""


class UploadError(IPTVRecError):
    """Fallo subiendo el vídeo a YouTube."""


class IntegrityError(IPTVRecError):
    """La verificación de integridad (sha256) de la copia falló."""
