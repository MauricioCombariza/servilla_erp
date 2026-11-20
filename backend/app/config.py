from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(...)
    bases_web_url: str = ""
    # Imágenes de guía del servidor legado: https://host/guias (sin valor por defecto: vacío = deshabilitado).
    # Con imagenes_legado_ca (ruta a un .pem) se verifica el certificado TLS; sin él no se verifica.
    imagenes_legado_url: str = ""
    imagenes_legado_ca: str = ""

    jwt_secret: str = Field(...)
    jwt_algorithm: str = "HS256"
    # Token de acceso corto: se renueva con el refresh mientras la sesión siga viva
    jwt_access_expire_minutes: int = 5

    # Sesión: cierre a las 2 horas sin actividad y máximo 24 horas (decisión del
    # 2026-11-20; PR-12 dice 10 minutos, hay que ajustar la política o registrar la excepción).
    # Cada sesión vive en la tabla sesiones; cerrarla corta el acceso de inmediato.
    sesion_inactividad_minutos: int = 120
    sesion_max_horas: int = 24
    # Bloqueo de la cuenta tras N intentos fallidos seguidos (PR-12; CSI-065 control 17)
    login_max_intentos: int = 5
    login_bloqueo_minutos: int = 15

    # Cambio periódico de contraseñas del ERP (SER-MNT-PR-02 §20.3: 45 días para usuarios y
    # administradores; el banco exige entre 20 y 45). Aviso unos días antes de que venza.
    clave_vigencia_dias: int = 45
    clave_aviso_dias: int = 7
    clave_min_largo: int = 12
    clave_historial: int = 5  # no se puede repetir ninguna de las últimas N claves

    allowed_origins: str = "http://localhost:5173"
    environment: str = "development"

    imile_storage_state_path: str = "backend/.secrets/imile_session.json"

    # Sesión de iMile del flujo de ingreso de paquetes (app/services/imile_sesion.py)
    imile_user: str = ""
    imile_pass: str = ""
    imile_sesion_state_path: str = ""  # vacío → backend/.secrets/imile_sesion.json
    # Ingreso real de paquetes en iMile (Paso 2.5). Apagado hasta validarlo contra iMile real.
    imile_ingreso_activo: bool = False
    # Tope de cada ingreso en iMile: si se cuelga, se guarda como error y suelta el navegador
    # (un solo navegador atiende a todos: si no, la pantalla queda "Esperando a iMile…")
    imile_ingreso_timeout_s: float = 45
    # Total de paquetes de la tula consultado en iMile al abrirla (Paso 2.3). Solo lectura.
    imile_consulta_tula_activa: bool = False
    # Asignación de los paquetes del mensajero en iMile (Paso 3.3, "Asignar repartidor").
    # Solo corre cuando alguien presiona "Asignar en iMile".
    imile_asignacion_activa: bool = True
    # Graba UNA descarga real de tula en iMile al abrir la primera tula (imile_descarga_grabacion.py)
    imile_grabar_descarga: bool = False
    # Consulta del tracking de cada guía entregada después de cargar el informe Delivered
    # (imile_tracking.py): hora de llegada a la estación y novedades. Solo lectura.
    imile_tracking_activo: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
