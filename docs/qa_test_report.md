
# Task 2: Automated Regression and Integration Tests

## Running the tests

From the project root, with dependencies installed:

    python -m pytest tests -q

For the local Python 3.14 environment:

    .venv314/bin/python -m pytest tests -q

## Results

Latest full test run: 26 passed, 1 xfailed.
Latest scheduler-specific test run: 3 passed, 1 xfailed.

The additional boundary test passed in the scheduler-specific run. The full suite must be rerun to confirm the updated total.

Tests cover GPA calculations, invalid inputs, unreachable GPA targets, course catalog searching and filtering, page routes, schedule reopening, session isolation, and schedule conflict boundaries.

The overlapping-class test is marked strict xfail because the application currently accepts conflicting classes.

## Bugs discovered

### Course model test mismatch

Steps: Run the original tests in tests/test_tiger_models.py.

Expected: Valid course data passes validation.

Actual: Required schedule fields were missing, and the test referenced an outdated name attribute.

Resolution: Updated the tests to match the current model.

### GPA credit calculation test fixture

Steps: Calculate cumulative GPA with 12 completed credits at 3.00 and a new course worth 3 credits at 4.00.

Expected: 3.20 cumulative GPA.

Actual: The course model derives credits from scheduled hours, so a one-hour test fixture produced an incorrect result.

Resolution: Updated the fixture to represent three credits.

### Schedule overlap bug (open)

Steps:
1. Create a schedule using POST /api/schedules.
2. Add Class A on Monday from 10:00 to 11:00.
3. Add Class B on Monday from 10:30 to 11:30.

Expected: The second class is rejected with HTTP 409 because the times overlap.

Actual: The second class is accepted with HTTP 201.

Status: Open production bug. Covered by test_overlapping_classes_should_be_rejected in tests/test_tiger_scheduler.py, marked strict xfail.

### Schedule boundary verification

Steps:
1. Create a schedule.
2. Add Class A on Monday from 10:00 to 11:00.
3. Add Class B on Monday from 11:00 to 12:00.

Expected: Both classes are accepted because their times do not overlap.

Actual: Both classes are accepted with HTTP 201.

Status: Passing automated regression test.

## Known limitations

Schedule data currently uses in-memory session storage. Schedule reopening and isolation between separate sessions are tested.

Permanent database persistence, reopening after a server restart, and authenticated account-level access restrictions cannot yet be verified with the current implementation.

The overlapping-class conflict bug remains unresolved and requires a production fix.

