# Breakthrough - End of Year

This feature is...

- [x] A Review mode for a given year
  - `?review=1` GET parameter enables review mode
  - Timeline section shows current year's breakthrough habits
- [x] An ability to Progress the outcome to the next year or close it
  - [x] `ProjectedOutcomeMoved` event model tracks:
    - `old_breakthrough` and `new_breakthrough` references
    - `confidence_level` at the time of move
    - `name`, `description`, `resolved_by`, `success_criteria` for historical reference
    - `projected_outcome` with SET_NULL for optional reference
  - [x] Moved outcomes displayed on old breakthrough page (similar to closed outcomes)
  - [x] UI to trigger the move action (endpoint and button)