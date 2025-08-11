# Complex mode design document

This is an addition to Observations, that would give the user to:

1. attach other observations to an observation, which we will call an Complex Observation.
2. view all attached observations as a side by side panel with the Complex Observation they are attached to
   1. attached observations are read-only
   2. the Complex Observation can be edited as on the /observations/<id>/ page

The purpose of this feature is to group multiple observations as a single entity, so that these can be read and analysed together as one – and the user can draw new insights and conclusions from these.

## Glossary

- Complex Observation: the observation that has one or more observations attached to
- Attached Observation: the observation being attached to Complex Observation. An Attached Observation can be part of multiple Complex Observations

## Step-by-step guide

The outome should be implemented in the following way:

- [ ] Create two additional events – `ObservationAttached` and `ObservationDetached`
- [ ] Create a `ComplexPresenter` class that can replay Attached/Detached events
- [ ] Add the API endpoints to attach and detach observations
- [ ] Add the API endpoint to search for an observation
- [ ] Change User interface to allow for searching, attaching and displaying Attached Observations

### Additional events 

Create two additional events – `ObservationAttached` and `ObservationDetached`

1. [ ] ObservationAttached links to another observation (via ID foreign key and event_stream_id).
2. [ ] ObservationDetached links only to the event_stream_id.
3. [ ] ObservationAttached has SET NULL constraint on observation removed.
4. [ ] If an observation is closed (and the Observation object is removed), it DOES NOT result in an ObservationDetached event – we keep it as attached

### Presenter classes for events

Create a `ComplexPresenter` class that can replay Attached/Detached events and generate from that the following information:

1. [ ] Number of open Observations currently attached
2. [ ] Number of total unique Observations currently attached (number of unique event_stream_id's)
3. [ ] List of open Observations currently attached
4. [ ] All events, chronologically sorted, for all the currently attached Observations
5. [ ] A helper presenter class, that can contain the situation field and event at the time of the event

### API endpoints to attach and detach observations

Both endpoints should create a respective event in the database.

### API endpoint to search for observations

That search should:

1. [ ] Search the situation, interpretation and approach text fields
2. [ ] Use internal PostgreSQL text index
3. [ ] Situation field should take precendence (so if that can give bigger/multiplied score), then 

### User interface changes 

On the `tasks/templates/tree/observation_edit.html`:

1. [ ] Add a toggle for the Complex side panel (from the left)
    1. [ ] If there are any Attached Observations, it's turned on by default
2. [ ] Add an search bar with suggestions
3. [ ] Add an action to attach the suggestion
4. [ ] Show events from all Attached Observation
5. Whole page can reload on any modification – we do not need to add dynamic content for now


   

