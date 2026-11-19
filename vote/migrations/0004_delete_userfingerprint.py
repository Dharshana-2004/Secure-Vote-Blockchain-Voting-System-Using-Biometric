from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('vote', '0003_alter_userfingerprint_template_format'),
    ]

    operations = [
        migrations.DeleteModel(
            name='UserFingerprint',
        ),
    ]








