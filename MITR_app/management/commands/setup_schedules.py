from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule


class Command(BaseCommand):
    help = 'Create or update django-q2 Schedule entries for MITR background tasks.'

    def handle(self, *args, **options):
        now = timezone.localtime(timezone.now())
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        schedules = [
            {
                'name': 'check_overdue_tasks',
                'func': 'MITR_app.tasks.check_overdue_tasks',
                'schedule_type': Schedule.MINUTES,
                'minutes': 720,
                'repeats': -1,
                'next_run': now,
            },
            {
                'name': 'check_subscription_reminders',
                'func': 'MITR_app.tasks.check_subscription_reminders',
                'schedule_type': Schedule.HOURLY,
                'minutes': None,
                'repeats': -1,
                'next_run': now,
            },
            {
                'name': 'check_ended_subscriptions',
                'func': 'MITR_app.tasks.check_ended_subscriptions',
                'schedule_type': Schedule.DAILY,
                'minutes': None,
                'repeats': -1,
                'next_run': next_midnight,
            },
        ]

        for spec in schedules:
            obj, created = Schedule.objects.update_or_create(
                name=spec['name'],
                defaults={
                    'func': spec['func'],
                    'schedule_type': spec['schedule_type'],
                    'minutes': spec['minutes'],
                    'repeats': spec['repeats'],
                    'next_run': spec['next_run'],
                },
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f"{action} schedule '{obj.name}' ({obj.func})")
            )

