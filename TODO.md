# TODO. A backlog of ideas

- [ ] a weekly report could list out count and a summary of all items as email (for example)
- [x] No need for editable habit lines
  - [x] A journal suffices for that and doesn't have any shenanigans
  - [x] Implement a migration and then remove it altogether
- [ ] Add journal to the `today` view
- [ ] Move tools from random-tools to tasks-collector-tools
- Observation-Event migration
  - [x] Migrate observations to have their own ObservationMade/ObservationClosed events
  - [ ] Remove `date_closed` on observations
  - [x] Fix event_stream_id on habittracked
    - [ ] Implement signals event_stream_id saving on change etc for JournalAdded, HabitTracked...
  - [ ] Check once more whether the data and editing capabilities are preserved
  - [ ] See if `spawn_observation_events` should be done all around the application or not
  - [ ] add `pub_date` to events and allow for setting different day (yesterday) than now for events affecting a specific date (e.g. HabitsTracked)
  - [ ] Drop closed observations (migration + replace view in code)
  - [ ] Test and implement