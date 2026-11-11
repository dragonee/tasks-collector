# Tasks Collector Tools

These tools add CLI support to the [Tasks Collector](https://github.com/dragonee/tasks-collector) application.

## Installation

The project is managed with [uv](https://docs.astral.sh/uv/). To put the `tc` command on your `PATH`:

```
uv tool install ./cli
```

After pulling changes, run `uv tool install --reinstall ./cli` (or install with `--editable` to have `tc` follow the working tree).

To work on the tools, run `uv sync` in this directory and call it with `uv run`, e.g. `uv run tc journal`.
The tests run with `uv run --with pytest pytest tests`.

## All-in-one

Everything is a subcommand of `tc`. A word written as `obs[ervation]` can be shortened down to `obs`.

### tc (2.1.0)

```
usage: tc [--config FILE] [COMMAND] [ARGS ...]

Command line for the Tasks Collector.

commands:
  tasks               Connect to the Tasks Collector.
  obs[ervation]       Add an observation.
  obs[ervation] dump  Dump observations to markdown files.
  upd[ate]            Add update to an observation.
  jou[rnal]           Add journal entry.
  trip jou[rnal]      Add journal entry to the current trip.
  hab[its]            Track habits daily or list them.
  events dump         Dump daily events to markdown.
  reflect             Reflect on a day, week or month.
  reflect dump        Dump reflections and journals to markdown.
  today               Print today's reflection, plan, habits, observations and journals.
  board dump          Dump a board to markdown.
  whoami              Say which server tc talks to, and as whom.

Without a command, tc runs `tasks`.
Run `tc COMMAND --help` for the options of a command.

tc reads /etc/tasks-collector.ini, ~/.tasks-collector.ini and
./tasks-collector.ini, a later one overriding what the ones before it say.
--config FILE (or TC_CONFIG=FILE) reads that file alone. `tc whoami` says
which were read, and who the server takes tc for.
```

### tc tasks (2.1.0)

```
usage: tc tasks [-h] [--version] [--thread THREAD]

Connect to the Tasks Collector.

By default, a line is added as an unscheduled task to the board of the thread
from your profile.
By prefixing a line with `!` or `#`, it will be added to the Habit Tracker instead.

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  --thread THREAD  Use specific thread.

Available commands:
  observation
  olist
  habits
  hlist
  oedit
  edit
  journal
  trip
  tjournal
  tripjournal
  thought
  update
  help
  clear
  wtf
  nove
  reflect
  thread
  stats
  focus

Quit by pressing Ctrl+D or Ctrl+C.
```

## Journalling

### tc journal (2.1.0)

```
usage: tc journal [-h] [--version] [-d DATE] [-T TAGS] [-Y] [-t THREAD]
                  [-S ID] [--active-story] [--current-trip] [-f FILE] [-F]
                  [--no-edit] [--dry-run] [--json] [-L]

Add journal entry.

The template lists today's plans above the comment. Tick a task there to
complete it: [x], or [~] / [^] for better / best. The ^t... that ends its
line says which task it is, so the line can be reworded; keep the ^t...

Without an editor (a script, an assistant): --no-edit -f FILE sends FILE as
the comment, and --dry-run shows what the server would make of it first.
An entry is sent with a key of its own, so one queued and sent again after
a failed connection is added once.

options:
  -h, --help           show this help message and exit
  --version            show program's version number and exit
  -d, --date DATE      Use this date for the journal entry.
  -T, --tags TAGS      Add these tags to the journal entry.
  -Y, --yesterday      Use yesterday's date for the journal entry.
  -t, --thread THREAD  Use this thread [default: Daily].
  -S, --story ID       Attach this journal entry to story ID.
  --active-story       Attach to the currently active story (overridden by
                       --story).
  --current-trip       Attach to the saved current trip (see the `trip`
                       command).
  -f, --file FILE      Start the comment with this file (- for standard
                       input).
  -F, --force          Send even if content is unchanged from template.
  --no-edit            Don't open the editor: send the comment from -f as it
                       is.
  --dry-run            Show what sending would do (reflection lines, habits,
                       tasks completed), and send nothing.
  --json               With --dry-run, print the server's answer as JSON.
  -L, --today          List journals from today.
```

### tc trip journal (2.1.0)

```
usage: tc trip journal [-h] [--version] [-d DATE] [-T TAGS] [-Y] [-t THREAD]
                       [-S ID] [--active-story] [--current-trip] [-f FILE]
                       [-F] [--no-edit] [--dry-run] [--json] [-L]

Add journal entry.

The template lists today's plans above the comment. Tick a task there to
complete it: [x], or [~] / [^] for better / best. The ^t... that ends its
line says which task it is, so the line can be reworded; keep the ^t...

Without an editor (a script, an assistant): --no-edit -f FILE sends FILE as
the comment, and --dry-run shows what the server would make of it first.
An entry is sent with a key of its own, so one queued and sent again after
a failed connection is added once.

options:
  -h, --help           show this help message and exit
  --version            show program's version number and exit
  -d, --date DATE      Use this date for the journal entry.
  -T, --tags TAGS      Add these tags to the journal entry.
  -Y, --yesterday      Use yesterday's date for the journal entry.
  -t, --thread THREAD  Use this thread [default: Daily].
  -S, --story ID       Attach this journal entry to story ID.
  --active-story       Attach to the currently active story (overridden by
                       --story).
  --current-trip       Attach to the saved current trip (see the `trip`
                       command).
  -f, --file FILE      Start the comment with this file (- for standard
                       input).
  -F, --force          Send even if content is unchanged from template.
  --no-edit            Don't open the editor: send the comment from -f as it
                       is.
  --dry-run            Show what sending would do (reflection lines, habits,
                       tasks completed), and send nothing.
  --json               With --dry-run, print the server's answer as JSON.
  -L, --today          List journals from today.
```

`tc today` is `tc reflect dump` of one day: today, unless `-d DATE` says another.

### tc today (2.1.0)

```
usage: tc today [-h] [--version] [-T THREAD] [--skip-journals] [--no-summary]
                [--no-titles] [--no-habits] [--no-observations]
                [--prefix PREFIX] [--anchors] [-d DATE_FROM] [-D DATE_TO]
                [--year YEAR] [-M] [--json]

Dump reflections and journals to markdown.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -T, --thread THREAD   Dump specific thread.
  --skip-journals       Skip journals.
  --no-summary          Skip Good/Better/Best summary.
  --no-titles           Skip section headers ("# Reflection", "# Journals",
                        etc).
  --no-habits           Skip habits section.
  --no-observations     Skip observations section.
  --prefix PREFIX       Prefix each line of journal entries with PREFIX.
  --anchors             End each task's line with its anchor (^t...), for text
                        that is sent back.
  -d, --from DATE_FROM  Dump from specific date.
  -D, --to DATE_TO      Dump to specific date.
  --year YEAR           Dump specific year.
  -M, --missing         Print only dates without reflection entries.
  --json                Print JSON in place of markdown: day by day, the
                        reflection and plan line by line (each line's text and
                        its task's anchor), habits, observations and journals.
```

## Observations

### tc observation (2.1.0)

```
usage: tc observation [-h] [--version] [-l] [-a] [-n N] [-c N] [-u]
                      [--date DATE] [-s] [--thread THREAD] [--type TYPE]
                      [-f FILE] [--no-edit]

Add an observation.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -l, --list            List last couple of observations.
  -a, --all             With -l, show all observations (not just mine).
  -n, --number N        With -l, show N observations [default: 20].
  -c, --chars N         With -l, show N chars of the situation [default: 100].
  -u, --sort-by-update  With -l, sort by last event time (most recent first).
  --date DATE           Use specific date.
  -s, --save            Save as default for updates.
  --thread THREAD       Use specific thread [default: big-picture].
  --type TYPE           Choose type [default: observation].
  -f, --file FILE       Start from this file, the template filled in (- for
                        standard input). Its > Date, > Thread and > Type lines
                        may be left out.
  --no-edit             Don't open the editor: send the file from -f as it is.
```

### tc update (2.1.0)

```
usage: tc update [-h] [--version] [-f FILE] [--no-edit] [ID]

Add update to an observation.

positional arguments:
  ID               Observation to update [default: the one saved with `tc
                   observation --save`].

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  -f, --file FILE  Start the comment with this file (- for standard input).
  --no-edit        Don't open the editor: send the comment from -f as it is.
```

## Habits

### tc habits (2.1.0)

```
usage: tc habits [-h] [--version] [-a] [-d DATE] [-Y] [-l] [--json]
                 [-o FILENAME] [-t LINE]

Track habits daily or list them.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -a, --all             Track all habits.
  -d, --date DATE       Use this date for tracking habits.
  -Y, --yesterday       Set the date to yesterday.
  -l, --list            List habits.
  --json                With -l, list each habit's name, slug, description and
                        keywords as JSON.
  -o, --output FILENAME
                        If listing, output to file [default: -].
  -t, --track LINE      Track the habits LINE names, without asking: "#workout
                        100 push-ups", "!alcohol". May be given more than
                        once.
```

## Tools for periodical reflections

TODO: write up process on how to do a periodical reflection.

### tc reflect (2.1.0)

```
usage: tc reflect [-h] [--version] [-d DATE] [-w] [-m] [-y] [-M]

Reflect on a day, week or month.

For a week or a month the editor lists the reflections and plans of its days
(or weeks). Tick a line to take it into the reflection: [x], or [~] / [^] for
better / best. The ^t... that ends a task's line says which task it is, so
the line can be reworded; keep the ^t...

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  -d, --date DATE  Use this date for reflection.
  -w, --week       Use this week for reflection.
  -m, --month      Use this month for reflection.
  -y, --yesterday  Use yesterday for reflection.
  -M, --missing    Fill in missing journal entries for the date range.
```

### tc observation dump (2.1.0)

```
usage: tc observation dump [-h] [--version] [--open] [--closed] [-d DATE_FROM]
                           [-D DATE_TO] [-f] [--stream ID] [--year YEAR]
                           PATH

Dump observations to markdown files.

positional arguments:
  PATH                  Directory to write the files to.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --open                Dump only open observations.
  --closed              Dump only closed observations.
  -d, --from DATE_FROM  Dump from specific date.
  -D, --to DATE_TO      Dump to specific date.
  -f, --force           Overwrite existing files.
  --stream ID           Dump object with specific Event Stream ID.
  --year YEAR           Dump specific year.
```

### tc board dump (2.1.0)

```
usage: tc board dump [-h] [--version] [--thread THREAD] [--enumerate]

Dump a board to markdown.

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  --thread THREAD  Use specific thread [default: big-picture].
  --enumerate      Add numeric enumeration to points (e.g. 1.2.4.)
```

### tc reflect dump (2.1.0)

```
usage: tc reflect dump [-h] [--version] [-T THREAD] [--skip-journals]
                       [--no-summary] [--no-titles] [--no-habits]
                       [--no-observations] [--prefix PREFIX] [--anchors]
                       [-d DATE_FROM] [-D DATE_TO] [--year YEAR] [-M] [--json]

Dump reflections and journals to markdown.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -T, --thread THREAD   Dump specific thread.
  --skip-journals       Skip journals.
  --no-summary          Skip Good/Better/Best summary.
  --no-titles           Skip section headers ("# Reflection", "# Journals",
                        etc).
  --no-habits           Skip habits section.
  --no-observations     Skip observations section.
  --prefix PREFIX       Prefix each line of journal entries with PREFIX.
  --anchors             End each task's line with its anchor (^t...), for text
                        that is sent back.
  -d, --from DATE_FROM  Dump from specific date.
  -D, --to DATE_TO      Dump to specific date.
  --year YEAR           Dump specific year.
  -M, --missing         Print only dates without reflection entries.
  --json                Print JSON in place of markdown: day by day, the
                        reflection and plan line by line (each line's text and
                        its task's anchor), habits, observations and journals.
```

### tc events dump (2.1.0)

```
usage: tc events dump [-h] [--version] [-d DATE_FROM] [-D DATE_TO]
                      [--year YEAR] [-T THREAD] [--no-plans]
                      [--no-reflections] [--json]
                      [PATH]

Dump daily events to markdown.

positional arguments:
  PATH                  Write one file per day to this directory instead of
                        printing.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -d, --from DATE_FROM  Dump from specific date.
  -D, --to DATE_TO      Dump to specific date.
  --year YEAR           Dump specific year.
  -T, --thread THREAD   Dump specific thread.
  --no-plans            Exclude plans from output.
  --no-reflections      Exclude reflections from output.
  --json                Print the days as the server gives them, as JSON, in
                        place of markdown.
```

## For scripts and assistants

What opens an editor also runs without one, and what prints markdown also prints JSON:

- `tc journal --no-edit -f FILE` sends FILE (`-f -`: standard input) as the comment. `--dry-run` asks the server what the entry would do (its reflection lines, the habits it tracks, the tasks it completes) and sends nothing.
- `tc observation --no-edit -f FILE` sends a filled-in observation template, and `tc update ID --no-edit -f FILE` an update.
- `tc habits --track "#workout 100 push-ups"` tracks habits without asking, and `tc habits --list --json` lists them with their keywords.
- `tc reflect dump --json` (`tc today --json` for today) and `tc events dump --json` print the days as JSON. A span is fetched in one request per year.

Each journal entry, observation, update and tracked habit is sent with a key of its own: one queued after a failed connection and sent again is added once.

A token can stand in for the password. Issue one in the account settings (Devices), ticking *Can only read* for one that changes nothing, and put it under `[Tasks]` as `token = …`. A token that can only read may still ask for a `--dry-run`. `tc --config FILE` (or `TC_CONFIG=FILE`) reads that configuration file alone, and `tc whoami` says which files were read and who the server takes tc for.

### tc whoami (2.1.0)

```
usage: tc whoami [-h] [--version] [--json]

Say which server tc talks to, and as whom.

It names the configuration files read (a later one overrides what the ones
before it say), the server's address, and who the server takes tc for: the
user, and the token when tc sends one, with whether it can only read.
Exits with 1 when the server doesn't take it for anyone.

options:
  -h, --help  show this help message and exit
  --version   show program's version number and exit
  --json      Print it as JSON.
```
