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
                'name': 'scan_and_send_reminders',
                'func': 'MITR_app.tasks.scan_and_send_reminders',
                'schedule_type': Schedule.MINUTES,
                'minutes': 30,
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
                defaults={k: v for k, v in spec.items() if k != 'name'},
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f"{action} schedule: {obj.name}")
            )

        # Remove obsolete schedules (per-task self-chained reminders and the
        # old overdue checker, now folded into scan_and_send_reminders).
        deleted = Schedule.objects.filter(name__startswith='reminder_task_').delete()
        self.stdout.write(f"Deleted {deleted[0]} old per-task schedules")
        deleted = Schedule.objects.filter(name='check_overdue_tasks').delete()
        self.stdout.write(f"Deleted {deleted[0]} obsolete check_overdue_tasks schedule")
