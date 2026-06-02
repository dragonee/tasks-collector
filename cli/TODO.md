## Completed Features

- [x] Save [x] lines or some other mark (maybe quote signs) as Good points in Reflection
- [x] observationdump dumps Updates
- [x] observationdump dumps Events?
- [x] observationdump dumps Closed
- [x] habits (ask for all habits occured/missed/skip for the day)
- [x] convert observationupdate to journal
- [x] remove journalize, implement journal directly in tasks-collector
- [x] Show plan for today in tasks tool
  - [x] And journal tool
- [x] Dump journal to file
- [x] Dump habits?
- [x] use pipe separator for multiple habits tracked in habits tool
- [x] Add reflection tool
  - [x] Add reflectiondump tool
  - [x] Weekly mode:
    - Shows eventdump for last 7 days
    - Allows to modify Reflection for weekly thread
  - [x] Monthly mode:
    - [x] Shows reflections on weekly thread
    - [x] Shows breakthroughs
    - [x] Allows to modify Reflection for monthly thread
- [x] Two-stage reflection:
  - First stage – get interesting points from reflection
  - Second stage - write a journal entry based on reflection
- [x] >Daily should send a task to a daily list
- [x] Bug: ensure that .tasks exists before writing to it

## Pending Features

- [ ] offline mode for observation and update tools if no internet connectivity is present (a single json store of objects to be sent... or markdown files)
- [ ] tasks downloads habits and journal shows them
- [ ] Should we remove event_stream_id events when we push to journal?
- [ ] Set short timeouts for plan and quick notes getters
- [ ] Cache plan and quick notes in journal tool
- [ ] Eventdump: fix `- #` problems, some markdown implementations are treating it as a heading in list
- [ ] Use rlcompleter for named observations
- [ ] Reflection Daily mode – do we need it?
  - Shows eventdump for today
  - Allows to modify Reflection for today
- [ ] Better emoji support
- [ ] Either handle projected outcome events or remove projected outcome events from events in tasks-collector
- [ ] Add Areas
  - Reflection Weekly is separated in areas (journal tags)
  - Each Area has own journal entry then, tagged accordignly
- [ ] >Thread Task this and that
- [ ] observation -u should search lastest work on the repo
