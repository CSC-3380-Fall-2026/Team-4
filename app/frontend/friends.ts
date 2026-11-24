import { requiredElement } from "./dom.js";
import {
    apiRequest,
    errorMessage,
    formatTime,
    getUserById,
    loadScheduleData,
    scheduleState,
    toMinutes,
} from "./schedule-data.js";
import { createRenderer } from "./friends-calendar.js";
import { makeElement } from "./friends-types.js";
import type {
    FreeCard,
    FriendLists,
    FriendState,
    ScheduleShare,
} from "./friends-types.js";
import type {
    Schedule,
    ScheduleUser,
    SharedFreeTime,
} from "./types.js";

// Friend requests, friends, and schedule sharing are all stored on the server.
const searchMessage = requiredElement("#friend-search-message");

const showMessage = (
    element: HTMLElement,
    text: string,
    isError = false,
): void => {
    element.textContent = text;
    element.className = `text-sm ${isError ? "text-red-600" : "text-purple-700"}`;
};

const fetchLists = (): Promise<[FriendLists, ScheduleShare[]]> => Promise.all([
    apiRequest<FriendLists>("/api/friends/list"),
    apiRequest<ScheduleShare[]>("/api/friends/shares"),
]);

Promise.all([loadScheduleData(), fetchLists()])
    .then(([, [lists, shares]]) => initializeFriends(lists, shares))
    .catch((error: unknown) => {
        showMessage(searchMessage, errorMessage(error), true);
    });

