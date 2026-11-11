from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_register')
        if not request.user.is_superuser:
            messages.error(request, 'Access denied. Admin only.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def coordinator_or_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_register')
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        try:
            from MITR_app.models import Employee
            emp = (
                Employee.objects.filter(user=request.user).first()
                or Employee.objects.filter(email__iexact=request.user.email).first()
            )
            if emp and emp.coordinator:
                return view_func(request, *args, **kwargs)
        except Exception:
            pass
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    return wrapper

