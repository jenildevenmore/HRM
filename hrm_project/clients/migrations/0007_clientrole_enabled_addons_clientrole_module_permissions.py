from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0006_client_role_limit_clientrole'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientrole',
            name='enabled_addons',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='clientrole',
            name='module_permissions',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
