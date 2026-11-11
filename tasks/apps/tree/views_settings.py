"""The settings: a page for each section, under a second-level menu."""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DefaultBoardForm, HabitKeywordsForm, MapProviderForm, UserForm
from .models import Profile
from .views_sharing import board_sharing_panels


@dataclass(frozen=True)
class Section:
    """A page of settings: the route it is at, what the menu and the page
    call it, and what the page says it is for."""

    url_name: str
    title: str
    description: str

    @property
    def template(self):
        return f"tree/settings/{self.url_name.removeprefix('settings-')}.html"


PROFILE = Section("settings-profile", "Profile", "Your name.")
DEVICES = Section(
    "settings-devices",
    "Devices",
    "The phones and scripts that are logged in as you.",
)
BOARDS = Section(
    "settings-boards",
    "Boards",
    "The board you start on, and the boards you work on with others.",
)
HABITS = Section(
    "settings-habits", "Habits", "The habits that show on your tracking pages."
)
MAPS = Section("settings-maps", "Maps", "Where a pin on a map opens.")

# The second-level menu: titled groups of sections, in the order shown.
MENU = (
    ("Account", (PROFILE, DEVICES)),
    ("Preferences", (BOARDS, HABITS, MAPS)),
)


def _profile(user):
    """``user``'s profile; one not saved yet when they have none."""
    try:
        return Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return Profile(user=user)


def _posted(request):
    """What a form is bound to: the POST, or nothing when the page is read."""
    return request.POST if request.method == "POST" else None


def _page(request, section, **context):
    return render(
        request,
        section.template,
        {"settings_menu": MENU, "section": section, **context},
    )


def _saved(request, section):
    messages.success(request, f"{section.title} saved.")
    return redirect(section.url_name)


@login_required
def index(request):
    """Settings open on the first section."""
    return redirect(MENU[0][1][0].url_name)


@login_required
def profile(request):
    form = UserForm(_posted(request), instance=request.user)
    if form.is_valid():
        form.save()
        return _saved(request, PROFILE)
    return _page(request, PROFILE, form=form)


@login_required
def devices(request):
    return _page(request, DEVICES, api_tokens=request.user.api_tokens.all())


@login_required
def boards(request):
    form = DefaultBoardForm(
        _posted(request), instance=_profile(request.user), user=request.user
    )
    if form.is_valid():
        form.save()
        return _saved(request, BOARDS)
    return _page(
        request, BOARDS, form=form, board_sharing=board_sharing_panels(request)
    )


@login_required
def habits(request):
    form = HabitKeywordsForm(
        _posted(request), instance=_profile(request.user), user=request.user
    )
    if form.is_valid():
        form.save()
        return _saved(request, HABITS)
    return _page(request, HABITS, form=form)


@login_required
def maps(request):
    form = MapProviderForm(_posted(request), instance=_profile(request.user))
    if form.is_valid():
        form.save()
        return _saved(request, MAPS)
    return _page(request, MAPS, form=form)
