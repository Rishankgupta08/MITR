# Create your views here.
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
import os
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

def get_available_companies(default_company='NTPL'):
    companies = set()
    if default_company:
        companies.add(default_company)
    for c in User.objects.exclude(company='').values_list('company', flat=True).distinct():
        if c:
            companies.add(c)
    for c in Employee.objects.exclude(company='').exclude(company='TO_BE_ASSIGNED').values_list('company', flat=True).distinct():
        if c:
            companies.add(c)
    for c in Subscription.objects.exclude(company='').values_list('company', flat=True).distinct():
        if c:
            companies.add(c)
    return sorted(companies)


def get_active_company(request):
    user_company = getattr(request.user, 'company', '') or 'NTPL'
    if not request.user.is_superuser:
        return user_company, [user_company]
    companies = get_available_companies(user_company)
    req_company = request.GET.get('company')
    if req_company and req_company in companies:
        request.session['admin_selected_company'] = req_company
        return req_company, companies
    saved = request.session.get('admin_selected_company')
    if saved and saved in companies:
        return saved, companies
    return user_company, companies


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
    company, available_companies = get_active_company(request)

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
    if is_admin:
        form.fields['employee'].queryset = Employee.objects.filter(company=company)
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
        'selected_company': company,
        'available_companies': available_companies,
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

    # Strict tenant & role isolation on task details/actions
    if not is_admin:
        if is_coordinator:
            if not task.employee or task.employee.company != user.company:
                messages.error(request, 'Access denied. You cannot access another company\'s task.')
                return redirect('dashboard')
        else:
            if not employee or task.employee_id != employee.id:
                messages.error(request, 'Access denied. You can only view your own tasks.')
                return redirect('dashboard')

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
    from django.db.models import Q
    company, available_companies = get_active_company(request)
    user_email = request.user
    is_superuser = user_email.is_superuser
    
    employee = None
    is_employee = False

    if not is_superuser:
        try:
            employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
            is_employee = True
            if not employee.coordinator:
                return redirect('dashboard')
        except Employee.DoesNotExist:
            employee = None
    
    employees = Employee.objects.filter(company=company)
    search_query = request.GET.get('search', '').strip()
    if search_query:
        employees = employees.filter(
            Q(name__icontains=search_query) | Q(email__icontains=search_query)
        )
    return render(request, 'employee_list.html', {
        'employees': employees,
        'is_employee': is_employee,
        'is_superuser': is_superuser,
        'employee': employee,
        'search_query': search_query,
        'selected_company': company,
        'available_companies': available_companies,
    })

 
@admin_required
def confirm_remove_employee(request, id):
    employee = get_object_or_404(Employee, id=id)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee removed successfully.')
        return redirect('employee_list')  # Redirect to the dashboard after deletion

    return render(request, 'confirm_remove_employee.html', {'employee': employee})

 
@coordinator_or_admin_required
def employee_progress(request, employee_id):
    from datetime import date

    # Tenant isolation: Coordinators can only view their own company's employees; Admin can view any company's employee
    if request.user.is_superuser:
        employee = get_object_or_404(Employee, id=employee_id)
    else:
        employee = get_object_or_404(Employee, id=employee_id, company=request.user.company)
    today = date.today()

    tasks = Task.objects.filter(employee=employee).order_by('-date_added')

    # Simple DB counts - no matplotlib needed
    total = tasks.count()
    completed = tasks.filter(completed=True).count()
    overdue = tasks.filter(completed=False, submission_date__lt=today).count()
    pending = tasks.filter(completed=False, submission_date__gte=today).count()

    context = {
        'employee': employee,
        'tasks': tasks,
        'today': today,
        'total': total,
        'completed': completed,
        'overdue': overdue,
        'pending': pending,
        'is_superuser': request.user.is_superuser,
        'coordinator': employee.coordinator,
    }
    return render(request, 'employee_progress.html', context)

 
def generate_summary(summary_date):
    if isinstance(summary_date, str):
        summary_date = datetime.strptime(summary_date, '%Y-%m-%d').date()
    elif isinstance(summary_date, datetime):
        summary_date = summary_date.date()

    start_date = timezone.make_aware(datetime.combine(summary_date, datetime.min.time())) if timezone.is_aware(timezone.now()) else datetime.combine(summary_date, datetime.min.time())
    end_date = timezone.make_aware(datetime.combine(summary_date, datetime.max.time())) if timezone.is_aware(timezone.now()) else datetime.combine(summary_date, datetime.max.time())

    created_tasks = Task.objects.filter(date_added__range=(start_date, end_date))
    completed_tasks = Task.objects.filter(completed=True, completed_date__range=(start_date, end_date))
    overdue_tasks = Task.objects.filter(submission_date__lt=summary_date, completed=False)

    summary = {
        'date': summary_date,
        'created_tasks': created_tasks,
        'completed_tasks': completed_tasks,
        'overdue_tasks': overdue_tasks,
    }

    return summary

