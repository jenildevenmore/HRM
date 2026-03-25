from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0007_clientrole_enabled_addons_clientrole_module_permissions'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE clients_client
                    ADD COLUMN IF NOT EXISTS execution_secret_key varchar(128);
                    ALTER TABLE clients_client
                    ADD COLUMN IF NOT EXISTS execution_key_activated_at timestamptz NULL;
                    UPDATE clients_client
                    SET execution_secret_key = md5(random()::text || clock_timestamp()::text)
                    WHERE execution_secret_key IS NULL OR execution_secret_key = '';
                    ALTER TABLE clients_client
                    ALTER COLUMN execution_secret_key SET NOT NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='client',
                    name='execution_secret_key',
                    field=models.CharField(blank=True, default='', max_length=128),
                ),
                migrations.AddField(
                    model_name='client',
                    name='execution_key_activated_at',
                    field=models.DateTimeField(blank=True, null=True),
                ),
            ],
        ),
    ]

