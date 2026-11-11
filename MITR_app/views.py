# Create your views here.
import matplotlib
matplotlib.use('Agg')
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_backends
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from .models import Task, Employee, Subscription
from .forms import TaskForm, RegistrationForm, LoginForm, EmployeeForm
from .decorators import admin_required, coordinator_or_admin_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from datetime import date, datetime, timedelta
from django.http import HttpResponse
from django.utils.timezone import now
import matplotlib.pyplot as plt
import os
import pandas as pd
import xlsxwriter
from django.utils import timezone
from django.db.models import F
import pytz
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
from django.conf import settings
from django_q.tasks import async_task
from .tasks import (
    send_subscription_confirmation_email
)

import logging
logger = logging.getLogger(__name__)
User = get_user_model()

def login_register_view(request):
    active_form = None
    if request.method == 'POST':
        if 'login' in request.POST:  # Distinguish between login and register forms
            active_form = 'login'
            login_form = LoginForm(request.POST)
            register_form = RegistrationForm()

            if login_form.is_valid():
                email = login_form.cleaned_data['email']
                password = login_form.cleaned_data['password']
                user = authenticate(request, email=email, password=password)
                if user is not None:
                    login(request, user)
                    # Check if the user is an employee
                    is_employee = Employee.objects.filter(email__iexact=user.email).exists()
                    request.session['is_employee'] = is_employee
                    return redirect('dashboard')

            request.session['login_error'] = 'Invalid email or password.'
            return redirect('login_register')

        elif 'register' in request.POST:  # Handle registration form submission
            active_form = 'register'
            login_form = LoginForm()
            register_form = RegistrationForm(request.POST)

            if register_form.is_valid():
                user = register_form.save(commit=False)
                user.username = (
                    request.POST.get('username')
                    or register_form.cleaned_data['email']
                )
                user.company = (
                    register_form.cleaned_data.get('company') or 'NTPL'
                )
                role = register_form.cleaned_data.get('role', 'employee')

                # Never make registered users superuser
                # Superuser is created ONLY via manage.py createsuperuser
                user.is_superuser = False
                user.is_staff = False
                user.save()

                # Create Employee record linked to this user
                employee, created = Employee.objects.get_or_create(
                    email=user.email,
                    defaults={
                        'user': user,
                        'name': user.username,
                        'company': user.company,
                        'coordinator': (role == 'coordinator'),
                        'phone_number': '',
                    }
                )
                if not created:
                    employee.user = user
                    employee.coordinator = (role == 'coordinator')
                    if not employee.company:
                        employee.company = user.company
                    employee.save()

                login(
                    request,
                    user,
                    backend='MITR_app.backends.EmailBackend',
                )
                request.session['is_employee'] = True
                return redirect('dashboard')
            else:
                error_messages = {}
                for field, errors in register_form.errors.items():
                    # Convert internal field names to user-friendly labels
                    field_labels = {
                        'username': 'Username',
                        'email': 'Email',
                        'role': 'Role',
                        'password1': 'Password',
                        'password2': 'Confirm Password',
                        'company': 'Company',
                    }
                    label = field_labels.get(field, field.replace('_', ' ').title())
                    error_messages[label] = [str(e) for e in errors]

                # Also clean up common Django password messages
                if 'Confirm Password' in error_messages:
                    cleaned = []
                    for msg in error_messages['Confirm Password']:
                        if 'too common' in msg:
                            cleaned.append('Password is too common. Add letters and symbols.')
                        elif 'entirely numeric' in msg:
                            cleaned.append('Password cannot be only numbers.')
                        elif 'too short' in msg:
                            cleaned.append('Password must be at least 8 characters.')
                        elif 'similar' in msg:
                            cleaned.append('Password is too similar to your username or email.')
                        else:
                            cleaned.append(msg)
                    error_messages['Confirm Password'] = cleaned
                    error_messages['Confirm_Password'] = cleaned

                if 'Password' in error_messages:
                    cleaned = []
                    for msg in error_messages['Password']:
                        if 'too common' in msg:
                            cleaned.append('Password is too common. Add letters and symbols.')
                        elif 'entirely numeric' in msg:
                            cleaned.append('Password cannot be only numbers.')
                        elif 'too short' in msg:
                            cleaned.append('Password must be at least 8 characters.')
                        else:
                            cleaned.append(msg)
                    error_messages['Password'] = cleaned

                request.session['register_errors'] = {
                    'field_errors': error_messages,
                    'general_error': 'Please fix the errors below.',
                    'active_form': 'register',
                }
                return redirect('login_register')

    # Retrieve session errors if any (GET request)
    session_errors = request.session.pop('register_errors', None)
    login_session_error = request.session.pop('login_error', None)

    if session_errors:
        active_form = session_errors.get('active_form', 'register')
    elif login_session_error:
        active_form = 'login'
    else:
        active_form = ''

    context = {
        'login_form': LoginForm(),
        'register_form': RegistrationForm(),
        'active_form': active_form,
        'field_errors': session_errors.get('field_errors', {}) if session_errors else {},
        'general_error': session_errors.get('general_error', '') if session_errors else '',
        'login_error': login_session_error or '',
    }
    return render(request, 'login_register.html', context)

