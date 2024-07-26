from django import forms

from django.core.exceptions import ValidationError

from .models import Plan, Reflection, Observation

class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ('pub_date', 'thread')

class ReflectionForm(forms.ModelForm):
    class Meta:
        model = Reflection
        exclude = ('pub_date', 'thread')

class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = [
            "situation", "interpretation", "approach", "pub_date", "type", "thread"
        ]