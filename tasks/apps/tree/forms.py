from django import forms

from django.core.exceptions import ValidationError

from .models import Plan, Reflection, EditableHabitsLine, Observation
from .habits import habits_line_to_habits_tracked

class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ('pub_date', 'thread')

class ReflectionForm(forms.ModelForm):
    class Meta:
        model = Reflection
        exclude = ('pub_date', 'thread')

class EditableHabitsLineForm(forms.ModelForm):
    class Meta:
        model = EditableHabitsLine
        exclude = ('pub_date', 'thread')
    
    def clean_line(self):
        print(self.cleaned_data, flush=True)

        try:
            print(habits_line_to_habits_tracked(self.cleaned_data['line']), flush=True)
        except ValueError as e:
            print(e, flush=True)
            raise ValidationError(str(e), code="invalid")
    
        return self.cleaned_data['line']

class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = [
            "situation", "interpretation", "approach", "pub_date", "type", "date_closed", "thread"
        ]