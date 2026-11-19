"""
Crea un usuario del ERP (o le cambia la clave si ya existe) con las reglas de app/auth/claves.py sin que la contraseña ni su
hash pasen por el código ni por el historial de la terminal: la clave se pide por teclado.


Sirve para el primer administrador de una base nueva (las migraciones ya no siembran
usuarios) y para rotar la clave de un usuario cuando no se puede entrar por la pantalla
de administración.

Uso (desde backend/, con DATABASE_URL apuntando a la base):
    python -m scripts.crear_usuario admin --nombre "Administrador" --rol administrador
    python -m scripts.crear_usuario mariela --solo-clave      # solo cambia la clave
"""

import argparse
import asyncio
import getpass
import sys

from fastapi import HTTPException
from sqlalchemy import select

from app.auth import claves
from app.database import AsyncSessionLocal
from app.models.usuarios import Usuario


def _pedir_clave() -> str:
    clave = getpass.getpass("Clave nueva: ")
    if getpass.getpass("Repite la clave: ") != clave:
        sys.exit("Las claves no coinciden.")
    return clave


async def main(args: argparse.Namespace) -> None:
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
    asyncio.run(main(p.parse_args()))
