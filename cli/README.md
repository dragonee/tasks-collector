# Tasks Collector Tools

These tools add CLI support to the [Tasks Collector](https://github.com/dragonee/tasks-collector) application.

## Installation

The project is managed with [uv](https://docs.astral.sh/uv/). To put the `tc` command on your `PATH`:

```
uv tool install ./cli
```

After pulling changes, run `uv tool install --reinstall ./cli` (or install with `--editable` to have `tc` follow the working tree).

To work on the tools, run `uv sync` in this directory and call it with `uv run`, e.g. `uv run tc journal`.

## All-in-one

Everything is a subcommand of `tc`. A word written as `obs[ervation]` can be shortened down to `obs`.

### tc (2.0.0)

```
usage: tc [COMMAND] [ARGS ...]

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
  board dump          Dump a board to markdown.

Without a command, tc runs `tasks`.
Run `tc COMMAND --help` for the options of a command.
```

### tc tasks (2.0.0)

```
usage: tc tasks [-h] [--version] [--thread THREAD]

Connect to the Tasks Collector.

By default, tasks are added to the thread from your profile.
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

### tc journal (2.0.0)

```
usage: tc journal [-h] [--version] [-d DATE] [-T TAGS] [-Y] [-t THREAD]
                  [-S ID] [--active-story] [--current-trip] [-f FILE] [-F]
                  [-L]

Add journal entry.

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
  -f, --file FILE      Use this file instead of the generated template.
  -F, --force          Send even if content is unchanged from template.
  -L, --today          List journals from today.
```

### tc trip journal (2.0.0)

```
usage: tc trip journal [-h] [--version] [-d DATE] [-T TAGS] [-Y] [-t THREAD]
                       [-S ID] [--active-story] [--current-trip] [-f FILE]
                       [-F] [-L]

Add journal entry.

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
  -f, --file FILE      Use this file instead of the generated template.
  -F, --force          Send even if content is unchanged from template.
  -L, --today          List journals from today.
```

## Observations

### tc observation (2.0.0)

```
usage: tc observation [-h] [--version] [-l] [-a] [-n N] [-c N] [-u]
                      [--date DATE] [-s] [--thread THREAD] [--type TYPE]

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
```

### tc update (2.0.0)

```
usage: tc update [-h] [--version] [ID]

Add update to an observation.

positional arguments:
  ID          Observation to update [default: the one saved with `tc
              observation --save`].

options:
  -h, --help  show this help message and exit
  --version   show program's version number and exit
```

## Habits

### tc habits (2.0.0)

```
usage: tc habits [-h] [--version] [-a] [-d DATE] [-Y] [-l] [-o FILENAME]

Track habits daily or list them.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -a, --all             Track all habits.
  -d, --date DATE       Use this date for tracking habits.
  -Y, --yesterday       Set the date to yesterday.
  -l, --list            List habits.
  -o, --output FILENAME
                        If listing, output to file [default: -].
```

## Tools for periodical reflections

TODO: write up process on how to do a periodical reflection.

### tc reflect (2.0.0)

```
usage: tc reflect [-h] [--version] [-d DATE] [-w] [-m] [-y] [-M]

Reflect on a day, week or month.

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  -d, --date DATE  Use this date for reflection.
  -w, --week       Use this week for reflection.
  -m, --month      Use this month for reflection.
  -y, --yesterday  Use yesterday for reflection.
  -M, --missing    Fill in missing journal entries for the date range.
```

### tc observation dump (2.0.0)

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

### tc board dump (2.0.0)

```
usage: tc board dump [-h] [--version] [--thread THREAD] [--enumerate]

Dump a board to markdown.

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  --thread THREAD  Use specific thread [default: big-picture].
  --enumerate      Add numeric enumeration to points (e.g. 1.2.4.)
```

### tc reflect dump (2.0.0)

```
usage: tc reflect dump [-h] [--version] [-T THREAD] [--skip-journals]
                       [--no-summary] [--no-titles] [--no-habits]
                       [--no-observations] [--prefix PREFIX] [-d DATE_FROM]
                       [-D DATE_TO] [--year YEAR] [-M]

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
  -d, --from DATE_FROM  Dump from specific date.
  -D, --to DATE_TO      Dump to specific date.
  --year YEAR           Dump specific year.
  -M, --missing         Print only dates without reflection entries.
```

### tc events dump (2.0.0)

```
usage: tc events dump [-h] [--version] [-d DATE_FROM] [-D DATE_TO]
                      [--year YEAR] [-T THREAD] [--no-plans]
                      [--no-reflections]
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
```