function initializeFriends(
    initialLists: FriendLists,
    initialShares: ScheduleShare[],
): void {
    // Shared with the calendar renderer, so they are refilled in place on refresh.
    const schedules: Schedule[] = [];
    const usersById = new Map<string | number, ScheduleUser>();
    const state: FriendState = {
        incoming: [],
        outgoing: [],
        friends: [],
        shares: [],
        selectedScheduleId: "",
        selectedFriendScheduleId: "",
        selectedFriend: null,
        // starts on today
        selectedDay: (new Date().getDay() + 6) % 7,
        dayPicked: false,
        freeDays: [],
    };

    const requestList = requiredElement("#pending-requests");
    const friendsList = requiredElement("#friends-list");
    const requestCount = requiredElement("#pending-request-count");
    const noRequests = requiredElement("#no-pending-requests");
    const noFriends = requiredElement("#no-friends");
    const friendForm = requiredElement<HTMLFormElement>("#find-friend-form");
    const usernameInput = requiredElement<HTMLInputElement>("#friend-username");
    const sharedSchedulePicker = requiredElement<HTMLSelectElement>(
        "#shared-schedule-picker",
    );
    const friendSchedulePicker = requiredElement<HTMLSelectElement>(
        "#friend-schedule-picker",
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
    const inviteButton = requiredElement<HTMLButtonElement>(
        '[form="find-friend-form"]',
    );
    const freeTimeStart = requiredElement<HTMLInputElement>("#free-time-start");
    const freeTimeEnd = requiredElement<HTMLInputElement>("#free-time-end");
    const minimumFreeDuration = requiredElement<HTMLSelectElement>(
        "#minimum-free-duration",
    );
    const freePeriods = requiredElement("#free-periods");
    let freeTimeRequestSequence = 0;

    const dayNames = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ];

    // "14:00", "15:30" -> "2:00–3:30 PM"
    const formatRange = (start: string, end: string): string => {
        const startText = formatTime(start)
            .replace(" AM", "")
            .replace(" PM", "");

        return `${startText}–${formatTime(end)}`;
    };

    // "Tuesday" -> "TUE, OCT 21" using the date in the current week
    const formatDay = (dayName: string): string => {
        const today = new Date();
        const daysSinceMonday = (today.getDay() + 6) % 7;
        const date = new Date(today);

        date.setDate(
            today.getDate() - daysSinceMonday + dayNames.indexOf(dayName),
        );

        const month = date.toLocaleDateString("en-US", { month: "short" });
        return `${dayName.slice(0, 3)}, ${month} ${date.getDate()}`.toUpperCase();
    };

    // 90 -> "90 minutes", 120 -> "2 hours"
    const formatLength = (duration: number): string => {
        if (duration < 120) {
            return `${duration} minutes`;
        }

        const hours = duration / 60;
        return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} hours`;
    };

    const displayName = (userId: string | null): string => state.friends.find(
        (friend) => friend.user_id === userId,
    )?.username ?? "Friend";

    const sharedCount = (userId: string): number =>
        usersById.get(userId)?.schedules.length ?? 0;

    const makeButton = (
        text: string,
        classes: string,
        action: () => Promise<void>,
        label: string,
    ): HTMLButtonElement => {
        const button = makeElement("button", classes, text);
        button.type = "button";
        button.setAttribute("aria-label", label);

        button.addEventListener("click", async () => {
            button.disabled = true;

            try {
                await action();
            } finally {
                button.disabled = false;
            }
        });

        return button;
    };

    // Run a server change, show its outcome, then reload everything from the server.
    const perform = async (
        request: () => Promise<{ message?: string } | undefined>,
        element: HTMLElement,
        success?: string,
    ): Promise<void> => {
        try {
            const result = await request();
            showMessage(element, success ?? result?.message ?? "Done.");
        } catch (error) {
            showMessage(element, errorMessage(error), true);
        }

        await refresh();
    };

    const applyData = (lists: FriendLists, shares: ScheduleShare[]): void => {
        const currentUser = getUserById(scheduleState.currentUserId);
        schedules.splice(0, schedules.length, ...(currentUser?.schedules ?? []));
        usersById.clear();

        scheduleState.users
            .filter((user) => user.id !== scheduleState.currentUserId)
            .forEach((user) => usersById.set(user.id, user));

        state.incoming = lists.incoming_requests;
        state.outgoing = lists.outgoing_requests;
        state.friends = lists.friends;
        state.shares = shares;

        if (!schedules.some((schedule) => schedule.id === state.selectedScheduleId)) {
            state.selectedScheduleId = schedules[0]?.id ?? "";
        }

        const stillFriend = state.friends.some(
            (friend) => friend.user_id === state.selectedFriend,
        );

        if (state.selectedFriend !== "" && !stillFriend) {
            state.selectedFriend = state.friends[0]?.user_id ?? "";
        }
    };

    const refresh = async (): Promise<void> => {
        try {
            const [lists, shares] = await fetchLists();
            await loadScheduleData();
            applyData(lists, shares);
        } catch (error) {
            showMessage(searchMessage, errorMessage(error), true);
        }

        renderAll();
    };

    const friendItem = (name: string, subtitle: string): HTMLLIElement => {
        const item = makeElement("li", "friend-row");
        const details = makeElement("div", "friend-details");

        details.append(
            makeElement("p", "friend-name", name),
            makeElement("p", "friend-sub", subtitle),
        );

        item.append(details);
        return item;
    };

    const requestItem = (
        username: string,
        subtitle: string,
        buttons: HTMLButtonElement[],
    ): HTMLLIElement => {
        const item = friendItem(username, subtitle);
        const actions = makeElement("div", "request-actions");

        actions.append(...buttons);
        item.append(actions);
        return item;
    };

    const renderRequests = (): void => {
        requestList.replaceChildren();
        // the number next to the Requests tab
        requestCount.textContent = state.incoming.length
            ? String(state.incoming.length)
            : "";
        noRequests.classList.toggle(
            "hidden",
            state.incoming.length + state.outgoing.length > 0,
        );

        state.incoming.forEach((request) => {
            requestList.append(requestItem(request.username, "Wants to be your friend", [
                makeButton("Accept", "page-button request-button", () => perform(
                    () => apiRequest(
                        `/api/friends/requests/${request.id}/accept`,
                        { method: "POST" },
                    ),
                    searchMessage,
                    `You and ${request.username} are now friends.`,
                ), `Accept friend request from ${request.username}`),
                makeButton("Decline", "secondary-button request-button", () => perform(
                    () => apiRequest(
                        `/api/friends/requests/${request.id}`,
                        { method: "DELETE" },
                    ),
                    searchMessage,
                ), `Decline friend request from ${request.username}`),
            ]));
        });

        state.outgoing.forEach((request) => {
            requestList.append(requestItem(
                request.username,
                "Request sent, waiting for a reply",
                [
                    makeButton("Cancel", "secondary-button request-button", () => perform(
                        () => apiRequest(
                            `/api/friends/requests/${request.id}`,
                            { method: "DELETE" },
                        ),
                        searchMessage,
                    ), `Cancel friend request to ${request.username}`),
                ],
            ));
        });
    };

    const renderFriends = (): void => {
        friendsList.replaceChildren();
        friendCount.textContent = String(state.friends.length);
        noFriends.classList.toggle("hidden", state.friends.length > 0);

        state.friends.forEach((friend) => {
            const count = sharedCount(friend.user_id);
            const status = count
                ? `Shared ${count} ${count === 1 ? "schedule" : "schedules"} with you`
                : "Hasn't shared a schedule with you yet";
            const item = friendItem(friend.username, status);

            const removeButton = makeButton("Remove", "friend-remove", async () => {
                if (!window.confirm(
                    `Remove ${friend.username} as a friend? They will no longer see schedules you shared with them.`,
                )) {
                    return;
                }

                await perform(
                    () => apiRequest(`/api/friends/${friend.id}`, { method: "DELETE" }),
                    searchMessage,
                    `${friend.username} was removed from your friends.`,
                );
            }, `Remove ${friend.username} as a friend`);

            // The check box picks who you compare with. The free time API only takes
            // one friend at a time, so checking one friend unchecks the other ones.
            const checkbox = makeElement("input", "friend-check");
            checkbox.type = "checkbox";
            checkbox.checked = state.selectedFriend === friend.user_id;
            checkbox.setAttribute("aria-label", `Compare schedules with ${friend.username}`);

            checkbox.addEventListener("change", () => {
                state.selectedFriend = checkbox.checked ? friend.user_id : "";
                renderFriends();
                renderFriendSchedulePicker();
                renderCalendar();
                void renderFreePeriods();
            });

            item.append(removeButton, checkbox);
            friendsList.append(item);
        });
    };

    // Fill a picker with schedules, or one disabled placeholder when there are none.
    const fillPicker = (
        picker: HTMLSelectElement,
        options: Schedule[],
        emptyText: string,
        value: string,
    ): void => {
        picker.replaceChildren();

        options.forEach((schedule) => {
            const option = document.createElement("option");
            option.value = schedule.id;
            option.textContent = schedule.name;
            picker.append(option);
        });

        if (options.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = emptyText;
            picker.append(option);
        }

        picker.disabled = options.length === 0;
        picker.value = value;
    };

    const renderSharedSchedulePicker = (): void => {
        fillPicker(
            sharedSchedulePicker,
            schedules,
            "No schedules yet",
            state.selectedScheduleId,
        );
    };

    // same look as the schedule picker above, filled with the checked friend's shared schedules
    const renderFriendSchedulePicker = (): void => {
        const friendSchedules = state.selectedFriend
            ? usersById.get(state.selectedFriend)?.schedules ?? []
            : [];

        if (!friendSchedules.some(
            (schedule) => schedule.id === state.selectedFriendScheduleId,
        )) {
            state.selectedFriendScheduleId = friendSchedules[0]?.id ?? "";
        }

        fillPicker(
            friendSchedulePicker,
            friendSchedules,
            "Nothing shared yet",
            state.selectedFriendScheduleId,
        );
    };

    const renderViewers = (): void => {
        scheduleViewers.replaceChildren();
        addScheduleViewer.replaceChildren();

        const schedule = schedules.find(
            (item) => item.id === state.selectedScheduleId,
        );
        const viewers = schedule
            ? state.shares.filter((share) => share.schedule_id === schedule.id)
            : [];
        const viewerIds = new Set(viewers.map((share) => share.friend_id));
        const available = state.friends.filter(
            (friend) => !viewerIds.has(friend.user_id),
        );

        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = state.friends.length
            ? "Share with friend..."
            : "Add a friend first";
        addScheduleViewer.append(defaultOption);

        available.forEach((friend) => {
            const option = document.createElement("option");
            option.value = friend.user_id;
            option.textContent = friend.username;
            addScheduleViewer.append(option);
        });

        const canShare = Boolean(schedule) && available.length > 0;
        addScheduleViewer.disabled = !canShare;
        addScheduleViewerButton.disabled = !canShare;
        noScheduleViewers.classList.toggle("hidden", viewers.length > 0);

        if (!schedule) {
            showMessage(
                sharingStatus,
                "Create a schedule on the Schedule page to share it with friends.",
            );
            return;
        }

        viewers.forEach((share) => {
            const chip = makeElement("span", "viewer-chip", share.username);

            chip.append(makeButton("×", "viewer-remove", () => perform(
                () => apiRequest(`/api/friends/shares/${share.id}`, { method: "DELETE" }),
                sharingStatus,
                `Stopped sharing ${schedule.name} with ${share.username}.`,
            ), `Stop sharing with ${share.username}`));

            scheduleViewers.append(chip);
        });

        if (!sharingStatus.textContent) {
            sharingStatus.textContent = viewers.length === 0
                ? `${schedule.name} is private.`
                : `${schedule.name} is shared with ${viewers.length} ${viewers.length === 1 ? "friend" : "friends"}.`;
        }
    };

    const showFreeMessage = (message: string, isError = false): void => {
        freePeriods.replaceChildren();
        freePeriods.className = isError
            ? "plan-cards plan-message plan-error"
            : "plan-cards plan-message";
        freePeriods.textContent = message;
    };

    const clearFreeTime = (message: string): void => {
        state.freeDays = [];
        freeTotal.textContent = "Shared free time this week";
        showFreeMessage(message);
        renderCalendar();
    };

    const renderFreeCards = (cards: FreeCard[]): void => {
        freePeriods.className = "plan-cards";
        freePeriods.replaceChildren();

        // the design has room for 3 cards, the first one is the gold "Best match"
        // longest first, so the first card really is the best match
        [...cards].sort((a, b) => b.duration - a.duration).slice(0, 3).forEach((card, index) => {
            const isBest = index === 0;
            const item = makeElement(
                "article",
                isBest ? "plan-card plan-best" : "plan-card",
            );
            const link = makeElement("a", "plan-button", "Make a plan ↗");
            link.href = "/schedule";

            item.append(
                makeElement("p", "plan-day", formatDay(card.day)),
                makeElement("p", "plan-time", formatRange(card.start, card.end)),
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
    };

    const renderFreePeriods = async (): Promise<void> => {
        const requestSequence = ++freeTimeRequestSequence;

        if (!state.selectedFriend) {
            clearFreeTime(state.friends.length > 0
                ? "Check a friend to compare shared free time."
                : "Add a friend to compare shared free time.");
            return;
        }

        const friendUser = usersById.get(state.selectedFriend);

        if (!friendUser) {
            clearFreeTime(
                `${displayName(state.selectedFriend)} hasn't shared a schedule with you yet, so there is nothing to compare.`,
            );
            return;
        }

        try {
            const result = await apiRequest<SharedFreeTime>("/api/shared-free-time", {
                method: "POST",
                // one of your schedules against one of the friend's, both picked under Sharing settings
                body: JSON.stringify({
                    friendId: friendUser.id,
                    scheduleId: state.selectedScheduleId || null,
                    friendScheduleId: state.selectedFriendScheduleId || null,
                    startTime: freeTimeStart.value,
                    endTime: freeTimeEnd.value,
                    minimumDuration: Number(minimumFreeDuration.value),
                }),
            });

            if (requestSequence !== freeTimeRequestSequence) {
                return;
            }

            state.freeDays = result.days;

            // show the day of the first free period so the gold part is on screen right away
            if (!state.dayPicked && result.days.length > 0) {
                state.selectedDay = dayNames.indexOf(result.days[0].day);
            }

            renderCalendar();

            if (result.days.length === 0) {
                freeTotal.textContent = "0 hours of shared free time this week";
                showFreeMessage(
                    `No shared free periods of at least ${minimumFreeDuration.value} minutes within the selected hours.`,
                );
                return;
            }

            // one card for each free period, and add up the total for the line under the heading
            const cards: FreeCard[] = result.days.flatMap(({ day, periods }) =>
                periods.map(({ start, end }) => ({
                    day,
                    start,
                    end,
                    duration: toMinutes(end) - toMinutes(start),
                })));
            const totalMinutes = cards.reduce((sum, card) => sum + card.duration, 0);
            const totalHours = Math.round((totalMinutes / 60) * 10) / 10;

            freeTotal.textContent = `${totalHours} hours of shared free time this week`;
            renderFreeCards(cards);
        } catch (error) {
            if (requestSequence !== freeTimeRequestSequence) {
                return;
            }

            state.freeDays = [];
            renderCalendar();
            showFreeMessage(errorMessage(error), true);
        }
    };

    const { renderCalendar } = createRenderer({
        state,
        schedules,
        usersById,
        displayName,
        makeElement,
    });

    const renderAll = (): void => {
        renderRequests();
        renderFriends();
        renderSharedSchedulePicker();
        renderFriendSchedulePicker();
        renderViewers();
        renderCalendar();
        void renderFreePeriods();
    };

    friendForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const enteredName = usernameInput.value.trim().replace(/^@/, "");

        if (!enteredName) {
            showMessage(searchMessage, "Enter a username to send a friend request.", true);
            return;
        }

        inviteButton.disabled = true;

        try {
            const result = await apiRequest<{ message: string }>("/api/friends/requests", {
                method: "POST",
                body: JSON.stringify({ username: enteredName }),
            });

            usernameInput.value = "";
            showMessage(searchMessage, result.message);
            await refresh();
        } catch (error) {
            showMessage(searchMessage, errorMessage(error), true);
        } finally {
            inviteButton.disabled = false;
        }
    });

    sharedSchedulePicker.addEventListener("change", () => {
        state.selectedScheduleId = sharedSchedulePicker.value;
        sharingStatus.textContent = "";
        renderViewers();
        renderCalendar();
        void renderFreePeriods();
    });

    friendSchedulePicker.addEventListener("change", () => {
        state.selectedFriendScheduleId = friendSchedulePicker.value;
        renderCalendar();
        void renderFreePeriods();
    });

    addScheduleViewerButton.addEventListener("click", async () => {
        const friendId = addScheduleViewer.value;
        const schedule = schedules.find(
            (item) => item.id === state.selectedScheduleId,
        );

        if (!friendId || !schedule) {
            showMessage(sharingStatus, "Choose a friend to share with.", true);
            return;
        }

        addScheduleViewerButton.disabled = true;

        await perform(
            () => apiRequest("/api/friends/shares", {
                method: "POST",
                body: JSON.stringify({ schedule_id: schedule.id, friend_id: friendId }),
            }),
            sharingStatus,
            `${schedule.name} is now shared with ${displayName(friendId)}.`,
        );
    });

    // the arrows next to the date move the overlap chart one day back or forward
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

    // Friends / Requests / Sharing settings tabs. Anything with data-tab switches the panel.
    const showTab = (name: string): void => {
        document.querySelectorAll(".friends-panel").forEach((panel) => {
            panel.classList.toggle("hidden", panel.id !== `tab-${name}`);
        });

        document.querySelectorAll<HTMLElement>(".friends-tab").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.tab === name);
            tab.setAttribute("aria-pressed", String(tab.dataset.tab === name));
        });
    };

    document.querySelectorAll<HTMLElement>("[data-tab]").forEach((button) => {
        button.addEventListener("click", () => showTab(button.dataset.tab ?? ""));
    });

    [freeTimeStart, freeTimeEnd].forEach((input) => {
        input.addEventListener("input", () => void renderFreePeriods());
        input.addEventListener("change", () => void renderFreePeriods());
    });

    minimumFreeDuration.addEventListener("change", () => void renderFreePeriods());

    applyData(initialLists, initialShares);
    renderAll();
}
