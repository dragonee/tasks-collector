from django.contrib import admin
from .models import Board, Thread, Plan, Reflection

# Register your models here.

admin.site.register(Board)
admin.site.register(Thread)
admin.site.register(Plan)
admin.site.register(Reflection)
