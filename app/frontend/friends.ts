import { requiredElement } from "./dom.js";
import {
    apiRequest,
    errorMessage,
    scheduleState,
    getUserById,
    loadScheduleData,
} from "./schedule-data.js";
import { createRenderer } from "./friends-calendar.js";
import { makeElement } from "./friends-types.js";
import type {
    FriendState,
    FriendUser,
    FreeCard,
} from "./friends-types.js";
import type {
    ScheduleUser,
    SharedFreeTime,
} from "./types.js";

const searchMessage = requiredElement("#friend-search-message");

loadScheduleData().then(initializeFriends).catch((error) => {
    searchMessage.textContent = errorMessage(error);
    searchMessage.className = "text-sm text-red-600";
});

function initializeFriends(): void {
    const users: FriendUser[] = scheduleState.users.filter(
        (user): user is ScheduleUser & { username: string } =>
            typeof user.username === "string",
    );

    const currentUser = getUserById(scheduleState.currentUserId);

    if (!currentUser) {
        throw new Error(
            "The current user was not included in the schedule response.",
        );
    }

    const schedules = currentUser.schedules;

    const friendUsers = users.filter(
        (user) => user.id !== currentUser.id,
    );

    const usersByUsername = new Map(
        users.map((user) => [user.username, user]),
    );

    const state: FriendState = {
        requests: [],
        friends: friendUsers.map((user) => ({
            username: user.username,
        })),
        viewers: Object.fromEntries(
            schedules.map((schedule) => [schedule.id, []]),
        ),
        publicSchedules: new Set<string>(),
        selectedScheduleId: schedules[0]?.id ?? "",
        selectedFriend: friendUsers[0]?.username ?? "",
        selectedDay: (new Date().getDay() + 6) % 7,
        dayPicked: false,
        freeDays: [],
    };

    const requestList = requiredElement("#pending-requests");
    const friendsList = requiredElement("#friends-list");
    const requestCount = requiredElement("#pending-request-count");
    const noRequests = requiredElement("#no-pending-requests");
    const noFriends = requiredElement("#no-friends");

    const friendForm = requiredElement<HTMLFormElement>(
        "#find-friend-form",
    );
    const usernameInput = requiredElement<HTMLInputElement>(
        "#friend-username",
    );
    const sharedSchedulePicker = requiredElement<HTMLSelectElement>(
        "#shared-schedule-picker",
    );
    const publicSharingToggle = requiredElement<HTMLInputElement>(
        "#public-sharing-toggle",
    );

    const scheduleViewers = requiredElement("#schedule-viewers");

    const addScheduleViewer = requiredElement<HTMLSelectElement>(
        "#add-schedule-viewer",
    );
    const addScheduleViewerButton = requiredElement<HTMLButtonElement>(
        "#add-schedule-viewer-button",
    );

    const noScheduleViewers = requiredElement("#no-schedule-viewers");
    const sharingStatus = requiredElement("#sharing-status");
    const friendCount = requiredElement("#friend-count");
    const freeTotal = requiredElement("#free-total");

    const freeTimeStart = requiredElement<HTMLInputElement>(
        "#free-time-start",
    );
    const freeTimeEnd = requiredElement<HTMLInputElement>(
        "#free-time-end",
    );
    const minimumFreeDuration = requiredElement<HTMLSelectElement>(
        "#minimum-free-duration",
    );

    const freePeriods = requiredElement("#free-periods");
    let freeTimeRequestSequence = 0;

    const formatTime = (time: string): string => {
        const [hours, minutes] = time.split(":").map(Number);
        const period = hours < 12 ? "AM" : "PM";

        return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${period}`;
    };

    const dayNames = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ];

    const toMinutes = (time: string): number => {
        const [hours, minutes] = time.split(":").map(Number);
        return hours * 60 + minutes;
    };

    const formatRange = (start: string, end: string): string => {
        const startText = formatTime(start)
            .replace(" AM", "")
            .replace(" PM", "");

        return `${startText}–${formatTime(end)}`;
    };

    const formatDay = (dayName: string): string => {
        const today = new Date();
        const daysSinceMonday = (today.getDay() + 6) % 7;
        const date = new Date(today);

        date.setDate(
            today.getDate()
            - daysSinceMonday
            + dayNames.indexOf(dayName),
        );

        const month = date.toLocaleDateString(
            "en-US",
            { month: "short" },
        );

        return `${dayName.slice(0, 3)}, ${month} ${date.getDate()}`.toUpperCase();
    };

    const formatLength = (duration: number): string => {
        if (duration < 120) {
            return `${duration} minutes`;
        }

        const hours = duration / 60;

        return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} hours`;
    };

    const showFreeMessage = (
        message: string,
        isError: boolean,
    ): void => {
        freePeriods.replaceChildren();

        freePeriods.className = isError
            ? "plan-cards plan-message plan-error"
            : "plan-cards plan-message";

        freePeriods.textContent = message;
    };

    const renderFreePeriods = async (): Promise<void> => {
        const requestSequence = ++freeTimeRequestSequence;

        if (!state.selectedFriend) {
            state.freeDays = [];
            freeTotal.textContent = "Shared free time this week";

            showFreeMessage(
                state.friends.length > 0
                    ? "Check a friend to compare shared free time."
                    : "Add a friend to compare shared free time.",
                false,
            );

            renderCalendar();
            return;
        }

        try {
            const result = await apiRequest<SharedFreeTime>(
                "/api/shared-free-time",
                {
                    method: "POST",
                    body: JSON.stringify({
                        friendUsername: state.selectedFriend,
                        startTime: freeTimeStart.value,
                        endTime: freeTimeEnd.value,
                        minimumDuration: Number(minimumFreeDuration.value),
                    }),
                },
            );

            if (requestSequence !== freeTimeRequestSequence) {
                return;
            }

            state.freeDays = result.days;

            if (!state.dayPicked && result.days.length > 0) {
                state.selectedDay = dayNames.indexOf(result.days[0].day);
            }

            renderCalendar();

            if (result.days.length === 0) {
                freeTotal.textContent =
                    "0 hours of shared free time this week";

                showFreeMessage(
                    `No shared free periods of at least ${minimumFreeDuration.value} minutes within the selected hours.`,
                    false,
                );

                return;
            }

            const cards: FreeCard[] = [];
            let totalMinutes = 0;

            result.days.forEach(({ day, periods }) => {
                periods.forEach(({ start, end }) => {
                    const duration = toMinutes(end) - toMinutes(start);

                    totalMinutes += duration;
                    cards.push({ day, start, end, duration });
                });
            });

            const totalHours = Math.round((totalMinutes / 60) * 10) / 10;

            freeTotal.textContent =
                `${totalHours} hours of shared free time this week`;

            freePeriods.className = "plan-cards";
            freePeriods.replaceChildren();

            cards.slice(0, 3).forEach((card, index) => {
                const isBest = index === 0;

                const item = makeElement(
                    "article",
                    isBest ? "plan-card plan-best" : "plan-card",
                );

                const link = makeElement(
                    "a",
                    "plan-button",
                    "Make a plan ↗",
                );

                link.href = "/schedule";

                item.append(
                    makeElement("p", "plan-day", formatDay(card.day)),
                    makeElement(
                        "p",
                        "plan-time",
                        formatRange(card.start, card.end),
                    ),
                    makeElement(
                        "p",
                        "plan-length",
                        isBest
                            ? `${formatLength(card.duration)} · Best match`
                            : `${formatLength(card.duration)} together`,
                    ),
                    link,
                );

                freePeriods.append(item);
            });
        } catch (error) {
            if (requestSequence !== freeTimeRequestSequence) {
                return;
            }

            state.freeDays = [];
            renderCalendar();
            showFreeMessage(errorMessage(error), true);
        }
    };

    const displayName = (username: string): string => username;

    const makeButton = (
        text: string,
        classes: string,
        action: () => void,
        label: string,
    ): HTMLButtonElement => {
        const button = makeElement("button", classes, text);

        button.type = "button";
        button.setAttribute("aria-label", label);
        button.addEventListener("click", action);

        return button;
    };

    const renderRequests = (): void => {
        requestList.replaceChildren();

        requestCount.textContent = state.requests.length > 0
            ? String(state.requests.length)
            : "";

        noRequests.classList.toggle(
            "hidden",
            state.requests.length > 0,
        );

        state.requests.forEach((request) => {
            const item = makeElement("li", "friend-row");
            const details = makeElement("div", "friend-details");
            const requestName = displayName(request.username);

            details.append(
                makeElement("p", "friend-name", requestName),
                makeElement("p", "friend-sub", request.major),
            );

            const actions = makeElement("div", "request-actions");

            actions.append(
                makeButton(
                    "Accept",
                    "page-button request-button",
                    () => {
                        const directoryEntry = usersByUsername.get(
                            request.username,
                        );

                        if (!directoryEntry) {
                            const newUser: FriendUser = {
                                username: request.username,
                                major: request.major,
                                status: "Free now",
                                schedules: [],
                            };

                            users.push(newUser);
                            usersByUsername.set(
                                request.username,
                                newUser,
                            );
                        }

                        state.friends.push({
                            username: request.username,
                        });

                        state.requests = state.requests.filter(
                            (item) => item.id !== request.id,
                        );

                        renderAll();
                    },
                    `Accept ${requestName}'s request`,
                ),
                makeButton(
                    "Decline",
                    "secondary-button request-button",
                    () => {
                        state.requests = state.requests.filter(
                            (item) => item.id !== request.id,
                        );

                        renderRequests();
                    },
                    `Decline ${requestName}'s request`,
                ),
            );

            item.append(details, actions);
            requestList.append(item);
        });
    };

    const renderFriends = (): void => {
        friendsList.replaceChildren();
        friendCount.textContent = String(state.friends.length);

        noFriends.classList.toggle(
            "hidden",
            state.friends.length > 0,
        );

        state.friends.forEach((friend) => {
            const user = usersByUsername.get(friend.username);
            const count = user?.schedules.length ?? 0;

            const status =
                `${count} shared ${count === 1 ? "schedule" : "schedules"}`;

            const friendName = displayName(friend.username);
            const item = makeElement("li", "friend-row");
            const details = makeElement("div", "friend-details");

            details.append(
                makeElement("p", "friend-name", friendName),
                makeElement("p", "friend-sub", status),
            );

            const removeButton = makeButton(
                "Remove",
                "friend-remove",
                () => {
                    state.friends = state.friends.filter(
                        (item) => item.username !== friend.username,
                    );

                    Object.values(state.viewers).forEach((viewers) => {
                        const viewerIndex = viewers.indexOf(
                            friend.username,
                        );

                        if (viewerIndex >= 0) {
                            viewers.splice(viewerIndex, 1);
                        }
                    });

                    if (state.selectedFriend === friend.username) {
                        state.selectedFriend =
                            state.friends[0]?.username ?? "";
                    }

                    renderAll();
                },
                `Remove ${friendName} from friends`,
            );

            const checkbox = makeElement("input", "friend-check");

            checkbox.type = "checkbox";
            checkbox.checked = state.selectedFriend === friend.username;

            checkbox.setAttribute(
                "aria-label",
                `Compare schedules with ${friendName}`,
            );

            checkbox.addEventListener("change", () => {
                state.selectedFriend = checkbox.checked
                    ? friend.username
                    : "";

                renderFriends();
                renderCalendar();
                void renderFreePeriods();
            });

            item.append(details, removeButton, checkbox);
            friendsList.append(item);
        });
    };

    const renderViewers = (): void => {
        const schedule = schedules.find(
            (item) => item.id === state.selectedScheduleId,
        );

        scheduleViewers.replaceChildren();

        if (!schedule) {
            addScheduleViewer.replaceChildren();
            addScheduleViewerButton.disabled = true;
            noScheduleViewers.classList.remove("hidden");

            sharingStatus.textContent =
                "Create a schedule to share it with friends.";

            return;
        }

        const viewers = state.viewers[schedule.id] ?? [];

        noScheduleViewers.classList.toggle(
            "hidden",
            viewers.length > 0,
        );

        addScheduleViewer.replaceChildren();

        const defaultOption = document.createElement("option");

        defaultOption.value = "";
        defaultOption.textContent = "Share with friend...";
        addScheduleViewer.append(defaultOption);

        state.friends.filter(
            (friend) => !viewers.includes(friend.username),
        ).forEach((friend) => {
            const option = document.createElement("option");

            option.value = friend.username;
            option.textContent = displayName(friend.username);
            addScheduleViewer.append(option);
        });

        addScheduleViewerButton.disabled =
            addScheduleViewer.options.length <= 1;

        viewers.forEach((username) => {
            const chip = makeElement(
                "span",
                "viewer-chip",
                displayName(username),
            );

            const removeButton = makeButton(
                "×",
                "viewer-remove",
                () => {
                    state.viewers[schedule.id] = viewers.filter(
                        (viewer) => viewer !== username,
                    );

                    renderViewers();
                },
                `Stop sharing with ${displayName(username)}`,
            );

            chip.append(removeButton);
            scheduleViewers.append(chip);
        });

        publicSharingToggle.checked =
            state.publicSchedules.has(schedule.id);

        sharingStatus.textContent = publicSharingToggle.checked
            ? `${schedule.name} is public and visible to anyone with its link.`
            : `${schedule.name} is shared with ${viewers.length} ${viewers.length === 1 ? "friend" : "friends"}.`;
    };

    const renderSharedSchedulePicker = (): void => {
        sharedSchedulePicker.replaceChildren();

        schedules.forEach((schedule) => {
            const option = document.createElement("option");

            option.value = schedule.id;
            option.textContent = schedule.name;
            sharedSchedulePicker.append(option);
        });

        if (!schedules.some(
            (schedule) => schedule.id === state.selectedScheduleId,
        )) {
            state.selectedScheduleId = schedules[0]?.id ?? "";
        }

        sharedSchedulePicker.value = state.selectedScheduleId;
    };

    const checkSelectedFriend = (): void => {
        const stillFriend = state.friends.some(
            (friend) => friend.username === state.selectedFriend,
        );

        if (state.selectedFriend && !stillFriend) {
            state.selectedFriend = state.friends[0]?.username ?? "";
        }
    };

    const { renderCalendar } = createRenderer({
        state,
        schedules,
        usersByUsername,
        displayName,
        makeElement,
    });

    const renderAll = (): void => {
        renderRequests();
        renderFriends();
        renderSharedSchedulePicker();
        renderViewers();
        checkSelectedFriend();
        renderCalendar();
        void renderFreePeriods();
    };

    friendForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();

        const enteredName = usernameInput.value.trim().replace(/^@/, "");
        searchMessage.className = "text-sm";

        if (!enteredName) {
            searchMessage.textContent =
                "Enter a username to send a friend request.";

            searchMessage.classList.add("text-red-600");
            return;
        }

        try {
            const result = await apiRequest<{ message: string }>(
                "/api/friends/requests",
                {
                    method: "POST",
                    body: JSON.stringify({ username: enteredName }),
                },
            );

            usernameInput.value = "";
            searchMessage.textContent = result.message;
            searchMessage.classList.add("text-purple-700");
        } catch (error) {
            searchMessage.textContent = errorMessage(error);
            searchMessage.classList.add("text-red-600");
        }
    });

    sharedSchedulePicker.addEventListener("change", () => {
        state.selectedScheduleId = sharedSchedulePicker.value;
        renderViewers();
    });

    addScheduleViewerButton.addEventListener("click", () => {
        const username = addScheduleViewer.value;

        if (!username) {
            return;
        }

        const viewers = state.viewers[state.selectedScheduleId];

        if (viewers && !viewers.includes(username)) {
            viewers.push(username);
        }

        renderViewers();
    });

    publicSharingToggle.addEventListener("change", () => {
        if (publicSharingToggle.checked) {
            state.publicSchedules.add(state.selectedScheduleId);
        } else {
            state.publicSchedules.delete(state.selectedScheduleId);
        }

        renderViewers();
    });

    requiredElement("#day-previous").addEventListener("click", () => {
        state.selectedDay = (state.selectedDay + 6) % 7;
        state.dayPicked = true;
        renderCalendar();
    });

    requiredElement("#day-next").addEventListener("click", () => {
        state.selectedDay = (state.selectedDay + 1) % 7;
        state.dayPicked = true;
        renderCalendar();
    });

    const showTab = (name: string): void => {
        document.querySelectorAll(".friends-panel").forEach((panel) => {
            panel.classList.toggle(
                "hidden",
                panel.id !== `tab-${name}`,
            );
        });

        document.querySelectorAll<HTMLElement>(
            ".friends-tab",
        ).forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.tab === name);
        });
    };

    document.querySelectorAll<HTMLElement>(
        "[data-tab]",
    ).forEach((button) => {
        button.addEventListener("click", () => {
            showTab(button.dataset.tab ?? "friends");
        });
    });

    [freeTimeStart, freeTimeEnd].forEach((input) => {
        input.addEventListener("input", renderFreePeriods);
        input.addEventListener("change", renderFreePeriods);
    });

    minimumFreeDuration.addEventListener("change", renderFreePeriods);

    renderAll();
}