def get_filtered_tasks(company, start_date=None,
                       end_date=None, status_filter=None):
    """
    Single source of truth for report queries.
    Always filters by company at DB level.
    """
    from django.db.models import Q
    from datetime import date

    # Base query — always scoped to company
    queryset = Task.objects.filter(
        employee__company=company
    )

    # Date range filter
    if start_date:
        queryset = queryset.filter(
            Q(date_added__date__gte=start_date) |
            Q(completed_date__date__gte=start_date)
        )
    if end_date:
        queryset = queryset.filter(
            Q(date_added__date__lte=end_date) |
            Q(submission_date__lte=end_date)
        )

    # Status filter at DB level (not Python)
    today = date.today()
    if status_filter == 'completed':
        queryset = queryset.filter(completed=True)
    elif status_filter == 'pending':
        queryset = queryset.filter(
            completed=False,
            submission_date__gte=today
        )
    elif status_filter == 'overdue':
        queryset = queryset.filter(
            completed=False,
            submission_date__lt=today
        )
    elif status_filter == 'completed_overdue':
        queryset = queryset.filter(
            completed=True,
            completed_date__date__gt=F('submission_date')
        )

    # Always ordered — never random
    return queryset.order_by('-date_added').distinct()

@coordinator_or_admin_required
def summary_report(request):
    user_email = request.user
    is_superuser = user_email.is_superuser
    company, available_companies = get_active_company(request)
    employee = None
    is_employee = False

    if not is_superuser:
        try:
            employee = (Employee.objects.filter(user=request.user).first() or Employee.objects.get(email__iexact=request.user.email))
            is_employee = True
            if not employee.coordinator:
                return redirect('dashboard')
        except Employee.DoesNotExist:
            employee = None
            print(f"No employee record found for user: {user_email}")

    selected_date_str = request.GET.get('date') or datetime.now().strftime('%Y-%m-%d')
    report_type = request.GET.get('report_type') or request.GET.get('filter', 'daily')
    status_filter = request.GET.get('status_filter') or request.GET.get('status', 'all')

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

    tasks = get_filtered_tasks(
        company=company,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
    )

    return render(request, 'summary_report.html', {
        'tasks': tasks,
        'all_tasks': tasks,
        'selected_date': selected_date,
        'report_type': report_type,
        'status_filter': status_filter,
        'is_employee': is_employee,
        'is_superuser': is_superuser,
        'employee': employee,
        'selected_company': company,
        'available_companies': available_companies,
    })

def remove_timezone_from_datetime(dt):
    """Remove timezone information from a datetime object."""
    if dt is not None:
        return dt.replace(tzinfo=None)
    return dt

@login_required
@coordinator_or_admin_required
def download_summary_report(request, date=None, report_type='daily', status_filter='all'):
    company, _ = get_active_company(request)
    date_str = date or request.GET.get('date') or datetime.now().strftime('%Y-%m-%d')
    report_type = request.GET.get('report_type') or request.GET.get('filter') or report_type
    status_filter = request.GET.get('status_filter') or request.GET.get('status') or status_filter
    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    if report_type == 'weekly':
        start_date = selected_date - timedelta(days=selected_date.weekday())
        end_date = start_date + timedelta(days=6)
    elif report_type == 'monthly':
        start_date = selected_date.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:  # Daily
        start_date = selected_date
        end_date = selected_date

    tasks = get_filtered_tasks(company, start_date, end_date, status_filter)

    # Create an in-memory output file for the new workbook.
    output = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    output['Content-Disposition'] = f'attachment; filename="summary_report_{date_str}_{report_type}_{status_filter}.xlsx"'

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
    for row_num, task in enumerate(tasks, start=1):
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

    from django.db.models import Q
    company, available_companies = get_active_company(request)
    subscriptions_list = Subscription.objects.filter(
        company=company
    ).order_by('-start_date')

    search_query = request.GET.get('search', '').strip()
    if search_query:
        subscriptions_list = subscriptions_list.filter(
            Q(customer_name__icontains=search_query) |
            Q(subscription_type__icontains=search_query) |
            Q(customer_email__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
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
            'employee': employee,
            'search_query': search_query,
            'selected_company': company,
            'available_companies': available_companies,
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
            'search_query': search_query,
            'selected_company': company,
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
            # Convert end_date string (YYYY-MM-DD or ISO YYYY-MM-DDTHH:MM) to aware datetime
            raw_end_date = request.POST['end_date']
            end_date = datetime.fromisoformat(raw_end_date)
            if 'T' not in raw_end_date and ' ' not in raw_end_date:
                end_date = end_date.replace(hour=23, minute=59, second=59)
            if timezone.is_naive(end_date):
                end_date = timezone.make_aware(end_date)
            
            subscription = Subscription.objects.create(
                subscription_type=request.POST['subscription_type'],
                description=request.POST['description'],
                ending_reminder=request.POST['ending_reminder'],
                customer_name=request.POST['customer_name'],
                customer_email=request.POST['customer_email'],
                customer_phone=request.POST['customer_phone'],
                end_date=end_date,
                company=get_active_company(request)[0],
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
            # Convert end_date string (YYYY-MM-DD or ISO YYYY-MM-DDTHH:MM) to aware datetime
            raw_end_date = request.POST['end_date']
            end_date = datetime.fromisoformat(raw_end_date)
            if 'T' not in raw_end_date and ' ' not in raw_end_date:
                end_date = end_date.replace(hour=23, minute=59, second=59)
            if timezone.is_naive(end_date):
                end_date = timezone.make_aware(end_date)
            
            subscription = Subscription.objects.create(
                subscription_type=request.POST['subscription_type'],
                description=request.POST['description'],
                ending_reminder=request.POST['ending_reminder'],
                customer_name=request.POST['customer_name'],
                customer_email=request.POST['customer_email'],
                customer_phone=request.POST['customer_phone'],
                end_date=end_date,
                company=request.user.company,
            )
            async_task(send_subscription_confirmation_email, subscription.id)
            return redirect('subscriptions')
            
        return redirect('subscriptions')
    except Employee.DoesNotExist:
        return redirect('dashboard')
