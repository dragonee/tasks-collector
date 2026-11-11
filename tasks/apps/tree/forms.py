from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import (
    Breakthrough,
    HabitKeyword,
    JournalAdded,
    JournalTag,
    Observation,
    Plan,
    Profile,
    ProjectedOutcome,
    Reflection,
    Thread,
)

User = get_user_model()

from django.utils import timezone

from .services.journalling import habits_line_to_habits_tracked


class UserThreadFormMixin:
    """Offers only the threads of ``user`` (a required keyword argument) in
    the ``thread_field`` select; with no user there is nothing to choose."""

    thread_field = "thread"

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields[self.thread_field].queryset = (
            Thread.objects.for_user(user) if user is not None else Thread.objects.none()
        )
        # Forms that point at a journal entry may only point at the user's.
        if "journal" in self.fields:
            self.fields["journal"].queryset = (
                JournalAdded.objects.owned_by(user)
                if user is not None
                else JournalAdded.objects.none()
            )


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ("pub_date", "thread")


class ReflectionForm(forms.ModelForm):
    class Meta:
        model = Reflection
        exclude = ("pub_date", "thread")


class ObservationForm(UserThreadFormMixin, forms.ModelForm):
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


class InsightForm(forms.Form):
    situation = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10}),
        required=False,
    )
    approach = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10}),
        required=True,
    )


class SingleHabitTrackedForm(UserThreadFormMixin, forms.Form):
    text = forms.CharField(max_length=255)

    journal = forms.ModelChoiceField(
        queryset=JournalAdded.objects.all(), required=False
    )
    # or
    published = forms.DateTimeField(required=False)
    # Limited to the user's threads by UserThreadFormMixin.
    thread = forms.ModelChoiceField(queryset=Thread.objects.none(), required=False)

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
            cleaned_data["thread"] = Thread.objects.daily(self.user)

        try:
            cleaned_data["triplets"] = habits_line_to_habits_tracked(
                cleaned_data["text"], self.user
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


class ProjectedOutcomeEvolvedForm(forms.Form):
    note = forms.CharField(
        max_length=512,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Add a note about this outcome...",
            }
        ),
    )


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


class ProfileForm(UserThreadFormMixin, forms.ModelForm):
    thread_field = "default_board_thread"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["habit_keywords"].queryset = HabitKeyword.objects.filter(
            user=self.user
        ).select_related("habit")
        # Any board the user may change can be their default: their own and
        # the boards shared with them.
        board_field = self.fields["default_board_thread"]
        board_field.queryset = (
            Thread.objects.board_editable_by(self.user).select_related("user")
            if self.user is not None
            else Thread.objects.none()
        )
        board_field.label_from_instance = self._board_label

    def _board_label(self, thread):
        if thread.user_id == self.user.pk:
            return thread.name
        return f"{thread.name} (shared by {thread.user.username})"

    class Meta:
        model = Profile
        fields = ["default_board_thread", "map_provider", "habit_keywords"]
        widgets = {
            "default_board_thread": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "map_provider": forms.Select(
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


class JournalTagNameForm(forms.Form):
    """One of ``user``'s journal tags, by name: the one so named (in any case)
    or slugged, or else a new one. How a user makes their tags."""

    # Slugs the diary's URLs already take: a tag page there is unreachable.
    RESERVED_SLUGS = {"add"}

    name = forms.CharField(
        max_length=255,
        label="Tag",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Tag name",
                "list": "journal-tags",
                "autocomplete": "off",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        slug = slugify(name)
        if not slug:
            raise ValidationError("A tag name needs a letter or a digit.")
        if slug in self.RESERVED_SLUGS:
            raise ValidationError(f"“{name}” can't be a tag name.")
        self.slug = slug
        return name

    def tag(self):
        name = self.cleaned_data["name"]
        tags = JournalTag.objects.filter(user=self.user)
        existing = tags.filter(name__iexact=name).first()
        if existing is not None:
            return existing
        tag, _ = JournalTag.objects.get_or_create(
            user=self.user, slug=self.slug, defaults={"name": name}
        )
        return tag


class JournalAddedForm(UserThreadFormMixin, forms.ModelForm):
    # Handle tags manually - use single select for tags
    tag = forms.ModelChoiceField(
        queryset=JournalTag.objects.none(),
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

        # Set default thread to the user's 'Daily' if not provided
        if not self.instance.pk and "thread" not in self.initial:
            daily_thread = (
                self.fields["thread"].queryset.filter(name=Thread.DAILY).first()
            )
            if daily_thread is not None:
                self.initial["thread"] = daily_thread.id

        # Tags are per user: offer only the user's own.
        self.fields["tag"].queryset = (
            JournalTag.objects.filter(user=self.user)
            if self.user is not None
            else JournalTag.objects.none()
        )

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
