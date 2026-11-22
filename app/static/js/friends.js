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
        selectedFriend: "",
    };

    const requestList = document.querySelector("#pending-requests");
    const friendsList = document.querySelector("#friends-list");
    const requestCount = document.querySelector("#pending-request-count");
    const noRequests = document.querySelector("#no-pending-requests");
    const noFriends = document.querySelector("#no-friends");
    const friendForm = document.querySelector("#find-friend-form");
    const usernameInput = document.querySelector("#friend-username");
    const sharedSchedulePicker = document.querySelector("#shared-schedule-picker");
    const scheduleViewers = document.querySelector("#schedule-viewers");
    const addScheduleViewer = document.querySelector("#add-schedule-viewer");
    const addScheduleViewerButton = document.querySelector("#add-schedule-viewer-button");
    const noScheduleViewers = document.querySelector("#no-schedule-viewers");
    const sharingStatus = document.querySelector("#sharing-status");
    const compareFriendPicker = document.querySelector("#compare-friend-picker");
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

    const formatDuration = (start, end) => {
        const toMinutes = (time) => {
            const [hours, minutes] = time.split(":").map(Number);
            return hours * 60 + minutes;
        };
        const duration = toMinutes(end) - toMinutes(start);
        const hours = Math.floor(duration / 60);
        const minutes = duration % 60;
        if (hours === 0) {
            return `${minutes} min`;
        }
        return minutes === 0 ? `${hours} hr` : `${hours} hr ${minutes} min`;
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
        if (!state.friends.some((friend) => friend.user_id === state.selectedFriend)) {
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

    const avatar = (name) => makeElement(
        "span",
        "grid size-9 shrink-0 place-items-center rounded-full bg-purple-100 text-sm font-bold text-purple-700",
        name.charAt(0).toUpperCase(),
    );

    const requestItem = (request, subtitle, buttons) => {
        const item = makeElement("li", "flex flex-col gap-3 rounded-md border border-neutrals-100 bg-neutrals-0 p-3 sm:flex-row sm:items-center sm:justify-between");
        const identity = makeElement("div", "flex min-w-0 items-center gap-3");
        const details = makeElement("div", "min-w-0");
        details.append(
            makeElement("p", "truncate text-sm font-bold text-neutrals-800", request.username),
            makeElement("p", "text-xs text-neutrals-400", subtitle),
        );
        identity.append(avatar(request.username), details);
        const actions = makeElement("div", "flex shrink-0 gap-2");
        actions.append(...buttons);
        item.append(identity, actions);
        return item;
    };

    const renderRequests = () => {
        requestList.replaceChildren();
        requestCount.textContent = state.incoming.length ? `${state.incoming.length} new` : "";
        noRequests.classList.toggle("hidden", state.incoming.length + state.outgoing.length > 0);
        state.incoming.forEach((request) => {
            requestList.append(requestItem(request, "Wants to be your friend", [
                makeButton("Accept", "rounded-md bg-purple-400 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-purple-500", () => perform(
                    () => apiRequest(`/api/friends/requests/${request.id}/accept`, { method: "POST" }),
                    searchMessage,
                    `You and ${request.username} are now friends.`,
                ), `Accept friend request from ${request.username}`),
                makeButton("Decline", "rounded-md border border-neutrals-200 px-3 py-1.5 text-xs font-semibold text-neutrals-500 transition-colors hover:bg-yellow-50", () => perform(
                    () => apiRequest(`/api/friends/requests/${request.id}`, { method: "DELETE" }),
                    searchMessage,
                ), `Decline friend request from ${request.username}`),
            ]));
        });
        state.outgoing.forEach((request) => {
            requestList.append(requestItem(request, "Request sent, waiting for a reply", [
                makeButton("Cancel", "rounded-md border border-neutrals-200 px-3 py-1.5 text-xs font-semibold text-neutrals-500 transition-colors hover:bg-yellow-50", () => perform(
                    () => apiRequest(`/api/friends/requests/${request.id}`, { method: "DELETE" }),
                    searchMessage,
                ), `Cancel friend request to ${request.username}`),
            ]));
        });
    };

    const renderFriends = () => {
        friendsList.replaceChildren();
        noFriends.classList.toggle("hidden", state.friends.length > 0);
        state.friends.forEach((friend) => {
            const count = sharedCount(friend.user_id);
            const status = count
                ? `Shared ${count} ${count === 1 ? "schedule" : "schedules"} with you`
                : "Hasn't shared a schedule with you yet";
            const item = makeElement("li", "flex items-center justify-between gap-3 rounded-md border border-neutrals-100 bg-neutrals-0 px-3 py-2");
            const identity = makeElement("div", "flex min-w-0 items-center gap-3");
            const details = makeElement("div", "min-w-0");
            details.append(
                makeElement("p", "truncate text-sm font-bold text-neutrals-800", friend.username),
                makeElement("p", "text-xs text-neutrals-400", status),
            );
            identity.append(avatar(friend.username), details);
            const removeButton = makeButton("Remove", "shrink-0 rounded-md border border-red-300 px-3 py-1.5 text-xs font-semibold text-red-600 transition-colors hover:bg-red-50", async () => {
                if (!window.confirm(`Remove ${friend.username} as a friend? They will no longer see schedules you shared with them.`)) {
                    return;
                }
                await perform(
                    () => apiRequest(`/api/friends/${friend.id}`, { method: "DELETE" }),
                    searchMessage,
                    `${friend.username} was removed from your friends.`,
                );
            }, `Remove ${friend.username} as a friend`);
            item.append(identity, removeButton);
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
            const chip = makeElement("span", "inline-flex items-center gap-1 rounded-md bg-purple-500 px-2.5 py-1 text-xs font-medium text-white", share.username);
            chip.append(makeButton("×", "cursor-pointer text-sm leading-none text-white/80 hover:text-yellow-300", () => perform(
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

    const renderComparePicker = () => {
        compareFriendPicker.replaceChildren();
        state.friends.forEach((friend) => {
            const option = document.createElement("option");
            option.value = friend.user_id;
            option.textContent = friend.username;
            compareFriendPicker.append(option);
        });
        if (state.friends.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "No friends yet";
            compareFriendPicker.append(option);
        }
        compareFriendPicker.disabled = state.friends.length === 0;
        compareFriendPicker.value = state.selectedFriend;
        document.querySelector("#friend-legend-name").textContent = state.selectedFriend
            ? displayName(state.selectedFriend)
            : "Friend";
    };

    const showFreeNote = (text, classes = "border-dashed border-neutrals-200 bg-neutrals-50 text-neutrals-400") => {
        freePeriods.replaceChildren();
        freePeriods.className = `rounded-md border p-4 text-sm ${classes}`;
        freePeriods.textContent = text;
    };

    const renderFreePeriods = async () => {
        const requestSequence = ++freeTimeRequestSequence;
        if (!state.selectedFriend) {
            showFreeNote("Add a friend to compare shared free time.");
            return;
        }
        const friendUser = usersById.get(state.selectedFriend);
        if (!friendUser) {
            showFreeNote(`${displayName(state.selectedFriend)} hasn't shared a schedule with you yet, so there is nothing to compare.`);
            return;
        }
        try {
            const result = await apiRequest("/api/shared-free-time", {
                method: "POST",
                body: JSON.stringify({
                    friendUsername: friendUser.username,
                    startTime: freeTimeStart.value,
                    endTime: freeTimeEnd.value,
                    minimumDuration: Number(minimumFreeDuration.value),
                }),
            });
            if (requestSequence !== freeTimeRequestSequence) {
                return;
            }
            if (result.days.length === 0) {
                showFreeNote(`No shared free periods of at least ${minimumFreeDuration.value} minutes within the selected hours.`);
                return;
            }
            const list = makeElement("div", "grid gap-2");
            result.days.forEach(({ day, periods }) => {
                const daySection = makeElement("section", "grid gap-1");
                daySection.append(makeElement("h5", "text-xs font-bold text-neutrals-700", day));
                const periodList = makeElement("ul", "flex flex-wrap gap-1.5");
                periods.forEach(({ start, end }) => {
                    const period = makeElement(
                        "li",
                        "inline-flex items-center gap-1.5 rounded-md border border-neutrals-100 bg-neutrals-0 px-2 py-1",
                    );
                    period.append(
                        makeElement("span", "size-1.5 shrink-0 rounded-full bg-purple-500"),
                        makeElement("span", "text-xs font-bold text-neutrals-900", `${formatTime(start)} - ${formatTime(end)}`),
                        makeElement("span", "text-xs text-neutrals-400", formatDuration(start, end)),
                    );
                    periodList.append(period);
                });
                daySection.append(periodList);
                list.append(daySection);
            });
            freePeriods.className = "grid gap-2 rounded-md border border-neutrals-200 bg-neutrals-0 p-2.5";
            freePeriods.replaceChildren(list);
        } catch (error) {
            if (requestSequence === freeTimeRequestSequence) {
                showFreeNote(error.message, "border-red-200 bg-red-50 text-red-600");
            }
        }
    };

    const { renderCalendar, scrollCalendarToFirstEvent } = window.FriendsCalendar.createRenderer({
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
        renderViewers();
        renderComparePicker();
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
        const submitButton = friendForm.querySelector("button");
        submitButton.disabled = true;
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
            submitButton.disabled = false;
        }
    });

    sharedSchedulePicker.addEventListener("change", () => {
        state.selectedScheduleId = sharedSchedulePicker.value;
        sharingStatus.textContent = "";
        renderViewers();
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

    compareFriendPicker.addEventListener("change", () => {
        state.selectedFriend = compareFriendPicker.value;
        renderComparePicker();
        renderCalendar();
        renderFreePeriods();
    });
    [freeTimeStart, freeTimeEnd].forEach((input) => {
        input.addEventListener("input", renderFreePeriods);
        input.addEventListener("change", renderFreePeriods);
    });
    minimumFreeDuration.addEventListener("change", renderFreePeriods);

    applyData(initialLists, initialShares);
    renderAll();
    scrollCalendarToFirstEvent();
    }
})();