def logout_view(request):
    logout(request)
    return redirect('login_register')

@admin_required
def update_coordinator(request, employee_id):
    if request.method == "POST":
        try:
            employee = get_object_or_404(Employee, id=employee_id)
            
            # Try to get data from POST first
            coordinator_status = request.POST.get("coordinator", None)
            
            # If not in POST, try to parse from body
            if coordinator_status is None and request.body:
                import json
                try:
                    data = json.loads(request.body)
                    coordinator_status = data.get("coordinator", "false")
                except json.JSONDecodeError:
                    # If not JSON, try to parse URL-encoded data
                    from urllib.parse import parse_qs
                    body_data = parse_qs(request.body.decode('utf-8'))
                    coordinator_status = body_data.get("coordinator", ["false"])[0]
            
            # Convert string to boolean
            if isinstance(coordinator_status, str):
                coordinator_status = coordinator_status.lower() == "true"
            
            employee.coordinator = coordinator_status
            employee.save()
            print(f"{employee.name} {'Set as' if employee.coordinator else 'Removed as'} Coordinator")
            return JsonResponse({"success": True, "coordinator": employee.coordinator})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
def dashboard_view(request):
    from .tasks import send_initial_email

    user = request.user
    company = user.company or 'NTPL'

    # Determine role
    is_admin = user.is_superuser
    employee = (
        Employee.objects.filter(user=user).first()
        or Employee.objects.filter(email__iexact=user.email).first()
    )

    if is_admin:
        # Admin sees all tasks in their company
        tasks = Task.objects.filter(
            employee__company=company
        ).select_related('employee').order_by('-date_added')
        is_coordinator = True
        is_employee = False
    elif employee and employee.coordinator:
        # Coordinator sees all tasks in their company
        tasks = Task.objects.filter(
            employee__company=company
        ).select_related('employee').order_by('-date_added')
        is_coordinator = True
        is_employee = False
    elif employee:
        # Regular employee sees ONLY their own tasks
        tasks = Task.objects.filter(
            employee=employee
        ).select_related('employee').order_by('-date_added')
        is_coordinator = False
        is_employee = True
    else:
        tasks = Task.objects.none()
        is_coordinator = False
        is_employee = True

    # HANDLE TASK FORM & EMPLOYEE FORM
    form = TaskForm(user=request.user)
    form_has_errors = False
    employee_form = EmployeeForm()

    if request.method == 'POST':
        if 'taskForm' in request.POST and (is_admin or is_coordinator):
            form = TaskForm(user=request.user, data=request.POST)
            if form.is_valid():
                task = form.save(commit=False)
                task.date_added = timezone.now()
                task.task_id = timezone.now().astimezone(pytz.timezone('Asia/Kolkata')).strftime('%d%m%Y%H%M%S')
                task.save()
                async_task(send_initial_email, task.id)
                return redirect(f'{reverse("dashboard")}?task_added=true')
            else:
                form_has_errors = True
        elif 'addEmployeeForm' in request.POST and is_admin:
            employee_form = EmployeeForm(request.POST)
            if employee_form.is_valid():
                new_emp = employee_form.save(commit=False)
                new_emp.company = company
                new_emp.save()
                return redirect(f'{reverse("dashboard")}?employee_added=true')

    # SEARCH
    search_query = request.GET.get('search', '')
    if search_query:
        tasks = tasks.filter(title__icontains=search_query)

    # Pagination
    paginator = Paginator(tasks, 10)  # Show 10 tasks per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'tasks': page_obj,
        'is_admin': is_admin,
        'is_superuser': is_admin,
        'is_coordinator': is_coordinator,
        'is_employee': is_employee,
        'employee': employee,
        'today': date.today(),
        'search_query': search_query,
        'form': form,
        'form_has_errors': form_has_errors,
        'employee_form': employee_form,
    }
    return render(request, 'dashboard.html', context)
     
