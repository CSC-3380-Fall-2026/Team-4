import { requiredElement } from "./dom.js";
import type { CalendarOptions } from "./friends-types.js";
import type {
    Schedule,
    ScheduleEvent,
    RenderPage,
} from "./types.js";

export const createRenderer = ({
    state,
    schedules,
    usersByUsername,
    displayName,
    makeElement,
}: CalendarOptions): { renderCalendar: RenderPage } => {
    const dayNames = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ];

    const chart = requiredElement("#friends-calendar");
    const dayLabel = requiredElement("#day-label");
    const namesLabel = requiredElement("#overlap-names");
    const startInput = requiredElement<HTMLInputElement>(
        "#free-time-start",
    );
    const endInput = requiredElement<HTMLInputElement>(
        "#free-time-end",
    );

    const minutes = (time: string): number => {
        const [hours, mins] = time.split(":").map(Number);
        return hours * 60 + mins;
    };

    const hourLabel = (totalMinutes: number): string => {
        const hours = Math.floor(totalMinutes / 60);
        const period = hours < 12 ? "AM" : "PM";

        return `${hours % 12 || 12} ${period}`;
    };

    const shortTime = (time: string): string => {
        const [hours, mins] = time.split(":").map(Number);

        return `${hours % 12 || 12}:${String(mins).padStart(2, "0")}`;
    };

    const pickedDate = (): Date => {
        const today = new Date();
        const daysSinceMonday = (today.getDay() + 6) % 7;
        const date = new Date(today);

        date.setDate(
            today.getDate() - daysSinceMonday + state.selectedDay,
        );

        return date;
    };

    const eventsOn = (
        userSchedules: Schedule[],
        dayName: string,
    ): ScheduleEvent[] => userSchedules
        .flatMap((schedule) => schedule.events)
        .filter((event) => event.days.includes(dayName));

    const renderCalendar = (): void => {
        const dayName = dayNames[state.selectedDay];
        const windowStart = minutes(startInput.value || "08:00");
        let windowEnd = minutes(endInput.value || "17:00");

        if (windowEnd <= windowStart) {
            windowEnd = windowStart + 60;
        }

        const windowLength = windowEnd - windowStart;
        const friendUser = usersByUsername.get(state.selectedFriend);

        const freeDay = state.freeDays.find(
            (item) => item.day === dayName,
        );

        const freePeriods = freeDay ? freeDay.periods : [];

        dayLabel.textContent = pickedDate().toLocaleDateString(
            "en-US",
            {
                weekday: "long",
                month: "short",
                day: "numeric",
            },
        );

        namesLabel.textContent = friendUser
            ? `You + ${displayName(state.selectedFriend)}`
            : "You";

        const placeBar = (
            bar: HTMLElement,
            start: number,
            end: number,
        ): boolean => {
            const from = Math.max(start, windowStart);
            const to = Math.min(end, windowEnd);

            if (to <= from) {
                return false;
            }

            bar.style.left =
                `${((from - windowStart) / windowLength) * 100}%`;

            bar.style.width =
                `${((to - from) / windowLength) * 100}%`;

            return true;
        };

        const makeRow = (
            name: string,
            events: ScheduleEvent[],
            showTimes: boolean,
        ): HTMLDivElement => {
            const row = makeElement("div", "overlap-row");

            row.append(makeElement(
                "span",
                "overlap-name",
                name,
            ));

            const track = makeElement("div", "overlap-track");

            events.forEach((event) => {
                const bar = makeElement("span", "overlap-busy");

                bar.title =
                    `${event.title}, ${shortTime(event.start)} - ${shortTime(event.end)}`;

                if (placeBar(
                    bar,
                    minutes(event.start),
                    minutes(event.end),
                )) {
                    track.append(bar);
                }
            });

            freePeriods.forEach((period) => {
                const text = showTimes
                    ? `${shortTime(period.start)}–${shortTime(period.end)}`
                    : undefined;

                const bar = makeElement(
                    "span",
                    "overlap-free",
                    text,
                );

                if (placeBar(
                    bar,
                    minutes(period.start),
                    minutes(period.end),
                )) {
                    track.append(bar);
                }
            });

            row.append(track);
            return row;
        };

        chart.replaceChildren();

        const hours = makeElement("div", "overlap-hours");

        for (let time = windowStart; time < windowEnd; time += 60) {
            const label = makeElement(
                "span",
                "",
                hourLabel(time),
            );

            label.style.left =
                `${((time - windowStart) / windowLength) * 100}%`;

            hours.append(label);
        }

        chart.append(hours);

        const rows = makeElement("div", "overlap-rows");

        freePeriods.forEach((period) => {
            const band = makeElement("span", "overlap-band");

            if (placeBar(
                band,
                minutes(period.start),
                minutes(period.end),
            )) {
                const bandTrack = makeElement(
                    "div",
                    "overlap-band-track",
                );

                bandTrack.append(band);
                rows.append(bandTrack);
            }
        });

        rows.append(makeRow(
            "You",
            eventsOn(schedules, dayName),
            true,
        ));

        if (friendUser) {
            rows.append(makeRow(
                displayName(state.selectedFriend),
                eventsOn(friendUser.schedules, dayName),
                false,
            ));
        }

        chart.append(rows);
    };

    return { renderCalendar };
};
