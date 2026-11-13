# Connor's Tiger Drive task walkthrough

Prepared from the uploaded main snapshot c1a40434e47df24b4e6972c0808da28a4e35a4a1.
William's shared-page-layout snapshot: 1496d86ff27bec43fbbe3d8f279b35f8a212f219.
These snapshots already have the same main page implementation. This work starts from main, rather than merging every uploaded branch.

## What is ready and what remains

| Task | Type / points supplied | Current result |
| --- | --- | --- |
| Connect and review the pages; preserve Vercel startup | Regular / 1 | Implemented and tested locally. Live deployment and recording its commit still need Connor. |
| Connect the Planning page to the existing GPA calculations | Regular / 2 | Implemented. The assigned example returns 3.20; invalid inputs stay in the form. |
| Add selected schedule, GPA summary, and upcoming events to William's dashboard | Design / 1 | Implemented with typed Jinja data, page links, and empty states. Supplied schedule/events are supported; the saved-schedule backend still needs to supply them. |

The earlier integration and Planning descriptions overlap these cards. Do not count the same work twice.
This package has not been pushed to GitHub or deployed to Vercel. The base commit above is NOT a deployed commit.

## What changed

- One shared Jinja layout provides Dashboard, Schedule, Planning, Course Catalog, Friends, Profile, Login, and Signup navigation.
- William's purple colors, Lato font, sidebar structure, and compiled stylesheet are reused. A separate stylesheet handles the new sections and responsive forms.
- The form uses ordinary HTML POST requests and Python handlers. It does not need JavaScript. Changing a grade takes effect when Calculate GPA is selected.
- Existing GPA endpoint addresses and camelCase JSON field names remain supported. New Python functions use snake_case; compatibility aliases preserve previous imports.
- GPA uses the existing weighted formulas. The valid LSU grade mapping comes from the uploaded GPA-Revisions branch without adopting its incompatible replacement course model.
- GPA input models are separate from the existing full course model. No invented meeting time or semester is required to calculate a forecast.
- Login and Signup have HTML forms that call the existing Supabase account operations. Account settings are loaded when needed, so missing settings no longer crash every page at startup.
- The Profile page verifies the session with Supabase and queries only the verified user's profile ID. Passwords are never echoed into HTML.
- The last computed GPA forecast can appear on Dashboard through a signed, HTTP-only browser cookie when SESSION_SECRET is configured. It is a forecast, not a saved academic record. It expires after 24 hours and clears on login/logout.
- All template filenames used by these routes match their case on Linux. The login template is renamed from Tiger_login.html to tiger_login.html.

Important scope: Schedule and Friends are connected pages with William's visual style and honest empty states. Their earlier JavaScript sample-data interactions are not loaded by the new pages. Saved schedule editing, friend requests, and shared calendars are not implemented by this package. Existing unused prototype sources are retained for the teammates implementing those features. Catalog search and GPA calculations continue to work.

## 1. Put the changes on a new branch

Use your existing Team-4 repository in VS Code. Open Terminal > New Terminal.
Copy only the commands, not PowerShell's PS prompt or output.

    cd "$env:USERPROFILE\Team-4\Team-4"
    git status

If there are uncommitted changes, save them on their existing branch before continuing. Do not discard them.
When the working tree is clean:

    git fetch origin
    git switch main
    git pull --ff-only origin main
    git switch -c connor-planning-dashboard

The included patch was built against the uploaded main snapshot. Your current main may have newer work. The check below catches conflicting edits; it does not mean this package includes later teammates' features.

Extract Connor_Tiger_Drive_Implementation.zip into a separate Downloads folder. It contains:
- connor_tasks.patch: the complete code change, including new files and the case correction.
- changed_files/: complete contents of every added or changed file, with repository-relative folders.
- files_to_remove.txt: the old uppercase login path replaced by the lowercase version.
- START_HERE.txt: this walkthrough.
- FILE_MAP.txt: the exact changed-file list.

In the VS Code terminal, run the following, replacing the path with the extracted patch's actual location:

    git apply --index --check "C:\Users\chase\Downloads\Connor_Tiger_Drive_Implementation\connor_tasks.patch"

If it prints no error, apply it:

    git apply --index "C:\Users\chase\Downloads\Connor_Tiger_Drive_Implementation\connor_tasks.patch"
    git status --short

If the check reports a conflict, stop before applying. Use VS Code's file comparison to combine the listed files with the newer main changes. Do not replace a whole teammate branch or use a force push.

Alternative for manually copying files: use changed_files/ and FILE_MAP.txt. Each listed path tells you exactly where the complete file belongs. On Windows, rename the old login file in two steps before copying its replacement:

    git mv app/templates/Tiger_login.html app/templates/login_temp.html
    git mv app/templates/login_temp.html app/templates/tiger_login.html

Use that manual rename only for the manual-copy route, not after the patch has already handled the change. Do not delete the whole templates directory.

## 2. Understand the important files

