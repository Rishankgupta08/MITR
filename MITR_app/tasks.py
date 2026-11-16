from django_q.tasks import async_task
from django.core.mail import send_mail
from datetime import date, timedelta
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_initial_email(task_id=None):
    from .models import Task

    if task_id is None:
        logger.error("Initial Email not sent: task_id is None")

    try:
        task = Task.objects.get(id=task_id)
        send_mail(
            f"NEW TASK ALERT!",
            f"""
Dear {task.employee},
You've been assigned a new task. Details have been listed below 
Task Name:-{task.title}
Task Description:-{task.description}
Client Name: {task.client_company}
Client Email: {task.email}
due date: {task.submission_date}

Please ensure it's completed before the due date.
It's essential that we complete this task before the due date to ensure our commitment to delivering high-quality service to our clients.
Your prompt action and attention to detail are greatly appreciated.

Thank you.

Regards,
Nescube Technology Private Limited
SD-135, Jaipuria Sunrise Plaza Indirapuram,Ghaziabad -201014 U.P. India
M:+91-9213093891 | +91-9213093892 | +91-120-4286333
Web: www.nescubeonline.com Support Partner:  www.nestechindia.com             
            """,
            'mitr.taskreminder@gmail.com',
            [task.employee.email],
            fail_silently=False,
        )
        logger.info(f"Initial email sent for task {task_id}")
    except Exception as e:
        logger.error(f"Error sending initial email for task {task_id}: {e}")

def scan_and_send_reminders():
    """
    Single scanner - runs every 30 min via django-q2 schedule.
    Checks all incomplete tasks and sends reminders if due.
    Atomic update prevents duplicate sends.
    """
    from django.db import models, transaction
    from django.conf import settings
    from .models import Task

    now = timezone.now()
    today = date.today()

    # --- Regular reminders -------------------------------------------------
    # Tasks the employee already marked as completed (awaiting verification)
    # are skipped, same as the old per-task reminder logic.
    due_tasks = Task.objects.filter(
        completed=False,
        employee_marked_completed=False,
        employee__isnull=False,
        next_reminder_date__lte=now,
    ).select_related('employee')

    for task in due_tasks:
        with transaction.atomic():
            # Atomic claim - prevents duplicate sends
            updated = Task.objects.filter(
                id=task.id,
                next_reminder_date=task.next_reminder_date,
            ).update(next_reminder_date=now + task.remind_every)
            if updated == 1:
                try:
                    send_mail(
                        subject=f'Task Reminder: {task.title}',
                        message=f'''
Dear {task.employee.name},

This is a reminder for task: {task.title}
Deadline: {task.submission_date}
Description: {task.description}

Please complete this task at your earliest convenience.
                        ''',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[task.employee.email],
                        fail_silently=True,
                    )
                    logger.info(f'Reminder sent for task {task.id}')
                except Exception as e:
                    logger.error(f'Reminder failed for task {task.id}: {e}')

    # --- Overdue reminders (12 hour throttle) -----------------------------
    twelve_hours_ago = now - timedelta(hours=12)
    throttle = (
        models.Q(last_overdue_reminder__isnull=True) |
        models.Q(last_overdue_reminder__lt=twelve_hours_ago)
    )
    overdue_tasks = Task.objects.filter(
        completed=False,
        employee_marked_completed=False,
        employee__isnull=False,
        submission_date__lt=today,
    ).filter(throttle).select_related('employee')

    for task in overdue_tasks:
        with transaction.atomic():
            updated = Task.objects.filter(id=task.id).filter(throttle).update(
                last_overdue_reminder=now
            )
            if updated == 1:
                try:
                    send_mail(
                        subject=f'OVERDUE: {task.title}',
                        message=f'Task {task.title} is overdue. Deadline was {task.submission_date}.',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[task.employee.email],
                        fail_silently=True,
                    )
                    logger.info(f'Overdue reminder sent for task {task.id}')
                except Exception as e:
                    logger.error(f'Overdue reminder failed for task {task.id}: {e}')


def send_subscription_confirmation_email(subscription_id,email=None):
    logger.info(f" CC EMAIL SENT to {email}")
    from .models import Subscription
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        send_mail(
            'Subscription Confirmation',
            f"""
Dear {subscription.customer_name},

Thank you for subscribing to our {subscription.subscription_type} service. 
Your subscription details are as follows:

Subscription Type: {subscription.subscription_type}
Description: {subscription.description}
Start Date: {subscription.start_date.strftime('%Y-%m-%d')}
End Date: {subscription.end_date.strftime('%Y-%m-%d')}

We will send you a reminder {subscription.get_ending_reminder_display()} before your subscription ends.

Regards,
Nescube Technology Private Limited
SD-135, Jaipuria Sunrise Plaza Indirapuram,Ghaziabad -201014 U.P. India
M:+91-9213093891 | +91-9213093892 | +91-120-4286333
Web: www.nescubeonline.com Support Partner:  www.nestechindia.com 
            """,
            'mitr.taskreminder@gmail.com',
            [ email if email is not None else subscription.customer_email],
            fail_silently=False,
        )
        logger.info(f"Subscription confirmation email sent for subscription {subscription_id}")
        if email is None:
            send_subscription_confirmation_email(subscription_id,email='kk.dwivedi@nescubeonline.com')
    except Exception as e:
        logger.error(f"Error sending subscription confirmation email for subscription {subscription_id}: {e}")

