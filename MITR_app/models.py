from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from datetime import timedelta, datetime
from django.core.mail import send_mail
from django.utils import timezone
from django_q.tasks import async_task
from .tasks import send_reminder_email
import logging
import subprocess

logger = logging.getLogger(__name__)


settings.AUTH_USER_MODEL


class CustomUser(AbstractUser):
    company = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    is_superuser = models.BooleanField(default=False)


    def __str__(self):
        return self.username  # You can choose any field as a string representation
    
    def is_employee(self):
        return hasattr(self, 'employee')


class Task(models.Model):
    REMIND_CHOICES = (
        ('', '---------'),
        (timedelta(hours=1), '1 Hour'),
        (timedelta(hours=2), '2 Hours'),
        (timedelta(hours=3), '3 Hours'),
        (timedelta(hours=4), '4 Hours'),
        (timedelta(hours=5), '5 Hours'),
        (timedelta(hours=6), '6 Hours'),
        (timedelta(hours=12), '12 Hours'),
        (timedelta(days=1), '1 Day'),
        (timedelta(days=2), '2 Days'),
        (timedelta(days=3), '3 Days'),
        (timedelta(days=7), '1 Week'),
        (timedelta(weeks=2), '2 Weeks'),
        (timedelta(weeks=3), '3 Weeks'),
        (timedelta(weeks=4), '1 Month'),
    )
    task_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False,  # Prevent manual editing in forms/admin
        default=None,
        null=True,  # Allow null initially for pre-save generation
        blank=True
    )
    title = models.CharField(max_length=100)
    description = models.TextField()
    email = models.EmailField()
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, null=True, blank=True)
    remind_every = models.DurationField()
    submission_date = models.DateField(default=datetime.now())
    date_added = models.DateTimeField(default=timezone.now)
    completed = models.BooleanField(default=False)
    client_company = models.CharField(max_length=100,null=True)
    client_phone_number = models.CharField(max_length=15)  
    employee_marked_completed = models.BooleanField(default=False)
    next_reminder_date = models.DateTimeField(default=timezone.now)
    completed_date = models.DateTimeField(null=True, blank=True)
    overdue_reason = models.CharField(max_length=5000, null=True, default="")
    completed_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='completed_tasks')
    completed_at = models.DateTimeField(null=True, blank=True)
    rework_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='reworked_tasks')
    rework_date = models.DateTimeField(null=True, blank=True)
    last_overdue_reminder = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.next_reminder_date:
            self.next_reminder_date = timezone.now() + self.remind_every
        if self.completed and not self.completed_date:
            self.completed_date = timezone.now()
        
        super().save(*args, **kwargs)

        # Schedule reminder emails
        if not self.completed:
            self.schedule_reminder_emails()

    def complete_task(self, user):
        self.completed = True
        self.completed_by = user
        self.completed_at = timezone.now()
        self.save()

    def __str__(self):
        return self.title

    
    def send_task_email(self):
        subject = self.title
        message = f"""
        Task Title: {self.title}
        Description: {self.description}
        Submission Date: {self.submission_date}
        """
        send_mail(
            subject,
            message,
            'mitr.reminder@gmail.com',
            [self.employee.email],
            fail_silently=False,
        )

    def schedule_reminder_emails(self):
        if not self.completed:
            async_task(send_reminder_email, self.id)

class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15)
    company = models.CharField(max_length=100, default='TO_BE_ASSIGNED')
    coordinator = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class Subscription(models.Model):
    SUBSCRIPTION_TYPES = [
        ('amazon_prime', 'Amazon Prime'),
        ('netflix', 'Netflix'),
        ('disney_hotstar', 'Disney+ Hotstar'),
    ]
    
    REMINDER_CHOICES = [
        ('1 Day', '1 Day'),
        ('1 Week', '1 Week'),
        ('1 Month', '1 Month'),
    ]
    
    subscription_type = models.CharField(max_length=50)
    description = models.TextField()
    ending_reminder = models.CharField(max_length=20, choices=REMINDER_CHOICES)
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=15)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    reminder_sent = models.BooleanField(default=False)
    end_notification_sent = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.customer_name} - {self.subscription_type}"
    
    def save(self, *args, **kwargs):
        if not self.pk and not self.end_date:  # Only on creation and if end_date not set
            self.end_date = timezone.now() + timedelta(days=30)  # Default to 30 days if no end_date provided
        super().save(*args, **kwargs)
        
    @property
    def status(self):
        now = timezone.now()
        if self.end_date >= now:
            return 'Active'
        else:
            return 'Expired'
