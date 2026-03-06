import re
from contextlib import contextmanager

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.utils.text import slugify


_SCHEMA_RE = re.compile(r'^[a-z_][a-z0-9_]{0,62}$')


def build_schema_name(client):
    base = client.domain or client.name or f'client_{client.id}'
    normalized = slugify(base).replace('-', '_')
    if not normalized:
        normalized = f'client_{client.id}'
    return f'tenant_{normalized}'[:63]


def validate_schema_name(schema_name):
    return bool(_SCHEMA_RE.match(schema_name))


@contextmanager
def _schema_search_path(conn, schema_name):
    """
    Force search_path at connection level for the migrate command.
    This is more reliable than running SET search_path once on a cursor.
    """
    options = dict(conn.settings_dict.get('OPTIONS', {}))
    original = options.get('options', '')
    forced = f'-c search_path={schema_name},public'
    options['options'] = f'{original} {forced}'.strip() if original else forced

    conn.close()
    conn.settings_dict['OPTIONS'] = options
    try:
        yield
    finally:
        restore = dict(conn.settings_dict.get('OPTIONS', {}))
        if original:
            restore['options'] = original
        else:
            restore.pop('options', None)
        conn.close()
        conn.settings_dict['OPTIONS'] = restore


def provision_client_schema(client):
    """
    Create a PostgreSQL schema and run migrations scoped to that schema.
    Returns (ok: bool, error: str|None).
    """
    if not getattr(settings, 'CLIENT_SCHEMA_AUTO_PROVISION', False):
        return True, None

    database = getattr(settings, 'CLIENT_SCHEMA_MIGRATE_DATABASE', 'default')
    conn = connections[database]

    if conn.vendor != 'postgresql':
        return False, 'Client schema provisioning requires PostgreSQL.'

    schema_name = client.schema_name or build_schema_name(client)
    if not validate_schema_name(schema_name):
        return False, f'Invalid schema name: {schema_name}'

    try:
        with conn.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

        # Run all migrations inside the newly created schema.
        with _schema_search_path(conn, schema_name):
            call_command(
                'migrate',
                database=database,
                interactive=False,
                run_syncdb=True,
                verbosity=0,
            )

        client.schema_name = schema_name
        client.schema_provisioned = True
        client.save(update_fields=['schema_name', 'schema_provisioned'])
        return True, None
    except Exception as exc:
        return False, str(exc)
