(() => {
    // Build calendar rendering around the shared Friends page state and helpers
    const createRenderer = ({ state, schedules, usersById, displayName, makeElement }) => {
        const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
        const calendar = document.querySelector("#friends-calendar");
        const calendarScroll = document.querySelector("#friends-calendar-scroll");

        const minutes = (time) => {
            const [hours, mins] = time.split(":").map(Number);
            return hours * 60 + mins;
        };

        const timeLabel = (time) => {
            const [hours, mins] = time.split(":").map(Number);
            const period = hours < 12 ? "AM" : "PM";
            return `${hours % 12 || 12}:${String(mins).padStart(2, "0")} ${period}`;
        };

        const combinedEvents = () => {
            const friendUser = usersById.get(state.selectedFriend);
            if (!friendUser) {
                return [];
            }
            // Compare every schedule for both users, independent of the sharing selection
            const events = [
                ...schedules.flatMap((schedule) => schedule.events.map((event) => ({ ...event, owner: "you" }))),
                ...friendUser.schedules.flatMap((schedule) => schedule.events.map((event) => ({ ...event, owner: "friend" }))),
            ];
            const merged = [];
            events.forEach((event) => {
                const signature = `${event.title}|${event.start}|${event.end}|${[...event.days].sort().join(",")}`;
                // Mark matching events from opposite owners as shared rather than duplicating them
                const sharedEvent = merged.find((item) => (
                    item.signature === signature && item.owner !== event.owner
                ));
                if (sharedEvent) {
                    sharedEvent.owner = "shared";
                } else {
                    merged.push({ ...event, signature });
                }
            });
            return merged;
        };

        const renderCalendar = () => {
            calendar.querySelectorAll(".friends-calendar-day").forEach((day) => day.replaceChildren());
            combinedEvents().forEach((event) => {
                const start = Math.max(minutes(event.start), 0);
                const end = Math.min(minutes(event.end), 24 * 60);
                if (end <= start) {
                    return;
                }

                event.days.forEach((dayName) => {
                    const dayIndex = dayNames.indexOf(dayName);
                    const dayColumn = calendar.querySelector(`[data-weekday="${dayIndex}"]`);
                    if (!dayColumn) {
                        return;
                    }
                    // Preserve distinct owner colors while sharing the same compact layout.
                    const colorClasses = event.owner === "you"
                        ? "border-purple-300 bg-purple-50 text-purple-700"
                        : event.owner === "friend"
                            ? "border-yellow-300 bg-yellow-50 text-yellow-800"
                            : "border-neutrals-300 bg-neutrals-100 text-neutrals-700";
                    const isCompact = end - start <= 60;
                    const layoutClasses = isCompact
                        ? "m-0.5 flex min-h-0 min-w-0 items-center overflow-hidden rounded-md border px-1 text-[9px] leading-none"
                        : "m-0.5 flex min-h-0 min-w-0 flex-col overflow-hidden rounded-md border px-1.5 py-1 text-[10px] leading-tight";
                    const card = makeElement("article", `col-start-1 row-(--event-grid-row) z-10 ${layoutClasses} ${colorClasses}`);
                    card.dataset.start = event.start;
                    card.dataset.end = event.end;
                    const ownerName = event.owner === "shared"
                        ? "Shared"
                        : event.owner === "you" ? "You" : displayName(state.selectedFriend);
                    card.title = `${event.title}, ${timeLabel(event.start)} - ${timeLabel(event.end)} (${ownerName})`;
                    card.setAttribute("aria-label", card.title);
                    if (isCompact) {
                        card.append(makeElement("strong", "block truncate font-bold", `${event.title} · ${timeLabel(event.start)}`));
                    } else {
                        card.append(
                            makeElement("strong", "truncate font-bold", event.title),
                            makeElement("span", "truncate", `${timeLabel(event.start)} - ${timeLabel(event.end)}`),
                            makeElement("span", "truncate opacity-80", ownerName),
                        );
                    }
                    const firstRow = Math.floor(start / 30);
                    const lastRow = Math.ceil(end / 30);
                    card.style.setProperty("--event-grid-row", `${firstRow + 1} / ${lastRow + 1}`);
                    dayColumn.append(card);
                });
            });
        };

        const scrollCalendarToFirstEvent = () => {
            const firstEvent = [...calendar.querySelectorAll("article[data-start]")]
                .sort((left, right) => minutes(left.dataset.start) - minutes(right.dataset.start))[0];
            if (!firstEvent) {
                return;
            }

            calendarScroll.scrollTop = 0;
            const eventOffset = firstEvent.getBoundingClientRect().top
                - calendarScroll.getBoundingClientRect().top;
            const stickyHeader = calendar.querySelector(".sticky");
            calendarScroll.scrollTop = Math.max(
                0,
                eventOffset - (stickyHeader?.offsetHeight ?? 0) - 4,
            );
        };

        return { renderCalendar, scrollCalendarToFirstEvent };
    };

    window.FriendsCalendar = { createRenderer };
})();
