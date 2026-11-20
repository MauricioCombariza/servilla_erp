"""
Crea un usuario del ERP (o le cambia la clave si ya existe) con las reglas de app/auth/claves.py sin que la contraseña ni su
hash pasen por el código ni por el historial de la terminal: la clave se pide por teclado.


Sirve para el primer administrador de una base nueva (las migraciones ya no siembran
usuarios) y para rotar la clave de un usuario cuando no se puede entrar por la pantalla
de administración.

Uso (desde backend/, con DATABASE_URL apuntando a la base):
    python -m scripts.crear_usuario admin --nombre "Administrador" --rol administrador
    python -m scripts.crear_usuario mariela --solo-clave      # solo cambia la clave
    python -m scripts.crear_usuario admin --reiniciar-mfa     # celular y códigos perdidos

--reiniciar-mfa es la salida de emergencia cuando el único administrador pierde el celular
y los códigos de respaldo: borra su segundo factor, lo desbloquea y cierra sus sesiones
(no cambia la clave). Lo configura de nuevo al entrar. Queda en eventos_seguridad.
"""

import argparse
import asyncio
import getpass
import sys

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.auth import claves, sesiones
from app.database import AsyncSessionLocal
from app.models.usuarios import Usuario, UsuarioMfaRespaldo


def _pedir_clave() -> str:
    clave = getpass.getpass("Clave nueva: ")
    if getpass.getpass("Repite la clave: ") != clave:
        sys.exit("Las claves no coinciden.")
    return clave


async def reiniciar_mfa(username: str) -> None:
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(Usuario.username == username))
        if usuario is None:
            sys.exit(f"No existe el usuario {username!r}.")
        usuario.mfa_secreto, usuario.mfa_activo, usuario.mfa_ultimo_paso = None, False, None
        sesiones.desbloquear(usuario)
        await db.execute(delete(UsuarioMfaRespaldo).where(UsuarioMfaRespaldo.usuario_id == usuario.id))
        await sesiones.cerrar_todas(db, usuario.id, "mfa_reiniciado")
        await sesiones.registrar_evento(db, "mfa_reiniciado", usuario=usuario,
                                        detalle="desde el servidor (scripts.crear_usuario)")
        await db.commit()
    print(f"Usuario {username!r}: segundo factor reiniciado; lo configura al entrar.")


async def main(args: argparse.Namespace) -> None:
    if args.reiniciar_mfa:
        await reiniciar_mfa(args.username)
        return
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(Usuario.username == args.username))
        if usuario is None and args.solo_clave:
            sys.exit(f"No existe el usuario {args.username!r}.")
        if usuario is None and not args.nombre:
            sys.exit("Para crear un usuario nuevo hace falta --nombre.")

        if usuario is None:
            usuario = Usuario(username=args.username, password_hash="",
                              nombre_completo=args.nombre, rol=args.rol, activo=True)
            accion = "creado"
        else:
            accion = "clave cambiada"
        try:
            # La pone la misma persona que la va a usar: no es temporal
            await claves.poner_clave(db, usuario, _pedir_clave(), temporal=False)
        except HTTPException as e:
            sys.exit(e.detail)
        db.add(usuario)
        await db.commit()
    print(f"Usuario {args.username!r}: {accion}.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("username")
    p.add_argument("--nombre", help="Nombre completo (obligatorio si el usuario no existe)")
    p.add_argument("--rol", default="administrador")
    p.add_argument("--solo-clave", action="store_true", help="Solo cambia la clave de un usuario existente")
    p.add_argument("--reiniciar-mfa", action="store_true",
                   help="Borra el segundo factor (celular perdido) sin cambiar la clave")
    asyncio.run(main(p.parse_args()))
