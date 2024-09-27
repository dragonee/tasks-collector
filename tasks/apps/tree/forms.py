from django import forms

from django.core.exceptions import ValidationError

from .models import Plan, Reflection, Observation, QuickNote, Thread

from .habits import habits_line_to_habits_tracked

from django.utils import timezone

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

class QuickNoteForm(forms.ModelForm):
    class Meta:
        model = QuickNote
        fields = [
            "note"
        ]

class SingleHabitTrackedForm(forms.Form):
    text = forms.CharField(max_length=255)
    
    published = forms.DateTimeField(required=False)
    
    thread = forms.ModelChoiceField(queryset=Thread.objects.all(), required=False)

    def clean_text(self):
        text = self.cleaned_data['text']

        if not text.startswith('!') and not text.startswith('#'):
            raise ValidationError('Habit line must start with ! or #')
        
        return text


    def clean(self):
        cleaned_data = super().clean()

        if not cleaned_data.get('published'):
            cleaned_data['published'] = timezone.now()
        
        if not cleaned_data.get('thread'):
            cleaned_data['thread'] = Thread.objects.get(name='Daily')

        try:
            cleaned_data['triplets'] = habits_line_to_habits_tracked(cleaned_data['text'])
        except ValueError as e:
            self.add_error('text', str(e))
        
        return cleaned_data