def send_subscription_reminder_email(subscription_id,email=None):
    from .models import Subscription
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        send_mail(
            'Subscription Ending Soon',
            f"""
Dear {subscription.customer_name},

We hope you're doing well.

This is a friendly reminder that your {subscription.subscription_type} subscription is set to expire on {subscription.end_date.strftime('%Y-%m-%d')}. 
To ensure uninterrupted access to our services and continue enjoying the benefits of your subscription, we encourage you to renew it before the expiration date. Renewing now will help you avoid any disruption in your access.
If you have any questions or need assistance with the renewal process, please don't hesitate to contact our support team. We are happy to assist you.  

Looking forward to continuing to serve you

Regards,
Nescube Technology Private Limited
SD-135, Jaipuria Sunrise Plaza Indirapuram,Ghaziabad -201014 U.P. India
M:+91-9213093891 | +91-9213093892 | +91-120-4286333
Web: www.nescubeonline.com Support Partner:  www.nestechindia.com 
            """,
            'mitr.taskreminder@gmail.com',
            [email if email is not None else subscription.customer_email],
            fail_silently=False,
        )
        logger.info(f"Subscription reminder email sent for subscription {subscription_id}")
        if email is None:
            send_subscription_reminder_email(subscription_id,email='kk.dwivedi@nescubeonline.com')
    except Exception as e:
        logger.error(f"Error sending subscription reminder email for subscription {subscription_id}: {e}")

def check_subscription_reminders():
    from .models import Subscription
    from datetime import datetime, timedelta
    
    try:
        now = timezone.now()
        active_subscriptions = Subscription.objects.filter(end_date__gt=now, reminder_sent=False)
        
        for subscription in active_subscriptions:
            reminder_days = {
                '1 Day': 1,
                '1 Week': 7,
                '1 Month': 30
            }
            days_before = reminder_days.get(subscription.ending_reminder, 1)
            reminder_date = subscription.end_date - timedelta(days=days_before)
            
            if now >= reminder_date:
                async_task(send_subscription_reminder_email, subscription.id)
                subscription.reminder_sent = True
                subscription.save()
                
        logger.info("Checked for subscription reminders")
    except Exception as e:
        logger.error(f"Error checking subscription reminders: {e}")


def send_subscription_ended_email(subscription_id):
    from .models import Subscription
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        send_mail(
            'Subscription Ended',
            f"""

Dear {subscription.customer_name},

We hope you're doing well.

We wanted to inform you that your {subscription.subscription_type} subscription ended on {subscription.end_date.strftime('%Y-%m-%d')}. 
To continue enjoying uninterrupted access to our services, we invite you to renew your subscription at your earliest convenience. Renewing now ensures you don’t miss out on the benefits and exclusive features that come with your membership.
If you have any questions or need assistance with the renewal process, feel free to reach out to our support team. We’re happy to help!

Looking forward to having you with us again.

Regards,
Nescube Technology Private Limited
SD-135, Jaipuria Sunrise Plaza Indirapuram,Ghaziabad -201014 U.P. India
M:+91-9213093891 | +91-9213093892 | +91-120-4286333
Web: www.nescubeonline.com Support Partner:  www.nestechindia.com 
            """,
            'mitr.taskreminder@gmail.com',
            [subscription.customer_email, 'kk.dwivedi@nescubeonline.com'],
            fail_silently=False,
        )
        logger.info(f"Subscription ended email sent for subscription {subscription_id}")
    except Exception as e:
        logger.error(f"Error sending subscription ended email for subscription {subscription_id}: {e}")


def check_ended_subscriptions():
    from .models import Subscription
    try:
        now = timezone.now()
        ended_subscriptions = Subscription.objects.filter(
            end_date__lte=now,
            end_notification_sent=False  # New field we'll add
        )
        
        for subscription in ended_subscriptions:
            async_task(send_subscription_ended_email, subscription.id)
            subscription.end_notification_sent = True
            subscription.save()
                
        logger.info(f"Checked for ended subscriptions. Found {ended_subscriptions.count()} ended subscriptions.")
    except Exception as e:
        logger.error(f"Error checking ended subscriptions: {e}")
