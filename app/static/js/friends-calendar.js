(() => {
    // Draws the "A little overlap goes a long way" chart on the Friends page.
    // It shows one day at a time: one row for you and one row for the friend you checked.
    const createRenderer = ({ state, schedules, usersByUsername, displayName, makeElement }) => {
        const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
        const chart = document.querySelector("#friends-calendar");
        const dayLabel = document.querySelector("#day-label");
        const namesLabel = document.querySelector("#overlap-names");
        const startInput = document.querySelector("#free-time-start");
        const endInput = document.querySelector("#free-time-end");

        const minutes = (time) => {
            const [hours, mins] = time.split(":").map(Number);
            return hours * 60 + mins;
        };

        // 780 -> "1 PM"
        const hourLabel = (totalMinutes) => {
            const hours = Math.floor(totalMinutes / 60);
            const period = hours < 12 ? "AM" : "PM";
            return `${hours % 12 || 12} ${period}`;
        };

        // "14:00" -> "2:00"
        const shortTime = (time) => {
            const [hours, mins] = time.split(":").map(Number);
            return `${hours % 12 || 12}:${String(mins).padStart(2, "0")}`;
        };

        // The real date of the picked weekday in this week (state.selectedDay 0 = Monday)
        const pickedDate = () => {
            const today = new Date();
            const daysSinceMonday = (today.getDay() + 6) % 7;
            const date = new Date(today);
            date.setDate(today.getDate() - daysSinceMonday + state.selectedDay);
            return date;
        };

        const eventsOn = (userSchedules, dayName) => userSchedules
            .flatMap((schedule) => schedule.events)
            .filter((event) => event.days.includes(dayName));

        const renderCalendar = () => {
            const dayName = dayNames[state.selectedDay];
            const windowStart = minutes(startInput.value || "08:00");
            let windowEnd = minutes(endInput.value || "17:00");
            if (windowEnd <= windowStart) {
                windowEnd = windowStart + 60;
            }
            const windowLength = windowEnd - windowStart;

            const friendUser = usersByUsername.get(state.selectedFriend);
            // only the schedule picked under Sharing settings, not every alternative
            const mine = schedules.filter((schedule) => schedule.id === state.selectedScheduleId);
            const you = mine.length > 0 ? `You (${mine[0].name})` : "You";
            const theirs = friendUser
                ? friendUser.schedules.filter((schedule) => schedule.id === state.selectedFriendScheduleId)
                : [];
            const them = theirs.length > 0
                ? `${displayName(state.selectedFriend)} (${theirs[0].name})`
                : displayName(state.selectedFriend);
            const freeDay = state.freeDays.find((item) => item.day === dayName);
            const freePeriods = freeDay ? freeDay.periods : [];

            dayLabel.textContent = pickedDate().toLocaleDateString("en-US", {
                weekday: "long",
                month: "short",
                day: "numeric",
            });
            namesLabel.textContent = friendUser
                ? `${you} + ${them}`
                : you;

            // Turn a start and end time into a left and width percent on the track
            const placeBar = (bar, start, end) => {
                const from = Math.max(start, windowStart);
                const to = Math.min(end, windowEnd);
                if (to <= from) {
                    return false;
                }
                bar.style.left = `${((from - windowStart) / windowLength) * 100}%`;
                bar.style.width = `${((to - from) / windowLength) * 100}%`;
                return true;
            };

            const makeRow = (name, events, showTimes) => {
                const row = makeElement("div", "overlap-row");
                row.append(makeElement("span", "overlap-name", name));
                const track = makeElement("div", "overlap-track");

                events.forEach((event) => {
                    const bar = makeElement("span", "overlap-busy");
                    bar.title = `${event.title}, ${shortTime(event.start)} - ${shortTime(event.end)}`;
                    if (placeBar(bar, minutes(event.start), minutes(event.end))) {
                        track.append(bar);
                    }
                });
                freePeriods.forEach((period) => {
                    // only the top row gets the time written on the gold part, like the figma
                    const text = showTimes ? `${shortTime(period.start)}–${shortTime(period.end)}` : undefined;
                    const bar = makeElement("span", "overlap-free", text);
                    if (placeBar(bar, minutes(period.start), minutes(period.end))) {
                        track.append(bar);
                    }
                });

                row.append(track);
                return row;
            };

            chart.replaceChildren();

            const hours = makeElement("div", "overlap-hours");
            for (let time = windowStart; time < windowEnd; time += 60) {
                const label = makeElement("span", "", hourLabel(time));
                label.style.left = `${((time - windowStart) / windowLength) * 100}%`;
                hours.append(label);
            }
            chart.append(hours);

            const rows = makeElement("div", "overlap-rows");
            // the light gold stripe that runs behind every row where everyone is free
            freePeriods.forEach((period) => {
                const band = makeElement("span", "overlap-band");
                if (placeBar(band, minutes(period.start), minutes(period.end))) {
                    const bandTrack = makeElement("div", "overlap-band-track");
                    bandTrack.append(band);
                    rows.append(bandTrack);
                }
            });
            rows.append(makeRow("You", eventsOn(mine, dayName), true));
            if (friendUser) {
                rows.append(makeRow(displayName(state.selectedFriend), eventsOn(theirs, dayName), false));
            }
            chart.append(rows);
        };

        return { renderCalendar };
    };

    window.FriendsCalendar = { createRenderer };
})();
