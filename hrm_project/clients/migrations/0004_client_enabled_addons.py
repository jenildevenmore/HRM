from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0003_client_schema_name_client_schema_provisioned'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='enabled_addons',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