@admin_required
def add_employee_view(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return redirect('login_register')

    # Retrieve the logged-in user's company
    company = request.user.company

    if request.method == 'POST':
        # Create a form instance and populate it with data from the request
        form = EmployeeForm(request.POST)
        if form.is_valid():
            # Create a new employee object but don't save it yet
            employee = form.save(commit=False)
            # Associate the employee with the user's company
            employee.company = company
            # Save the employee to the database
            employee.save()
            # Redirect to a success page or another relevant page
            return redirect(f'{reverse("dashboard")}?employee_added=true')  # Redirect with employee_added parameter
    else:
        # If it's a GET request, create an empty form
        form = EmployeeForm()

    return render(request, 'add_employee.html', {'form': form})

 
@login_required
def task_view(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    user = request.user
    is_admin = user.is_superuser
    employee = (
        Employee.objects.filter(user=user).first()
        or Employee.objects.filter(email__iexact=user.email).first()
    )
    is_coordinator = bool(is_admin or (employee and employee.coordinator))
    is_employee = bool(not is_admin and not is_coordinator)

    form = TaskForm(request.POST or None, instance=task)

    if request.method == 'POST':
        if is_employee and 'mark_as_completed' in request.POST:
            overdue_reason = request.POST.get('overdue_reason', '').strip()
            if not overdue_reason and task.submission_date <= datetime.now().date():
                form.add_error('overdue_reason', 'Reason for overdue is required if you mark the task as completed.')
            else:
                task.employee_marked_completed = True
                task.completed_date = datetime.now()
                task.overdue_reason = overdue_reason
                task.save()
                return redirect('task_view', task_id=task.id)
        elif (is_admin or is_coordinator) and 'complete_task' in request.POST:
            task.completed = True
            task.completed_at = datetime.now()
            task.completed_by = user
            task.save()
            return redirect('task_view', task_id=task.id)
        elif (is_admin or is_coordinator) and 'rework_task' in request.POST:
            task.rework_by = user
            task.rework_date = timezone.now()
            task.save()
            return redirect('task_view', task_id=task.id)

    context = {
        'task': task,
        'today': now().astimezone(pytz.timezone('Asia/Kolkata')).date(),
        'is_admin': is_admin,
        'is_coordinator': is_coordinator,
        'is_employee': is_employee,
        'form': form,
        'employee': employee,
    }
    return render(request, 'task_view.html', context)

 
@admin_required
def delete_task_view(request, task_id):
    # Get the task object or return a 404 error if not found
    task = get_object_or_404(Task, id=task_id)

    # Check if the user is authorized to delete the task (e.g., only employers)
    if not request.user.is_superuser:
        return HttpResponse("Unauthorized", status=401)  # Return an unauthorized response

    # Delete the task
    task.delete()

    # Redirect to the dashboard or any other appropriate page after deletion
    return redirect('dashboard')

 
@admin_required
def set_incomplete_view(request, task_id):
    # Get the task object or return a 404 error if not found
    task = get_object_or_404(Task, id=task_id)

    # Check if the user is authorized to set the task as incomplete
    # For example, only employers or users with specific permissions can do this
    if not request.user.is_superuser:
        return HttpResponse("Unauthorized", status=401)  # Return an unauthorized response

    # Set the task as incomplete
    task.completed = False
    task.save()

    # Redirect to the task view or any other appropriate page after updating
    return redirect('task_view', task_id=task.id)

 
@coordinator_or_admin_required
def employee_list_view(request):
    company = request.user.company
    user_email = request.user
    is_superuser = user_email.is_superuser
    
    # Default values
    employee = None
    is_employee = False

    # Try to fetch the employee object if the user is not a superuser
    if not is_superuser:
        try:
            employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
            is_employee = True
            # Redirect regular employees to dashboard
            if not employee.coordinator:
                return redirect('dashboard')
        except Employee.DoesNotExist:
            employee = None
            print(f"No employee record found for user: {user_email}")
    
    employees = Employee.objects.filter(company=company)
    return render(request, 'employee_list.html', {'employees': employees,'is_employee': is_employee,'is_superuser': is_superuser,'employee': employee})

 
@admin_required
def remove_employee_view(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee removed successfully.')
        return redirect('employee_list')
    return render(request, 'confirm_remove_employee.html', {'employee': employee})

 
@admin_required
def confirm_remove_employee(request, id):
    employee = get_object_or_404(Employee, id=id)
    if request.method == 'POST':
        employee.delete()
        return redirect('employee_list')  # Redirect to the dashboard after deletion

    return render(request, 'confirm_remove_employee.html', {'employee': employee})

 
def collect_employee_data(employee_id):
    employee = Employee.objects.get(id=employee_id)
    total_tasks = Task.objects.filter(employee=employee).count()
    completed_tasks = Task.objects.filter(employee=employee, completed=True).count()
    overdue_tasks = Task.objects.filter(employee=employee, completed=False, submission_date__lt=datetime.now().date()).count()
    pending_tasks = Task.objects.filter(employee=employee, completed=False, submission_date__gt=datetime.now().date()).count()

    data = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
        'pending_tasks' : pending_tasks
    }

    return employee.name, data

def plot_employee_progress(employee_id):
    employee_name, data = collect_employee_data(employee_id)
    colors = ['grey', 'green', 'red', 'blue']
    df = pd.DataFrame([data], index=[employee_name])
    df.plot(kind='bar', figsize=(10, 6), color=colors)

    plt.title(f'{employee_name} Task Progress')
    plt.xlabel('Tasks')
    plt.ylabel('Number of Tasks')
    plt.xticks(rotation=0)
    plt.legend(['Total Tasks', 'Completed Tasks', 'Overdue Tasks', 'Pending Tasks'])
    plt.tight_layout()

    # ✅ save inside MEDIA_ROOT
    image_filename = f'progress_graph_employee-{employee_id}.png'
    image_dir = os.path.join(settings.MEDIA_ROOT, 'progress')
    os.makedirs(image_dir, exist_ok=True)

    image_path = os.path.join(image_dir, image_filename)
    plt.savefig(image_path)
    plt.close()

    # ✅ return MEDIA_URL
    return settings.MEDIA_URL + f'progress/{image_filename}'
 
@coordinator_or_admin_required
def employee_progress(request, employee_id):
    user_email = request.user
    is_superuser = user_email.is_superuser
    
    # Default values
    current_employee = None

    # Try to fetch the employee object if the user is not a superuser
    if not is_superuser:
        try:
            current_employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
            # Redirect regular employees to dashboard
            if not current_employee.coordinator:
                return redirect('dashboard')
        except Employee.DoesNotExist:
            current_employee = None
            print(f"No employee record found for user: {user_email}")

    employee = get_object_or_404(Employee, id=employee_id)
    tasks = Task.objects.filter(employee=employee)
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(completed=True).count()
    pending_tasks = tasks.filter(completed=False).count()
    overdue_tasks = Task.objects.filter(employee=employee, completed=False, submission_date__lt=datetime.now().date()).count()
    progress_graph_url = None
    try:
        progress_graph_url = plot_employee_progress(employee_id)
        chart_generated = True
    except Exception as e:
        logger.warning(f"Chart generation failed: {e}")
        chart_generated = False
    today = datetime.today().date()
    is_superuser = request.user.is_superuser
    context = {
        'is_superuser': is_superuser,
        'employee': employee,
        'coordinator': employee.coordinator,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'tasks': tasks,
        'progress_graph_url': progress_graph_url,
        'chart_url': progress_graph_url,
        'chart_generated': chart_generated,
        'today': today,
        'overdue_tasks' : overdue_tasks,
    }

    return render(request, 'employee_progress.html', context)

 
def generate_summary(date):
    start_date = datetime.datetime.combine(date, datetime.time.min)
    end_date = datetime.datetime.combine(date, datetime.time.max)

    created_tasks = Task.objects.filter(created_at__range=(start_date, end_date))
    completed_tasks = Task.objects.filter(completed_at__range=(start_date, end_date))
    overdue_tasks = Task.objects.filter(submission_date__lt=date, completed=False)

    summary = {
        'date': date,
        'created_tasks': created_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
    }

    return summary

@coordinator_or_admin_required
def summary_report(request):
     user_email = request.user
     is_superuser = user_email.is_superuser
     company = user_email.company
     # Default values
     employee = None
     is_employee = False
 
     # Try to fetch the employee object if the user is not a superuser
     if not is_superuser:
         try:
             employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
             is_employee = True
             # Redirect regular employees to dashboard
             if not employee.coordinator:
                 return redirect('dashboard')
         except Employee.DoesNotExist:
             employee = None
             print(f"No employee record found for user: {user_email}")
 
     selected_date_str = request.GET.get('date', datetime.now().strftime('%Y-%m-%d'))
     report_type = request.GET.get('report_type', 'daily')
     status_filter = request.GET.get('status_filter', 'all')
 
     selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
 
     if report_type == 'weekly':
         start_date = selected_date - timedelta(days=selected_date.weekday())
         end_date = start_date + timedelta(days=6)
     elif report_type == 'monthly':
         start_date = selected_date.replace(day=1)
         end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
     else:  # Daily
         start_date = selected_date
         end_date = selected_date
 
     tasks_created = set(Task.objects.filter(date_added__date__range=[start_date, end_date],employee__company=company).order_by('-date_added'))
     tasks_completed = set(Task.objects.filter(completed=True, completed_date__isnull=False,employee__company=company).order_by('-date_added'))
     tasks_overdue = set(Task.objects.filter(submission_date__lt=selected_date, completed=False,employee__company=company).order_by('-date_added'))
 
     all_tasks = tasks_created | tasks_completed | tasks_overdue
     user_email = request.user
     is_superuser = user_email.is_superuser
     
     # Default values
     employee = None
     is_employee = False
 
     # Try to fetch the employee object if the user is not a superuser
     if not is_superuser:
         try:
             employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
             is_employee = True
         except Employee.DoesNotExist:
             # Handle the case where the user is not linked to an employee
             employee = None
             print(f"No employee record found for user: {user_email}")
     # Apply the status filter
     if status_filter != 'all':
         if status_filter == 'completed':
             all_tasks = {task for task in all_tasks if task.completed and task.completed_date.date() <= task.submission_date}
         elif status_filter == 'pending':
             all_tasks = {task for task in all_tasks if not task.completed and task.submission_date >= selected_date}
         elif status_filter == 'overdue':
             all_tasks = {task for task in all_tasks if not task.completed and task.submission_date < selected_date}
         elif status_filter == 'completed_overdue':
             all_tasks = {task for task in all_tasks if task.completed and task.completed_date.date() > task.submission_date}
 
     return render(request, 'summary_report.html', {
         'all_tasks': all_tasks,
         'selected_date': selected_date,
         'report_type': report_type,
         'status_filter': status_filter,
         'is_employee': is_employee,
         'is_superuser': is_superuser,
         'employee': employee
     })
def remove_timezone_from_datetime(dt):
    """Remove timezone information from a datetime object."""
    if dt is not None:
        return dt.replace(tzinfo=None)
    return dt

@coordinator_or_admin_required
def download_summary_report(request, date, report_type, status_filter):
    selected_date = datetime.strptime(date, '%Y-%m-%d').date()

    if report_type == 'weekly':
        start_date = selected_date - timedelta(days=selected_date.weekday())
        end_date = start_date + timedelta(days=6)
    elif report_type == 'monthly':
        start_date = selected_date.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:  # Daily
        start_date = selected_date
        end_date = selected_date

    # Ensure tasks_created and tasks_completed are filtered correctly
    tasks_created = Task.objects.filter(date_added__date__range=[start_date, end_date])
    tasks_completed = Task.objects.filter(completed=True, completed_date__isnull=False)
    tasks_overdue = Task.objects.filter(submission_date__lt=selected_date, completed=False)

    all_tasks = tasks_created | tasks_completed | tasks_overdue

    # Apply the status filter
    if status_filter != 'all':
        if status_filter == 'completed':
            all_tasks = all_tasks.filter(completed=True, completed_date__lte=F('submission_date'))
        elif status_filter == 'pending':
            all_tasks = all_tasks.filter(completed=False, submission_date__gte=selected_date)
        elif status_filter == 'overdue':
            all_tasks = all_tasks.filter(completed=False, submission_date__lt=selected_date)
        elif status_filter == 'completed_overdue':
            all_tasks = all_tasks.filter(completed=True, completed_date__gt=F('submission_date'))

    # Create an in-memory output file for the new workbook.
    output = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    output['Content-Disposition'] = f'attachment; filename="summary_report_{date}_{report_type}_{status_filter}.xlsx"'

    # Create an Excel workbook and worksheet
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    # Define the columns
    columns = [
        'Task ID','Task Title', 'Description', 'Client Company','Phone Number','Email',
        'Date Added', 'Submission Date', 'Completed Date', 'Status', 'Employee', 'Overdue_Reason'
    ]

    # Write the column headers
    for col_num, column_title in enumerate(columns):
        worksheet.write(0, col_num, column_title)

    # Write the data
    for row_num, task in enumerate(all_tasks, start=1):
        status = 'Pending'
        if task.completed:
            if task.completed_date and task.completed_date.date() and task.completed_date.date() > task.submission_date:
                status = 'Completed Overdue'
            else:
                status = 'Completed'
        elif task.submission_date < selected_date:
            status = 'Overdue'

        row = [
            task.task_id, task.title, task.description, task.client_company, task.client_phone_number, task.email,
            remove_timezone_from_datetime(task.date_added),
            task.submission_date.strftime('%Y-%m-%d') if task.submission_date else 'Missing Date',
            remove_timezone_from_datetime(task.completed_at) if task.completed_at else '',
            status, str(task.employee), task.overdue_reason
        ]

        for col_num, cell_value in enumerate(row):
            if isinstance(cell_value, datetime):
                cell_value = cell_value.strftime('%Y-%m-%d %H:%M:%S')  # Format datetime for Excel
            worksheet.write(row_num, col_num, cell_value)

    # Close the workbook
    workbook.close()
    
    return output

@coordinator_or_admin_required
def subscriptions(request):
                # Check if user is superuser first
    user_email = request.user
    is_superuser = user_email.is_superuser
    
    # Default values
    employee = None
    is_employee = False
    current_time = timezone.now()

    # Try to fetch the employee object if the user is not a superuser
    if not is_superuser:
        try:
            employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
            is_employee = True
        except Employee.DoesNotExist:
            # Handle the case where the user is not linked to an employee
            employee = None
            print(f"No employee record found for user: {user_email}")

    # Get all subscriptions ordered by start date
    subscriptions_list = Subscription.objects.all().order_by('-start_date')
    
    # Pagination
    paginator = Paginator(subscriptions_list, 10)  # Show 10 subscriptions per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    if request.user.is_superuser:
        context = {
            'subscriptions': page_obj,
            'reminder_choices': Subscription.REMINDER_CHOICES,
            'now': current_time,
            'is_employee': is_employee,
            'is_superuser': is_superuser,
            'employee': employee
        }
        return render(request, 'subscriptions.html', context)
    
    # For regular users, check employee status
    try:
        employee = Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email)
        if not employee.coordinator:
            return redirect('dashboard')
            
        context = {
            'employee': employee,
            'subscriptions': page_obj,
            'reminder_choices': Subscription.REMINDER_CHOICES,
            'now': current_time,
            'is_employee': is_employee,
            'is_superuser': is_superuser,
        }
        return render(request, 'subscriptions.html', context)
    except Employee.DoesNotExist:
        if request.user.is_superuser:
            context = {
                'subscriptions': page_obj,
                'reminder_choices': Subscription.REMINDER_CHOICES,
                'now': current_time,
                'is_employee': is_employee,
                'is_superuser': is_superuser,
                'employee': employee
            }
            return render(request, 'subscriptions.html', context)

        else:
            return redirect('dashboard')

@coordinator_or_admin_required
def add_subscription(request):
    # Check if user is superuser first
    if request.user.is_superuser:
        if request.method == 'POST':
            # Convert end_date string to datetime and set it to end of day
            end_date = datetime.strptime(request.POST['end_date'], '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            end_date = timezone.make_aware(end_date)
            
            subscription = Subscription.objects.create(
                subscription_type=request.POST['subscription_type'],
                description=request.POST['description'],
                ending_reminder=request.POST['ending_reminder'],
                customer_name=request.POST['customer_name'],
                customer_email=request.POST['customer_email'],
                customer_phone=request.POST['customer_phone'],
                end_date=end_date,
            )
            async_task(send_subscription_confirmation_email, subscription.id)
            return redirect('subscriptions')
        return redirect('subscriptions')

    # For non-superusers, check employee status
    try:
        employee = Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email)
        if not employee.coordinator:
            return redirect('dashboard')
            
        if request.method == 'POST':
            # Convert end_date string to datetime and set it to end of day
            end_date = datetime.strptime(request.POST['end_date'], '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            end_date = timezone.make_aware(end_date)
            
            subscription = Subscription.objects.create(
                subscription_type=request.POST['subscription_type'],
                description=request.POST['description'],
                ending_reminder=request.POST['ending_reminder'],
                customer_name=request.POST['customer_name'],
                customer_email=request.POST['customer_email'],
                customer_phone=request.POST['customer_phone'],
                end_date=end_date,
            )
            async_task(send_subscription_confirmation_email, subscription.id)
            return redirect('subscriptions')
            
        return redirect('subscriptions')
    except Employee.DoesNotExist:
        return redirect('dashboard')
