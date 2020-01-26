from django import forms

from .models import Plan, Reflection

class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ('pub_date', 'thread')

class ReflectionForm(forms.ModelForm):
    class Meta:
        model = Reflection
        exclude = ('pub_date', 'thread')
