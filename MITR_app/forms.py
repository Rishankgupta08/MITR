from django import forms
from django.forms import ValidationError
from datetime import date, timedelta
from .models import CustomUser, Employee, Task
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

CustomUser = get_user_model()

class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    company = forms.CharField(max_length=100, required=True)

    class Meta:
        model = CustomUser
        fields = ['email', 'company', 'password1', 'password2']

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match. Please try again.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = str(uuid.uuid4())  # Generate a unique username
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class TaskForm(forms.ModelForm):

    def __init__(self, user=None, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        self.fields['overdue_reason'].initial = None
        self.fields['overdue_reason'].required = False
        if user and hasattr(user, 'company'):
            company = user.company
            #print(f"Filtering employees for company: {company}")
            employees = Employee.objects.filter(company=company)
            if employees.exists():
                self.fields['employee'].queryset = employees
            else:
                # If no employees found, display "No employees"
                self.fields['employee'].queryset = Employee.objects.none()      

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

    remind_every = forms.ChoiceField(choices=REMIND_CHOICES)
    submission_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    
    class Meta:
        model = Task
        fields = ['title', 'description', 'email', 'employee', 'remind_every', 'submission_date', 'client_company','client_phone_number','overdue_reason']
        widgets = {
              'employee': forms.Select(attrs={'class': 'form-control'}),
              'submission_date': forms.DateInput(attrs={'type': 'date'}),  # Add a class for styling if needed
          }
        
        employee = forms.ModelChoiceField(queryset=Employee.objects.none(), required=True)


    def clean_submission_date(self):
        submission_date = self.cleaned_data.get('submission_date')
        if submission_date < date.today():
            raise ValidationError('Submission date cannot be in the past.')
        return submission_date
    
    def clean(self):
        cleaned_data = super().clean()
        required_fields = ['title', 'description', 'email', 'employee', 'remind_every', 'submission_date', 'client_company', 'client_phone_number']
        # If task is overdue, make overdue_reason required
        if cleaned_data.get('submission_date') < date.today():
            required_fields.append('overdue_reason')
        
        missing_fields = [field for field in required_fields if not cleaned_data.get(field)]
        if missing_fields:
            print("these fields are missing",missing_fields)
            raise forms.ValidationError(f"The following fields are required: {', '.join(missing_fields)}")
        return cleaned_data

    # def clean(self):
    #     cleaned_data = super().clean()

    #     # Required fields for every task
    #     required_fields = [
    #         'title', 'description', 'email', 'employee',
    #         'remind_every', 'submission_date', 'client_company',
    #         'client_phone_number'
    #     ]

    #     # Get submission date and overdue reason from cleaned data
    #     submission_date = cleaned_data.get('submission_date')
    #     overdue_reason = cleaned_data.get('overdue_reason')

    #     # Check if the task is overdue and require overdue_reason if it is
    #     if submission_date and submission_date < date.today():
    #         # Check if overdue_reason is missing when required
    #         if not overdue_reason:
    #             self.add_error('overdue_reason', 'Reason for overdue is required if the task is overdue.')

    #     # Check for missing required fields
    #     missing_fields = [field for field in required_fields if not cleaned_data.get(field)]
    #     if missing_fields:
    #         print("these fields are missing", missing_fields)
    #         raise forms.ValidationError(f"The following fields are required: {', '.join(missing_fields)}")

    #     return cleaned_data
    
class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'email', 'phone_number']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(EmployeeForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        employee = super().save(commit=False)
        if self.user:
            employee.user = self.user
        if commit:
            employee.save()
        return employee
    
from django import forms

class DateForm(forms.Form):
    date = forms.DateField(widget=forms.SelectDateWidget)
