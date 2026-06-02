# Tasks Collector Tools

These tools add CLI support to the [Tasks Collector](https://github.com/dragonee/tasks-collector) application.

## All-in-one

### tasks (1.0.2)

```
Connect to the Tasks Collector.

Usage:
    tasks [options]

Options:
    --thread THREAD  Use specific thread.
    -h, --help       Show this message.
    --version        Show version information.

By default, tasks are added to the thread from your profile.
By prefixing a line with `!` or `#`, it will be added to the Habit Tracker instead.

Available commands:
  observation
  olist
  habits
  hlist
  oedit
  edit
  quest
  journal
  thought
  update
  help
  clear
  wtf
  nove
  reflect
  thread
  stats

Quit by pressing Ctrl+D or Ctrl+C.
```

## Journalling

### journal (1.1)

```
Add journal entry.

Usage: 
    journal [options]

Options:
    -d, --date DATE  Use this date for the journal entry.
    -T TAGS, --tags TAGS  Add these tags to the journal entry.
    -s               Also save a copy as new observation, filling Situation field.
    -o               Alias for -s.
    -Y, --yesterday  Use yesterday's date for the journal entry.
    -t THREAD, --thread THREAD  Use this thread [default: Daily]
    -f FILE, --file FILE  Use this file instead of the generated template.
    -L, --today      List journals from today.
    -h, --help       Show this message.
    --version        Show version information.
```

## Observations

### observation (1.0.2)

```
Add an observation.

Usage:
    observation [options]

Options:
    -l, --list       List last couple of observations.
    -a, --all        With -l, show all observations (not just mine).
    -n, --number N   With -l, show N observations [default: 20].
    -c, --chars N    With -l, show N chars of the situation [default: 100].
    -u, --sort-by-update  With -l, sort by last event time (most recent first).
    --date DATE      Use specific date.
    -s, --save       Save as default for updates [default: False].
    --thread THREAD  Use specific thread [default: big-picture].
    --type TYPE      Choose type [default: observation].
    -h, --help       Show this message.
    --version        Show version information.
```

### update (1.0.2)

```
Add update to an observation.

Usage: 
    update [options] [ID]

Options:
    -h, --help       Show this message.
    --version        Show version information.
```

## Habits

### habits (1.1)

```
Track habits daily or list them.

Usage: 
    habits [options]

Options:
    -a, --all        Track all habits.
    -d, --date DATE  Use this date for tracking habits.
    -Y, --yesterday  Set the date to yesterday.
    -l, --list       List habits
    -o, --output FILENAME  If listing, output to file [default: -]
    -h, --help       Show this message.
    --version        Show version information.
```

## Quests

### quest (1.0.1)

```
Follow a quest.

Usage: 
    quest [options] KEY [STAGE]

Options:
    -h, --help       Show this message.
    --version        Show version information.
```

## Tools for periodical reflections

TODO: write up process on how to do a periodical reflection.

### reflect (1.1)

```
Reflect on a day, week or month.

Usage: 
    reflect [options]

Options:
    -d, --date DATE  Use this date for reflection.
    -w, --week       Use this week for reflection.
    -m, --month      Use this month for reflection.
    -y, --yesterday  Use yesterday for reflection.
    -M, --missing    Fill in missing journal entries for the date range.
    -h, --help       Show this message.
    --version        Show version information.
```

### observationdump (1.1)

```
Dump observations to markdown files.

Usage: 
    observationdump [options] PATH

Options:
    --open           Dump only open observations.
    --closed         Dump only closed observations.
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    -f, --force      Overwrite existing files.
    --stream ID      Dump object with specific Event Stream ID.
    --year YEAR      Dump specific year.
    -h, --help       Show this message.
    --version        Show version information.
```

### boardmd (1.0)

```
Dump a board to markdown.

Usage: 
    boardmd [options]

Options:
    --thread THREAD  Use specific thread [default: big-picture].
    --enumerate      Add numberic enumeration to points (e.g. 1.2.4.)
    -h, --help       Show this message.
    --version        Show version information.
```

### reflectiondump (1.0)

```
Dump observations to markdown files.

Usage: 
    reflectiondump [options]

Options:
    -T, --thread THREAD  Dump specific thread.
    --skip-journals     Skip journals.
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    --year YEAR      Dump specific year.
    -M, --missing    Print only dates without reflection entries.
    -h, --help       Show this message.
    --version        Show version information.
```

### eventdump (1.0)

```
Dump observations to markdown files.

Usage:
    eventdump [options] [PATH]

Options:
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    --year YEAR      Dump specific year.
    -T THREAD, --thread THREAD Dump specific thread.
    --no-plans       Exclude plans from output.
    --no-reflections  Exclude reflections from output.
    -h, --help       Show this message.
    --version        Show version information.
```

### reflect (1.1)

```
Reflect on a day, week or month.

Usage: 
    reflect [options]

Options:
    -d, --date DATE  Use this date for reflection.
    -w, --week       Use this week for reflection.
    -m, --month      Use this month for reflection.
    -y, --yesterday  Use yesterday for reflection.
    -M, --missing    Fill in missing journal entries for the date range.
    -h, --help       Show this message.
    --version        Show version information.
```
