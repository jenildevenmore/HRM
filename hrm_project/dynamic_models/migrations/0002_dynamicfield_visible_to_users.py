from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dynamic_models', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dynamicfield',
            name='visible_to_users',
            field=models.BooleanField(default=True),
        ),
    ]
