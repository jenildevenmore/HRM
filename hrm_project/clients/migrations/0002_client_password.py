from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='password',
            field=models.CharField(default='', max_length=128),
        ),
    ]
