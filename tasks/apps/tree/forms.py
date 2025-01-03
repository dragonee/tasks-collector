from django import forms

from django.core.exceptions import ValidationError

from .models import Plan, Reflection, Observation, QuickNote, Thread, JournalAdded, Breakthrough, ProjectedOutcome

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
    
    journal = forms.ModelChoiceField(queryset=JournalAdded.objects.all(), required=False)
    # or
    published = forms.DateTimeField(required=False)
    thread = forms.ModelChoiceField(queryset=Thread.objects.all(), required=False)

    def clean_text(self):
        text = self.cleaned_data['text']

        if not text.startswith('!') and not text.startswith('#'):
            raise ValidationError('Habit line must start with ! or #')
        
        return text


    def clean(self):
        cleaned_data = super().clean()

        if not 'text' in cleaned_data:
            return cleaned_data

        if cleaned_data.get('journal') and not cleaned_data.get('published'):
            cleaned_data['published'] = cleaned_data['journal'].published
        
        if cleaned_data.get('journal') and not cleaned_data.get('thread'):
            cleaned_data['thread'] = cleaned_data['journal'].thread

        if not cleaned_data.get('published'):
            cleaned_data['published'] = timezone.now()
        
        if not cleaned_data.get('thread'):
            cleaned_data['thread'] = Thread.objects.get(name='Daily')
            
        try:
            cleaned_data['triplets'] = habits_line_to_habits_tracked(cleaned_data['text'])
        except ValueError as e:
            self.add_error('text', str(e))
        
        return cleaned_data


class OnlyTextSingleHabitTrackedForm(SingleHabitTrackedForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['journal'].widget = forms.HiddenInput()
        self.fields['published'].widget = forms.HiddenInput()
        self.fields['thread'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()

        triplets = cleaned_data.get('triplets')

        if not triplets:
            self.add_error('text', 'No habits found')
            return cleaned_data

        return cleaned_data

class BreakthroughForm(forms.ModelForm):
    class Meta:
        model = Breakthrough
        fields = ['areas_of_concern', 'theme']
        widgets = {
            'areas_of_concern': forms.Textarea(attrs={
                'rows': 1,
                'placeholder': 'My areas of concern...',
            }),
            'theme': forms.TextInput(attrs={
                'placeholder': 'My theme...',
            }),
        }


from decimal import Decimal
class DecimalSliderWidget(forms.NumberInput):
    input_type = 'range'

    def __init__(self, attrs=None):
        default_attrs = {'step': '1', 'min': '0', 'max': '100'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def to_python(self, value):
        if value is None:
            return Decimal(0)
        return Decimal(value)

    def format_value(self, value):
        if value is None:
            return 0
        return float(value)


class ProjectedOutcomeForm(forms.ModelForm):
    class Meta:
        model = ProjectedOutcome
        fields = ['name', 'resolved_by', 'description', 'success_criteria', 'confidence_level']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Add an objective...',
            }),
            'resolved_by': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': 'Date resolved...',
            }),
            'description': forms.Textarea(attrs={
                'rows': 1,
                'placeholder': 'Describe the objective...',
            }),
            'success_criteria': forms.Textarea(attrs={
                'rows': 1,
                'placeholder': 'Describe the success criteria...',
            }),
            'confidence_level': DecimalSliderWidget(),
        }