| File | What it does |
| --- | --- |
| app/tiger_app.py | Starts the app, mounts static files once, and includes the API/page routers. |
| vercel_entry.py | Existing root entrypoint retained unchanged; keeps the team's flat Python imports working. |
| pyproject.toml | Preserves entrypoint = "vercel_entry:app" and lists the required Python dependencies. |
| vercel.json | Selects FastAPI and includes templates, static assets, and catalog data in the function bundle. |
| app/routers/tiger_pages.py | Serves the page URLs, root redirect, catalog page, and navigation icons. |
| app/routers/tiger_accounts.py | Processes Login, Signup, and Logout HTML forms. |
| app/routers/tiger_planning.py | Displays and submits the Planning form, including Add course and Remove. |
| app/tiger_planning.py | Converts raw form text, validates rows, and calls the GPA calculations. |
| app/tiger_gpa.py | Shared weighted semester, cumulative, and required-GPA functions, with existing API URLs preserved. |
| app/grade_scale.py | One LSU grade-point mapping used by the form and GPA calculations. |
| app/models/tiger_planning.py | Typed calculation data and raw strings retained after validation errors. |
| app/models/tiger_dashboard.py | The selected schedule, forecast, and event data the dashboard expects. |
| app/tiger_dashboard.py | Reads supplied dashboard data and the signed browser forecast; sorts future events in LSU's time zone. |
| app/tiger_forecast.py | Signs and reads the browser's short-lived GPA forecast. |
| app/tiger_auth.py | Reuses account operations with per-operation Supabase clients and verified profile ownership. |
| app/models/tiger_profile.py | Validates optional profile GPA/course data before it is displayed. |
| app/tiger_views.py | Provides shared navigation, icons, rendering, and form tokens. |
| app/templates/tiger_base.html | Shared page shell, CSS links, navigation, and content block. |
| app/templates/components/dashboard_nav.html | Shared page links and account links. |
| app/templates/components/page_message.html | Reusable success, error, and empty-state messages. |
| app/templates/tiger_planner.html | Real Planning inputs, retained values, grade selectors, and calculated results. |
| app/templates/tiger_dashboard.html | The three requested dashboard sections. |
| app/static/tiger_workspace.css | Responsive styles that reuse William's existing theme variables. |
| tests/test_connor_pages.py | Acceptance and regression tests for these changes. |

The existing app/ folder and tiger_app.py name remain because they are already used by the repository and deployment. New endpoint and model files are organized under routers/ and models/. New functions have type hints and docstrings. Existing imported API names have compatibility aliases rather than breaking teammates' imports.

## 3. Install and run locally

From the repository root:

    py -3.12 -m venv .venv312
    .\.venv312\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv312\Scripts\python.exe -c "from vercel_entry import app; print('Application imports successfully')"
    .\.venv312\Scripts\python.exe -m pytest -q

The supplied version passed 45 tests on Python 3.12.14. This includes the four existing tests. It also passed the browser calculation check and a 390px-wide iframe layout check.

For accounts, use your existing .env settings if they are already correct. Otherwise copy .env.example to .env, then enter the current SUPABASE_URL and SUPABASE_KEY locally. Never commit .env.
For Dashboard to remember a browser forecast, set SESSION_SECRET to a random value. You can generate it locally with:

    .\.venv312\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"

Copy the generated value into SESSION_SECRET in your local .env. Keep it private. The calculator still runs without it; only remembering the forecast across page visits is disabled.

Start the server:

    .\.venv312\Scripts\python.exe -m uvicorn vercel_entry:app --reload --port 8001

Open http://127.0.0.1:8001/dashboard in your browser. Leave that terminal running while you use the local site. Ctrl+C stops the server.

No Tailwind build is needed for this patch: main already includes app/static/css/app.css, and these new rules are in tiger_workspace.css. Future Tailwind changes should follow the repository's existing build process.

## 4. Test your assigned Planning task

1. Open http://127.0.0.1:8001/planning?example=true.
2. Confirm Current GPA is 3.0 and completed GPA credit hours is 60.
3. Confirm five courses have 3 credits each and expected grade A (4.0).
4. Keep target GPA at 3.20 and select Calculate GPA.
5. Check Semester GPA = 4.00, New cumulative GPA = 3.20, Required semester GPA = 4.00.
6. Change the five expected grades to B and calculate again. Semester and cumulative results should both be 3.00.
7. Change target GPA to 4.3 and calculate. It should explain that the target is unreachable and that the highest possible cumulative GPA is 3.26. Your inputs should remain visible.
8. Set completed credits to 0 with current GPA 3.0. It should show a useful error, not a server exception.
9. Set both current GPA and completed credits to 0. With 15 planned credits and target 3.5, required semester GPA should be 3.50.
10. Try Add course and Remove. Other grades and history fields should stay intact.
11. With SESSION_SECRET configured, calculate a valid forecast and open Dashboard. Its GPA summary should show that forecast.

