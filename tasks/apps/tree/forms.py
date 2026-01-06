from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import (
    Breakthrough,
    JournalAdded,
    JournalTag,
    Observation,
    Plan,
    Profile,
    ProjectedOutcome,
    QuickNote,
    Reflection,
    Thread,
)

User = get_user_model()

from django.utils import timezone

from .services.journalling import habits_line_to_habits_tracked


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ("pub_date", "thread")


class ReflectionForm(forms.ModelForm):
    class Meta:
        model = Reflection
        exclude = ("pub_date", "thread")


class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = [
            "situation",
            "interpretation",
            "approach",
            "pub_date",
            "type",
            "thread",
        ]


class QuickNoteForm(forms.ModelForm):
    class Meta:
        model = QuickNote
        fields = ["note"]


class QuickContentForm(forms.Form):
    CONTENT_TYPE_CHOICES = [
        ("quick_note", "Quick Note"),
        ("task", "Task to Do"),
        ("plan_focus", "Plan Focus"),
    ]

    content_type = forms.ChoiceField(
        choices=CONTENT_TYPE_CHOICES,
        initial="quick_note",
        widget=forms.Select(attrs={"id": "content-type-selector"}),
    )

    content = forms.CharField(
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Enter your content..."}
        ),
        max_length=1000,
    )

    focus_timeframe = forms.ChoiceField(
        choices=[
            ("today", "Today"),
            ("tomorrow", "Tomorrow"),
            ("this_week", "This Week"),
        ],
        initial="today",
        required=False,
        widget=forms.Select(attrs={"id": "focus-timeframe"}),
    )


class SingleHabitTrackedForm(forms.Form):
    text = forms.CharField(max_length=255)

    journal = forms.ModelChoiceField(
        queryset=JournalAdded.objects.all(), required=False
    )
    # or
    published = forms.DateTimeField(required=False)
    thread = forms.ModelChoiceField(queryset=Thread.objects.all(), required=False)

    def clean_text(self):
        text = self.cleaned_data["text"]

        if not text.startswith("!") and not text.startswith("#"):
            raise ValidationError("Habit line must start with ! or #")

        return text

    def clean(self):
        cleaned_data = super().clean()

        if not "text" in cleaned_data:
            return cleaned_data

        if cleaned_data.get("journal") and not cleaned_data.get("published"):
            cleaned_data["published"] = cleaned_data["journal"].published

        if cleaned_data.get("journal") and not cleaned_data.get("thread"):
            cleaned_data["thread"] = cleaned_data["journal"].thread

        if not cleaned_data.get("published"):
            cleaned_data["published"] = timezone.now()

        if not cleaned_data.get("thread"):
            cleaned_data["thread"] = Thread.objects.get(name="Daily")

        try:
            cleaned_data["triplets"] = habits_line_to_habits_tracked(
                cleaned_data["text"]
            )
        except ValueError as e:
            self.add_error("text", str(e))

        return cleaned_data


class OnlyTextSingleHabitTrackedForm(SingleHabitTrackedForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["journal"].widget = forms.HiddenInput()
        self.fields["published"].widget = forms.HiddenInput()
        self.fields["thread"].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()

        triplets = cleaned_data.get("triplets")

        if not triplets:
            self.add_error("text", "No habits found")
            return cleaned_data

        return cleaned_data


class BreakthroughForm(forms.ModelForm):
    class Meta:
        model = Breakthrough
        fields = ["areas_of_concern", "theme"]
        widgets = {
            "areas_of_concern": forms.Textarea(
                attrs={
                    "rows": 1,
                    "placeholder": "My areas of concern...",
                }
            ),
            "theme": forms.TextInput(
                attrs={
                    "placeholder": "My theme...",
                }
            ),
        }


from decimal import Decimal


class DecimalSliderWidget(forms.NumberInput):
    input_type = "range"

    def __init__(self, attrs=None):
        default_attrs = {"step": "1", "min": "0", "max": "100"}
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
        fields = [
            "name",
            "resolved_by",
            "description",
            "success_criteria",
            "confidence_level",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Add an objective...",
                }
            ),
            "resolved_by": forms.DateInput(
                attrs={
                    "type": "date",
                    "placeholder": "Date resolved...",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 1,
                    "placeholder": "Describe the objective...",
                }
            ),
            "success_criteria": forms.Textarea(
                attrs={
                    "rows": 1,
                    "placeholder": "Describe the success criteria...",
                }
            ),
            "confidence_level": DecimalSliderWidget(),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["default_board_thread", "habit_keywords"]
        widgets = {
            "default_board_thread": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "habit_keywords": forms.CheckboxSelectMultiple(),
        }


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "First name...",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Last name...",
                }
            ),
        }


class JournalAddedForm(forms.ModelForm):
    # Handle tags manually - use single select for tags
    tag = forms.ModelChoiceField(
        queryset=JournalTag.objects.all(),
        required=False,
        empty_label="Select a tag (optional)",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
        label="Tag",
    )

    class Meta:
        model = JournalAdded
        fields = ["comment", "thread"]
        widgets = {
            "comment": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Enter your journal entry...\n\nYou can use:\n- [x] for good things\n- [~] for things to improve\n- [^] for best practices\n- #habit_name or !habit_name to track habits",
                }
            ),
            "thread": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make thread required and remove empty option
        self.fields["thread"].required = True
        self.fields["thread"].empty_label = None

        # Set default thread to 'Daily' if not provided
        if not self.instance.pk and "thread" not in self.initial:
            try:
                daily_thread = Thread.objects.get(name="Daily")
                self.initial["thread"] = daily_thread.id
            except Thread.DoesNotExist:
                pass

        # Load existing tag if editing (just the first one if multiple exist)
        if self.instance.pk:
            existing_tag = self.instance.tags.first()
            if existing_tag:
                self.initial["tag"] = existing_tag.id

    def save(self, commit=True):
        # Set published to now if not set
        from django.utils import timezone

        instance = super().save(commit=False)
        if not instance.published:
            instance.published = timezone.now()

        if commit:
            instance.save()
            # Save the selected tag
            selected_tag = self.cleaned_data.get("tag")
            if selected_tag:
                instance.tags.set([selected_tag])
            else:
                instance.tags.clear()

        return instance
