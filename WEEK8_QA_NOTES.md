# Week 8 QA Notes

## GPA and Credit Validation
- GPA validation tests added.
- Course credit currently depends on meeting duration.
- A strict expected-failure test documents the need for explicit course credits.

## Account Ownership and Saved Schedules
- Confirmed: a schedule can be created and retrieved within the same session.
- Confirmed: a separate session cannot modify another session's schedule.
- Blocked: scheduler currently uses in-memory, cookie-scoped storage and mock users.
- Pending: tests using two authenticated account identities.
- Pending: rejection of missing or invalid authentication.
- Database persistence must be tested separately against Supabase after integration; current mocked/session tests do not verify database persistence.

## Page and Form Regression
- Confirmed: Friends, Planning, and Schedule content tests pass.
- Known gaps: Login, Registration, and Profile forms are placeholders, documented with strict expected-failure tests.
- Pending: catalog content and invalid form submission/error-message tests.

## Week 8 QA Follow-up

### Account Ownership
- Added a test requiring unauthenticated schedule creation to be rejected.
- Current backend accepts anonymous schedule creation; documented as an expected failure.
- Two-account ownership and Supabase persistence tests remain pending authenticated backend integration.

### Page and Form Regression
- Added passing tests for missing login and signup credentials (HTTP 422).
- Added an expected-failure test for the missing /catalog page.
- Existing catalog API tests cover searching and filtering.
- Login, registration, and profile form implementation remains pending.

### Latest Test Results
- 37 passed
- 7 expected failures
- 0 unexpected failures
