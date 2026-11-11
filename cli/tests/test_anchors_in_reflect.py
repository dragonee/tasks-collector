"""`tc reflect` for a week or a month: the dump's task lines carry anchors,
and a line ticked in the editor goes on to the journal with its anchor."""

from datetime import date

from tasks_collector_tools.models import Plan, Reflection, Result
from tasks_collector_tools.reflect import ticked_lines
from tasks_collector_tools.reflectiondump import ResultAggregator

DAY = date(2026, 11, 11)


def result(good="", better="", best="", focus=None):
    return Result(
        date=DAY,
        events=[],
        plan=Plan(id=1, focus=focus, pub_date=DAY) if focus else None,
        reflection=Reflection(id=1, good=good, better=better, best=best, pub_date=DAY),
    )


def test_the_dump_lists_a_tasks_line_with_its_anchor():
    aggregator = ResultAggregator(
        [
            result(
                good="Called them ^t91bd0a44\nslept well", focus="call bank ^t91bd0a44"
            )
        ]
    )

    assert aggregator.get_reflection_context()["good"] == (
        "- [ ] Called them ^t91bd0a44\n- [ ] slept well"
    )
    assert aggregator.get_plan_context()["focus"] == "- [ ] call bank ^t91bd0a44"


def test_a_ticked_line_keeps_its_anchor_however_it_is_reworded():
    edited = [
        "# Reflection from 9 November (Monday) to 15 November (Sunday)\n",
        "- [^] Sorted the loan at last ^t91bd0a44\n",
        "- [ ] slept well\n",
        "- [x] #run in the rain\n",
        "\n",
        "# Plans\n",
        "- [~] write report ^taaaaaaaa  \n",
        "# Journals\n",
        "- [x] quoted from a journal ^tbbbbbbbb\n",
    ]

    assert ticked_lines(edited) == (
        "- [^] Sorted the loan at last ^t91bd0a44\n"
        "- [x] run in the rain\n"
        "- [~] write report ^taaaaaaaa\n"
    )
