from contextlib import contextmanager
from django.db.models.signals import post_save
from .signals import update_employee_progress
from .models import Task

@contextmanager
def disable_signals():
    """Temporarily disable signals for data loading"""
    post_save.disconnect(update_employee_progress, sender=Task)
    try:
        yield
    finally:
        post_save.connect(update_employee_progress, sender=Task)