For the earlier JSON validation bug, /docs still has POST /calculateRequiredGPA. The request with currentGPA=3.0, completedCredits=0, plannedCredits=15, targetGPA=3.5 returns 400; changing currentGPA to 0.0 returns 200 and 3.5.

## 5. Test navigation and appearance

Open each URL directly, refresh it, and also reach it through navigation:

    /dashboard
    /schedule
    /planning
    /catalog
    /friends
    /profile
    /login
    /signup

The root / redirects to /dashboard. The older /signin link redirects to /signup.
Check /static/css/app.css and /static/tiger_workspace.css load. Check /health returns {"status":"healthy"}. Test catalog search with 3380 and an impossible search string.
Verify the selected schedule, GPA summary, and upcoming events each have a useful empty state and a link to their relevant page. Resize the browser to a narrow width; the course table may scroll within its card, while the page itself should fit.

## 6. Connect real schedule/profile records when the backend is ready

This package does not create database tables or apply SQL to Supabase.
The schedule backend can supply DashboardData through app.state.dashboard_provider. Its callable receives the Request and must return data belonging only to the verified current student. Selected schedule may be None; forecast may be None; events may be an empty list. Event starts_at values must include a time zone. The view displays the next six future events in America/Chicago time.

The expected profile table fields are profiles.id, username, gpa, and courses. Account IDs are the verified Supabase user IDs. Each completed-course object is expected to contain course_code, course_name, and credits. If the team's actual schema differs, adapt the profile model/query to that schema instead of inventing records. Unavailable or malformed academic data produces a helpful message.

Real Login/Signup/Profile behavior needs verification with your configured Supabase project. Offline tests mock the external account service; they do not prove that the live schema, email confirmation, or row access policies are configured. Sessions currently use the access token for up to one hour; when it expires, the student logs in again. Automatic refresh and password reset are separate follow-up features.

## 7. Review and create the pull request

After the tests pass:

    git diff --cached --stat
    git diff --cached --check
    git status --short

Review the changes in VS Code. Make sure .env and virtual-environment folders are absent from the staged changes. The patch route stages its changes automatically. For the manual-copy route, stage only the paths in FILE_MAP.txt. Then run:

    git commit -m "Connect Planning and dashboard in William's layout"
    git push -u origin connor-planning-dashboard

Open the pull request on GitHub. Use the team's normal review path into dev and then main if that policy still applies; Vercel production currently tracks main.

Suggested PR title:
Connect William's pages, GPA Planning, and dashboard summaries

Suggested PR body:
The Planning page used example values and the dashboard lacked its three summary sections. This change adds a Python/Jinja Planning form that reuses the GPA calculations, keeps inputs after errors, and uses William's shared layout across page routes. It preserves the root Vercel entrypoint and existing catalog/GPA API addresses. Account configuration is lazy so missing Supabase settings do not stop public pages from starting.

Validation: 45 local tests passed; browser verified the 3.20 cumulative example and unreachable-target message; narrow-screen layout checked. Live Vercel deployment and real Supabase account checks remain pending. Schedule and Friends remain honest empty/read-only pages until their backends are connected.

## 8. Deploy through Connor's Vercel account

Only Connor performs these deployment steps.

1. Review the Vercel preview for this branch before merging it to the production branch.
2. Keep the Vercel project connected to CSC-3380-Fall-2026/Team-4. The organization name is not an extra folder to deploy.
3. Keep Root Directory at ./ and the framework preset FastAPI. The custom entrypoint stays vercel_entry:app in pyproject.toml. Do not change it to a missing main.py or create a second frontend deployment.
4. Use the normal FastAPI build behavior. An old Render command such as gunicorn your_application.wsgi or an unrelated frontend output directory does not belong in this configuration.
5. Set SUPABASE_URL, SUPABASE_KEY, and SESSION_SECRET in the project's Environment Variables for both Preview and Production. Use raw values, not Markdown links, backticks, or NAME=value in the value box. Use your current keys; do not send them in chat or commit them.
6. Redeploy after changing environment variables. An older deployment does not automatically gain newly saved values.
7. After the reviewed changes reach main, open the resulting production deployment and compare its Source commit with the merged GitHub commit.
8. Test the production URL for /health, every page above, both CSS files, the Planning example, and real account login/profile behavior. Ready means the build completed; these route checks verify the application runs.
9. Use the production domain team-4-delta.vercel.app when sharing the site. An older deployment-specific URL will keep showing that older deployment.
10. Fill in docs/deployment_record.md with the actual deployed commit, URL, date, and results. Do not mark the deployment task complete while those fields are pending.

## References

- Google Python style: https://google.github.io/styleguide/pyguide.html
- FastAPI form processing: https://fastapi.tiangolo.com/tutorial/request-forms/
- Vercel FastAPI entrypoint and static assets: https://vercel.com/docs/frameworks/backend/fastapi
- Vercel function bundle configuration: https://vercel.com/docs/project-configuration/vercel-json
- LSU plus/minus grade scale: https://www.lsu.edu/registrar/grade-policy/plus-minus-grades.php
