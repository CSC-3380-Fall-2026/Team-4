(() => {
    // Friend requests, friends, and schedule sharing are all stored on the server.
    const { apiRequest, scheduleState, getUserById, loadScheduleData } = window.SchedulePrototype;
    const searchMessage = document.querySelector("#friend-search-message");

    const showMessage = (element, text, isError = false) => {
        element.textContent = text;
        element.className = `text-sm ${isError ? "text-red-600" : "text-purple-700"}`;
    };

    const fetchLists = () => Promise.all([
        apiRequest("/api/friends/list"),
        apiRequest("/api/friends/shares"),
    ]);

    Promise.all([loadScheduleData(), fetchLists()])
        .then(([, [lists, shares]]) => initializeFriends(lists, shares))
        .catch((error) => showMessage(searchMessage, error.message, true));

    function initializeFriends(initialLists, initialShares) {
    // Shared with the calendar renderer, so they are refilled in place on refresh.
    const schedules = [];
    const usersById = new Map();
    const state = {
        incoming: [],
        outgoing: [],
        friends: [],
        shares: [],
        selectedScheduleId: "",
        // which of the checked friend's shared schedules to compare with
        selectedFriendScheduleId: "",
        // null until the first load picks a friend; "" means the student unchecked everyone
        selectedFriend: null,
        // which day the overlap chart shows, 0 = Monday. Starts on today.
        selectedDay: (new Date().getDay() + 6) % 7,
        // turns true when the day arrows are pressed, after that the day stays put
        dayPicked: false,
        // the last answer from /api/shared-free-time so the chart can draw the gold parts
        freeDays: [],
    };

    const requestList = document.querySelector("#pending-requests");
    const friendsList = document.querySelector("#friends-list");
    const requestCount = document.querySelector("#pending-request-count");
    const noRequests = document.querySelector("#no-pending-requests");
    const noFriends = document.querySelector("#no-friends");
    const friendForm = document.querySelector("#find-friend-form");
    const usernameInput = document.querySelector("#friend-username");
    const sharedSchedulePicker = document.querySelector("#shared-schedule-picker");
    const friendSchedulePicker = document.querySelector("#friend-schedule-picker");
    const scheduleViewers = document.querySelector("#schedule-viewers");
    const addScheduleViewer = document.querySelector("#add-schedule-viewer");
    const addScheduleViewerButton = document.querySelector("#add-schedule-viewer-button");
    const noScheduleViewers = document.querySelector("#no-schedule-viewers");
    const sharingStatus = document.querySelector("#sharing-status");
    const friendCount = document.querySelector("#friend-count");
    const freeTotal = document.querySelector("#free-total");
    const inviteButton = document.querySelector('[form="find-friend-form"]');
    const freeTimeStart = document.querySelector("#free-time-start");
    const freeTimeEnd = document.querySelector("#free-time-end");
    const minimumFreeDuration = document.querySelector("#minimum-free-duration");
    const freePeriods = document.querySelector("#free-periods");
    let freeTimeRequestSequence = 0;

    const makeElement = (tag, classes, text) => {
        const element = document.createElement(tag);
        element.className = classes;
        if (text !== undefined) {
            element.textContent = text;
        }
        return element;
    };

    const formatTime = (time) => {
        const [hours, minutes] = time.split(":").map(Number);
        const period = hours < 12 ? "AM" : "PM";
        return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${period}`;
    };

    const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

    const toMinutes = (time) => {
        const [hours, minutes] = time.split(":").map(Number);
        return hours * 60 + minutes;
    };

    // "14:00", "15:30" -> "2:00–3:30 PM"
    const formatRange = (start, end) => {
        const startText = formatTime(start).replace(" AM", "").replace(" PM", "");
        return `${startText}–${formatTime(end)}`;
    };

    // "Tuesday" -> "TUE, OCT 21" using the date in the current week
    const formatDay = (dayName) => {
        const today = new Date();
        const daysSinceMonday = (today.getDay() + 6) % 7;
        const date = new Date(today);
        date.setDate(today.getDate() - daysSinceMonday + dayNames.indexOf(dayName));
        const month = date.toLocaleDateString("en-US", { month: "short" });
        return `${dayName.slice(0, 3)}, ${month} ${date.getDate()}`.toUpperCase();
    };

    // 90 -> "90 minutes", 120 -> "2 hours"
    const formatLength = (duration) => {
        if (duration < 120) {
            return `${duration} minutes`;
        }
        const hours = duration / 60;
        return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} hours`;
    };

    const friendById = (userId) => state.friends.find((friend) => friend.user_id === userId);
    const displayName = (userId) => friendById(userId)?.username ?? "Friend";
    const sharedCount = (userId) => usersById.get(userId)?.schedules.length ?? 0;

    const makeButton = (text, classes, action, label) => {
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
    const perform = async (request, element, success) => {
        try {
            const result = await request();
            showMessage(element, success ?? result?.message ?? "Done.");
        } catch (error) {
            showMessage(element, error.message, true);
        }
        await refresh();
    };

    const applyData = (lists, shares) => {
        const currentUser = getUserById(scheduleState.currentUserId);
        schedules.splice(0, schedules.length, ...(currentUser?.schedules ?? []));
        usersById.clear();
        scheduleState.sampleUsers
            .filter((user) => user.id !== scheduleState.currentUserId)
            .forEach((user) => usersById.set(user.id, user));
        state.incoming = lists.incoming_requests;
        state.outgoing = lists.outgoing_requests;
        state.friends = lists.friends;
        state.shares = shares;
        if (!schedules.some((schedule) => schedule.id === state.selectedScheduleId)) {
            state.selectedScheduleId = schedules[0]?.id ?? "";
        }
        const stillFriend = state.friends.some((friend) => friend.user_id === state.selectedFriend);
        if (state.selectedFriend !== "" && !stillFriend) {
            state.selectedFriend = state.friends[0]?.user_id ?? "";
        }
    };

    const refresh = async () => {
        try {
            const [lists, shares] = await fetchLists();
            await loadScheduleData();
            applyData(lists, shares);
        } catch (error) {
            showMessage(searchMessage, error.message, true);
        }
        renderAll();
    };

    const friendItem = (name, subtitle) => {
        const item = makeElement("li", "friend-row");
        const details = makeElement("div", "friend-details");
        details.append(
            makeElement("p", "friend-name", name),
            makeElement("p", "friend-sub", subtitle),
        );
        item.append(details);
        return item;
    };

    const requestItem = (request, subtitle, buttons) => {
        const item = friendItem(request.username, subtitle);
        const actions = makeElement("div", "request-actions");
        actions.append(...buttons);
        item.append(actions);
        return item;
    };

    const renderRequests = () => {
        requestList.replaceChildren();
        // the number next to the Requests tab
        requestCount.textContent = state.incoming.length ? String(state.incoming.length) : "";
        noRequests.classList.toggle("hidden", state.incoming.length + state.outgoing.length > 0);
        state.incoming.forEach((request) => {
            requestList.append(requestItem(request, "Wants to be your friend", [
                makeButton("Accept", "page-button request-button", () => perform(
                    () => apiRequest(`/api/friends/requests/${request.id}/accept`, { method: "POST" }),
                    searchMessage,
                    `You and ${request.username} are now friends.`,
                ), `Accept friend request from ${request.username}`),
                makeButton("Decline", "secondary-button request-button", () => perform(
                    () => apiRequest(`/api/friends/requests/${request.id}`, { method: "DELETE" }),
                    searchMessage,
                ), `Decline friend request from ${request.username}`),
            ]));
        });
        state.outgoing.forEach((request) => {
            requestList.append(requestItem(request, "Request sent, waiting for a reply", [
                makeButton("Cancel", "secondary-button request-button", () => perform(
                    () => apiRequest(`/api/friends/requests/${request.id}`, { method: "DELETE" }),
                    searchMessage,
                ), `Cancel friend request to ${request.username}`),
            ]));
        });
    };

    const renderFriends = () => {
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
                if (!window.confirm(`Remove ${friend.username} as a friend? They will no longer see schedules you shared with them.`)) {
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
                renderFreePeriods();
            });

            item.append(removeButton, checkbox);
            friendsList.append(item);
        });
    };

    const renderSharedSchedulePicker = () => {
        sharedSchedulePicker.replaceChildren();
        schedules.forEach((schedule) => {
            const option = document.createElement("option");
            option.value = schedule.id;
            option.textContent = schedule.name;
            sharedSchedulePicker.append(option);
        });
        if (schedules.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "No schedules yet";
            sharedSchedulePicker.append(option);
        }
        sharedSchedulePicker.disabled = schedules.length === 0;
        sharedSchedulePicker.value = state.selectedScheduleId;
    };

    // same look as the schedule picker above, filled with the checked friend's shared schedules
    const renderFriendSchedulePicker = () => {
        const friendSchedules = usersById.get(state.selectedFriend)?.schedules ?? [];
        if (!friendSchedules.some((schedule) => schedule.id === state.selectedFriendScheduleId)) {
            state.selectedFriendScheduleId = friendSchedules[0]?.id ?? "";
        }
        friendSchedulePicker.replaceChildren();
        friendSchedules.forEach((schedule) => {
            const option = document.createElement("option");
            option.value = schedule.id;
            option.textContent = schedule.name;
            friendSchedulePicker.append(option);
        });
        if (friendSchedules.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Nothing shared yet";
            friendSchedulePicker.append(option);
        }
        friendSchedulePicker.disabled = friendSchedules.length === 0;
        friendSchedulePicker.value = state.selectedFriendScheduleId;
    };

    const renderViewers = () => {
        scheduleViewers.replaceChildren();
        addScheduleViewer.replaceChildren();
        const schedule = schedules.find((item) => item.id === state.selectedScheduleId);
        const viewers = schedule
            ? state.shares.filter((share) => share.schedule_id === schedule.id)
            : [];
        const viewerIds = new Set(viewers.map((share) => share.friend_id));
        const available = state.friends.filter((friend) => !viewerIds.has(friend.user_id));
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = state.friends.length ? "Share with friend..." : "Add a friend first";
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
        viewers.forEach((share) => {
            const chip = makeElement("span", "viewer-chip", share.username);
            chip.append(makeButton("×", "viewer-remove", () => perform(
                () => apiRequest(`/api/friends/shares/${share.id}`, { method: "DELETE" }),
                sharingStatus,
                `Stopped sharing ${schedule.name} with ${share.username}.`,
            ), `Stop sharing with ${share.username}`));
            scheduleViewers.append(chip);
        });
        if (!schedule) {
            showMessage(sharingStatus, "Create a schedule on the Schedule page to share it with friends.");
        } else if (!sharingStatus.textContent) {
            sharingStatus.textContent = viewers.length === 0
                ? `${schedule.name} is private.`
                : `${schedule.name} is shared with ${viewers.length} ${viewers.length === 1 ? "friend" : "friends"}.`;
        }
    };

    const showFreeMessage = (message, isError = false) => {
        freePeriods.replaceChildren();
        freePeriods.className = isError ? "plan-cards plan-message plan-error" : "plan-cards plan-message";
        freePeriods.textContent = message;
    };

    const clearFreeTime = (message) => {
        state.freeDays = [];
        freeTotal.textContent = "Shared free time this week";
        showFreeMessage(message);
        renderCalendar();
    };

    const renderFreePeriods = async () => {
        const requestSequence = ++freeTimeRequestSequence;
        if (!state.selectedFriend) {
            clearFreeTime(state.friends.length > 0
                ? "Check a friend to compare shared free time."
                : "Add a friend to compare shared free time.");
            return;
        }
        const friendUser = usersById.get(state.selectedFriend);
        if (!friendUser) {
            clearFreeTime(`${displayName(state.selectedFriend)} hasn't shared a schedule with you yet, so there is nothing to compare.`);
            return;
        }
        try {
            const result = await apiRequest("/api/shared-free-time", {
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
                showFreeMessage(`No shared free periods of at least ${minimumFreeDuration.value} minutes within the selected hours.`);
                return;
            }

            // one card for each free period, and add up the total for the line under the heading
            const cards = [];
            let totalMinutes = 0;
            result.days.forEach(({ day, periods }) => {
                periods.forEach(({ start, end }) => {
                    const duration = toMinutes(end) - toMinutes(start);
                    totalMinutes += duration;
                    cards.push({ day, start, end, duration });
                });
            });
            const totalHours = Math.round((totalMinutes / 60) * 10) / 10;
            freeTotal.textContent = `${totalHours} hours of shared free time this week`;

            freePeriods.className = "plan-cards";
            freePeriods.replaceChildren();
            // the design has room for 3 cards, the first one is the gold "Best match"
            cards.slice(0, 3).forEach((card, index) => {
                const isBest = index === 0;
                const item = makeElement("article", isBest ? "plan-card plan-best" : "plan-card");
                const link = makeElement("a", "plan-button", "Make a plan ↗");
                link.href = "/schedule";
                item.append(
                    makeElement("p", "plan-day", formatDay(card.day)),
                    makeElement("p", "plan-time", formatRange(card.start, card.end)),
                    makeElement(
                        "p",
                        "plan-length",
                        isBest ? `${formatLength(card.duration)} · Best match` : `${formatLength(card.duration)} together`,
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
            showFreeMessage(error.message, true);
        }
    };

    const { renderCalendar } = window.FriendsCalendar.createRenderer({
        state,
        schedules,
        usersByUsername: usersById,
        displayName,
        makeElement,
    });

    const renderAll = () => {
        renderRequests();
        renderFriends();
        renderSharedSchedulePicker();
        renderFriendSchedulePicker();
        renderViewers();
        renderCalendar();
        renderFreePeriods();
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
            const result = await apiRequest("/api/friends/requests", {
                method: "POST",
                body: JSON.stringify({ username: enteredName }),
            });
            usernameInput.value = "";
            showMessage(searchMessage, result.message);
            await refresh();
        } catch (error) {
            showMessage(searchMessage, error.message, true);
        } finally {
            inviteButton.disabled = false;
        }
    });

    sharedSchedulePicker.addEventListener("change", () => {
        state.selectedScheduleId = sharedSchedulePicker.value;
        sharingStatus.textContent = "";
        renderViewers();
        renderCalendar();
        renderFreePeriods();
    });

    friendSchedulePicker.addEventListener("change", () => {
        state.selectedFriendScheduleId = friendSchedulePicker.value;
        renderCalendar();
        renderFreePeriods();
    });

    addScheduleViewerButton.addEventListener("click", async () => {
        const friendId = addScheduleViewer.value;
        const schedule = schedules.find((item) => item.id === state.selectedScheduleId);
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
    document.querySelector("#day-previous").addEventListener("click", () => {
        state.selectedDay = (state.selectedDay + 6) % 7;
        state.dayPicked = true;
        renderCalendar();
    });
    document.querySelector("#day-next").addEventListener("click", () => {
        state.selectedDay = (state.selectedDay + 1) % 7;
        state.dayPicked = true;
        renderCalendar();
    });

    // Friends / Requests / Sharing settings tabs. Anything with data-tab switches the panel.
    const showTab = (name) => {
        document.querySelectorAll(".friends-panel").forEach((panel) => {
            panel.classList.toggle("hidden", panel.id !== `tab-${name}`);
        });
        document.querySelectorAll(".friends-tab").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.tab === name);
            tab.setAttribute("aria-pressed", tab.dataset.tab === name);
        });
    };
    document.querySelectorAll("[data-tab]").forEach((button) => {
        button.addEventListener("click", () => showTab(button.dataset.tab));
    });
    [freeTimeStart, freeTimeEnd].forEach((input) => {
        input.addEventListener("input", renderFreePeriods);
        input.addEventListener("change", renderFreePeriods);
    });
    minimumFreeDuration.addEventListener("change", renderFreePeriods);

    applyData(initialLists, initialShares);
    renderAll();
    }
})();
