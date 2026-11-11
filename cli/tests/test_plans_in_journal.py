"""Plans in the journal template: task lines carry anchors, and a line ticked
in a plan section is sent with the comment."""

from types import SimpleNamespace

from tasks_collector_tools.journal import (
    format_plan,
    template_from_arguments,
    ticked_in_plans,
    with_ticked_lines,
)
from tasks_collector_tools.plans import Plan, anchored, task_line
from tasks_collector_tools.presenters import listize


def task(text, done=False, mark=None, anchor="91bd0a44"):
    return {"text": text, "done": done, "mark": mark, "anchor": anchor}


def plans(daily=(), weekly=(), monthly=()):
    return {
        "daily": Plan("2026-11-11", "Daily", list(daily)),
        "weekly": Plan("2026-11-15", "Weekly", list(weekly)),
        "monthly": Plan("2026-11-30", "big-picture", list(monthly)),
    }


def test_a_task_line_shows_how_it_was_done():
    assert task_line(task("a")) == "- [ ] a"
    assert task_line(task("a", done=True)) == "- [x] a"
    assert task_line(task("a", done=True, mark="~")) == "- [~] a"
    assert task_line(task("a", done=True, mark="^")) == "- [^] a"
    # A mark is how it was done; an open task has none to show.
    assert task_line(task("a", mark="~")) == "- [ ] a"


def test_anchors_only_where_text_is_sent_back():
    plan = Plan("2026-11-11", "Daily", [task("call bank")])

    assert str(plan) == "Focus: \n- [ ] call bank\n"
    assert plan.render(anchors=True) == "Focus: \n- [ ] call bank ^t91bd0a44\n"
    assert format_plan(plan, "Daily Plan") == (
        "# Daily Plan\nFocus: \n- [ ] call bank ^t91bd0a44\n"
    )


def test_a_plain_line_has_no_anchor():
    plain = task("written long ago", anchor=None)

    assert anchored("written long ago", plain) == "written long ago"
    assert task_line(plain, anchors=True) == "- [ ] written long ago"


def test_the_template_lists_the_plans_above_the_comment():
    arguments = SimpleNamespace(tags=None, thread="Daily", date=None, yesterday=False)

    template = template_from_arguments(
        arguments,
        plans(
            daily=[task("call bank")], weekly=[task("write report", anchor="aaaaaaaa")]
        ),
    )

    comment_at = template.index("# Comment")
    assert template.index("- [ ] call bank ^t91bd0a44") < comment_at
    assert template.index("- [ ] write report ^taaaaaaaa") < comment_at


def test_lines_ticked_in_the_plan_sections_are_found():
    made = plans(
        daily=[
            task("call bank", anchor="11111111"),
            task("Do x (2/3)", anchor="22222222"),
            task("done before", done=True, anchor="33333333"),
            task("left open", anchor="44444444"),
        ],
        weekly=[task("write report", anchor="55555555")],
    )
    edited = [
        "# Daily Plan\n",
        "Focus: \n",
        "- [x] call bank ^t11111111\n",
        "- [~] Did the second go of x ^t22222222\n",
        "- [x] done before ^t33333333\n",
        "- [ ] left open ^t44444444\n",
        "\n",
        "# Weekly Plan\n",
        "- [^] write report ^t55555555  \n",
        "- [x] typed in here, no task\n",
        "\n",
    ]

    assert ticked_in_plans(edited, made) == [
        "- [x] call bank ^t11111111",
        # Reworded: the anchor says which task.
        "- [~] Did the second go of x ^t22222222",
        "- [^] write report ^t55555555",
    ]


def test_nothing_ticked_changes_nothing():
    made = plans(daily=[task("call bank"), task("done", done=True, anchor="33333333")])
    untouched = made["daily"].render(anchors=True).splitlines(keepends=True)

    assert ticked_in_plans(untouched, made) == []
    assert with_ticked_lines("my day", []) == "my day"


def test_ticked_lines_go_before_the_comment():
    ticked = ["- [x] call bank ^t11111111"]

    assert with_ticked_lines("my day", ticked) == "- [x] call bank ^t11111111\nmy day"
    # Ticking alone is something to send.
    assert with_ticked_lines("", ticked) == "- [x] call bank ^t11111111"


def test_listize_takes_the_checkbox_off():
    assert listize("- [x] a\n- [ ] b\n- [~] c\n- d\ne", prefix="* ") == (
        "* a\n* b\n* c\n* d\n* e"
    )
