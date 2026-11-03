from django.apps import AppConfig

class MitrAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'MITR_app'
    def ready(self):
            import MITR_app.signals