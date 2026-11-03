
from celery import shared_task
from django.core.mail import send_mail
from datetime import timedelta
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

@shared_task
def send_initial_email(task_id=None):
    from .models import Task

    if task_id is not None:
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

@shared_task
def send_reminder_email(task_id=None):
    from .models import Task

    if task_id is not None:
        logger.error("Reminder Email not sent: task_id is None")

    try:
        task = Task.objects.get(id=task_id)
        current_time = timezone.now()

        # Skip if the task is already completed
        if task.employee_marked_completed:
            logger.info(f"Task {task_id} is already completed, skipping reminder")
            return

        # Pending tasks
        if current_time >= task.next_reminder_date:
            # Check if enough time has passed since the last reminder
            if current_time < task.next_reminder_date + timedelta(minutes=5):
                logger.info(f"Skipping duplicate reminder for task {task_id}")
                return

            send_mail(
                f"Reminder: {task.title}",
                f"""
Dear {task.employee},

Just a reminder about the task assigned to you.

Task Name: {task.title}
Task Description: {task.description}
Client Name: {task.client_company}
Client Email: {task.email}

Please make sure to complete it before the due date {task.submission_date}.

Thank you 

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
            logger.info(f"Reminder email sent for task {task_id}")

            # Update next reminder date before scheduling
            task.next_reminder_date = current_time + task.remind_every
            task.save()

            # Schedule the next reminder
            send_reminder_email.apply_async((task.id,), eta=task.next_reminder_date)

        # Overdue tasks
        elif current_time.date() >= task.submission_date:
            # Check if an overdue reminder was sent in the last 12 hours
            if hasattr(task, 'last_overdue_reminder') and task.last_overdue_reminder:
                if current_time < task.last_overdue_reminder + timedelta(hours=11):  # Buffer of 1 hour
                    logger.info(f"Skipping duplicate overdue reminder for task {task_id}")
                    return

            send_mail(
                f"Overdue Task Reminder: {task.title}",
                f"""
Dear {task.employee},

The task assigned to you is overdue.

Task Name: {task.title}
Task Description: {task.description}
Client Name: {task.client_company}
Client Email: {task.email}

Please complete it as soon as possible.

Thank you 

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
            logger.info(f"Overdue reminder email sent for task {task_id}")

            # Update last overdue reminder timestamp
            task.last_overdue_reminder = current_time
            task.save()

            # Schedule the next overdue reminder
            send_reminder_email.apply_async((task.id,), eta=current_time + timedelta(hours=12))

    except Task.DoesNotExist:
        logger.error(f"Task {task_id} does not exist")
    except Exception as e:
        logger.error(f"Error sending reminder email for task {task_id}: {e}")

@shared_task
def check_overdue_tasks(task_id=None):
    from .models import Task
    from datetime import datetime, timedelta

    if task_id is not None:
        logger.info("\r\n No task to check")
        return

    try:
        today = datetime.now().date()
        overdue_tasks = Task.objects.filter(completed=False, submission_date__lt=today, id=task_id)

        for task in overdue_tasks:
            overdue_since = today - task.submission_date
            if overdue_since.days <= 30:
                send_reminder_email.delay(task.id)
        
        logger.info("Checked for overdue tasks and scheduled reminders")
    except Exception as e:
        logger.error(f"Error checking overdue tasks: {e}")

@shared_task
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

@shared_task
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

@shared_task
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
                send_subscription_reminder_email.delay(subscription.id)
                subscription.reminder_sent = True
                subscription.save()
                
        logger.info("Checked for subscription reminders")
    except Exception as e:
        logger.error(f"Error checking subscription reminders: {e}")

@shared_task
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


@shared_task
def check_ended_subscriptions():
    from .models import Subscription
    try:
        now = timezone.now()
        ended_subscriptions = Subscription.objects.filter(
            end_date__lte=now,
            end_notification_sent=False  # New field we'll add
        )
        
        for subscription in ended_subscriptions:
            send_subscription_ended_email.delay(subscription.id)
            subscription.end_notification_sent = True
            subscription.save()
                
        logger.info(f"Checked for ended subscriptions. Found {ended_subscriptions.count()} ended subscriptions.")
    except Exception as e:
        logger.error(f"Error checking ended subscriptions: {e}")
