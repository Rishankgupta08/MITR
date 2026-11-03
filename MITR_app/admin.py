from django.contrib import admin

# Register your models here.from django.contrib import admin
from .models import CustomUser, Employee, Subscription, Task
admin.site.register(CustomUser)
admin.site.register(Subscription)
admin.site.register(Employee)
admin.site.register(Task)
