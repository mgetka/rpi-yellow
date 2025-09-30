from typing import List
import asyncio
import json
import uuid
import functools

import aiosqlite
import typer

from .settings import Settings


cli = typer.Typer(help="Management CLI.")
api_cli = typer.Typer(help="Manage API keys.")


def async_command(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


@api_cli.command("list")
@async_command
async def list_api_keys():
    """List all API keys."""
    settings = Settings()
    results = []
    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute(
            "SELECT id, name, key, permissions FROM api_keys"
        ) as cursor:
            async for row in cursor:
                results.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "key": row[2],
                        "permissions": json.loads(row[3]),
                    }
                )
    typer.echo(json.dumps(results))


@api_cli.command("create")
@async_command
async def create_api_key(
    name: str = typer.Argument(help="API key name."),
    permissions: List[str] = typer.Argument(help="One or more permission IDs."),
):
    """Create a new API key."""
    settings = Settings()
    key_id = str(uuid.uuid4())
    api_key = uuid.uuid4().hex
    permissions = list(set(permissions))

    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            "INSERT INTO api_keys (id, name, key, permissions) VALUES (?, ?, ?, ?)",
            (key_id, name, api_key, json.dumps(permissions)),
        )
        await db.commit()

    typer.echo(f"Created key {name}: {api_key} (id={key_id})", err=True)
    typer.echo(
        json.dumps(
            {"id": key_id, "name": name, "key": api_key, "permissions": permissions}
        )
    )


@api_cli.command("delete")
@async_command
async def delete_api_key(key_id: uuid.UUID = typer.Argument(help="API key id.")):
    """Delete an API key by ID."""
    settings = Settings()
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("DELETE FROM api_keys WHERE id = ?", (str(key_id),))
        await db.commit()

    if not cursor.rowcount:
        typer.echo(f"No API key found with ID {key_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Deleted API key {key_id}", err=True)


cli.add_typer(api_cli, name="api")

cli()
