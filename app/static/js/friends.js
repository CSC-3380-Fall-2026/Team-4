(() => {
    // Keep friend requests, sharing controls, and schedule comparison local to this page.
    const { apiRequest, scheduleState, getUserById, loadScheduleData } = window.SchedulePrototype;
    const searchMessage = document.querySelector("#friend-search-message");
    Promise.all([
        loadScheduleData(),
        apiRequest("/api/friends/list"),
        apiRequest("/api/friends/shared-by-me"),
    ]).then(([, friendsData, sharesData]) => initializeFriends(friendsData, sharesData)).catch((error) => {
        searchMessage.textContent = error.message;
        searchMessage.className = "text-sm text-red-600";
    });

    function initializeFriends(friendsData, sharesData) {
    const sampleUsers = scheduleState.sampleUsers;
    const currentUser = getUserById(scheduleState.currentUserId);
    const schedules = currentUser.schedules;
    // Friends are the students who shared schedules with the signed-in student.
    const friendUsers = sampleUsers.filter((user) => user.id !== currentUser.id);
    const usersByUsername = new Map(sampleUsers.map((user) => [user.username, user]));

    const state = {
        shares: sharesData,
        requests: friendsData.incoming_requests,
        friends: friendsData.friends,
        viewers: Object.fromEntries(schedules.map((schedule) => [
            schedule.id,
            sharesData.filter((share) => share.schedule_id === schedule.id)
                .map((share) => {
                    const friend = friendsData.friends.find((item) =>
                        item.requester_id === share.friend_id ||
                        item.addressee_id === share.friend_id
                    );
                    return friend?.username;
                }).filter(Boolean),
        ])),
        publicSchedules: new Set(),
        selectedScheduleId: schedules[0]?.id ?? "",

        selectedFriend: friendsData.friends[0]?.username ?? "",
        // which day the overlap chart shows, 0 = Monday. Starts on today.
        selectedDay: (new Date().getDay() + 6) % 7,
        // turns true when you press the day arrows, after that we stop moving the day for you
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
    const publicSharingToggle = document.querySelector("#public-sharing-toggle");
    const scheduleViewers = document.querySelector("#schedule-viewers");
    const addScheduleViewer = document.querySelector("#add-schedule-viewer");
    const addScheduleViewerButton = document.querySelector("#add-schedule-viewer-button");
    const noScheduleViewers = document.querySelector("#no-schedule-viewers");
    const sharingStatus = document.querySelector("#sharing-status");
    const friendCount = document.querySelector("#friend-count");
    const freeTotal = document.querySelector("#free-total");
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

    const showFreeMessage = (message, isError) => {
        freePeriods.replaceChildren();
        freePeriods.className = isError ? "plan-cards plan-message plan-error" : "plan-cards plan-message";
        freePeriods.textContent = message;
    };

    const renderFreePeriods = async () => {
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
            const result = await apiRequest("/api/shared-free-time", {
                method: "POST",
                body: JSON.stringify({
                    friendUsername: state.selectedFriend,
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
                    false,
                );
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
            // the figma has room for 3 cards, the first one is the gold "Best match"
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

    const displayName = (username) => username;

    const makeButton = (text, classes, action, label) => {
        const button = makeElement("button", classes, text);
        button.type = "button";
        button.setAttribute("aria-label", label);
        button.addEventListener("click", action);
        return button;
    };

    const renderRequests = () => {
        requestList.replaceChildren();
        // the number next to the Requests tab
        requestCount.textContent = state.requests.length > 0 ? String(state.requests.length) : "";
        noRequests.classList.toggle("hidden", state.requests.length > 0);

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

                makeButton("Accept","page-button request-button" , async () => {
                    try {
                        await apiRequest(`/api/friends/requests/${request.id}/accept`, {
                            method: "POST",
                        });
                        window.location.reload();
                    } catch (error) {
                        searchMessage.textContent = error.message;
                        searchMessage.className = "text-sm text-red-600";
                    }


                }, `Accept ${requestName}'s request`),

                makeButton("Decline","secondary-button request-button" , async () => {
                    try {
                        await apiRequest(`/api/friends/requests/${request.id}`, {
                            method: "DELETE",
                        });
                        window.location.reload();
                    } catch (error) {
                        searchMessage.textContent = error.message;
                        searchMessage.className = "text-sm text-red-600";
                    }



                }, `Decline ${requestName}'s request`),
            );
            item.append(details, actions);
            requestList.append(item);
        });
    };

    const renderFriends = () => {
        friendsList.replaceChildren();
        friendCount.textContent = String(state.friends.length);
        noFriends.classList.toggle("hidden", state.friends.length > 0);

        state.friends.forEach((friend) => {
            const user = usersByUsername.get(friend.username);
            const count = user?.schedules.length ?? 0;
            const status = `${count} shared ${count === 1 ? "schedule" : "schedules"}`;
            const friendName = displayName(friend.username);


            const removeButton = makeButton("Remove", "friend-remove", async () => {
                try {
                    await apiRequest(`/api/friends/${friend.id}`, { method: "DELETE" });
                    window.location.reload();
                } catch (error) {
                    searchMessage.textContent = error.message;
                    searchMessage.className = "text-sm text-red-600";
                }
            }, `Remove ${displayName(friend.username)} from friends`);


            const item = makeElement("li", "friend-row");
            const details = makeElement("div", "friend-details");
            details.append(
                makeElement("p", "friend-name", friendName),
                makeElement("p", "friend-sub", status),
            );



            // The check box picks who you compare with. The free time API only takes
            // one friend at a time, so checking one friend unchecks the other ones.
            const checkbox = makeElement("input", "friend-check");
            checkbox.type = "checkbox";
            checkbox.checked = state.selectedFriend === friend.username;
            checkbox.setAttribute("aria-label", `Compare schedules with ${friendName}`);
            checkbox.addEventListener("change", () => {
                state.selectedFriend = checkbox.checked ? friend.username : "";
                renderFriends();
                renderCalendar();
                renderFreePeriods();
            });

            item.append(details, removeButton, checkbox);

            friendsList.append(item);
        });
    };

    const renderViewers = () => {
        // This picker controls sharing only; it does not filter the comparison calendar
        const schedule = schedules.find((item) => item.id === state.selectedScheduleId);
        scheduleViewers.replaceChildren();
        if (!schedule) {
            addScheduleViewer.replaceChildren();
            addScheduleViewerButton.disabled = true;
            noScheduleViewers.classList.remove("hidden");
            sharingStatus.textContent = "Create a schedule to share it with friends.";
            return;
        }
        const viewers = state.viewers[schedule.id] ?? [];
        noScheduleViewers.classList.toggle("hidden", viewers.length > 0);
        addScheduleViewer.replaceChildren();
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Share with friend...";
        addScheduleViewer.append(defaultOption);
        state.friends.filter((friend) => !viewers.includes(friend.username)).forEach((friend) => {
            const option = document.createElement("option");
            option.value = friend.username;
            option.textContent = displayName(friend.username);
            addScheduleViewer.append(option);
        });
        addScheduleViewerButton.disabled = addScheduleViewer.options.length <= 1;

        viewers.forEach((username) => {

            const chip = makeElement("span", "viewer-chip", displayName(username));
            const removeButton = makeButton("×", "viewer-remove", async () => {
                const friend = state.friends.find((item) => item.username === username);
                const friendId = friend?.requester_id === scheduleState.currentUserId
                    ? friend?.addressee_id : friend?.requester_id;
                const share = state.shares.find((item) =>
                    item.schedule_id === schedule.id && item.friend_id === friendId
                );
                if (!share) return;
                try {
                    await apiRequest(`/api/friends/shares/${share.id}`, { method: "DELETE" });
                    state.shares = state.shares.filter((item) => item.id !== share.id);
                    state.viewers[schedule.id] = viewers.filter((viewer) => viewer !== username);
                    renderViewers();
                } catch (error) {
                    searchMessage.textContent = error.message;
                    searchMessage.className = "text-sm text-red-600";
                }

            }, `Stop sharing with ${displayName(username)}`);
            chip.append(removeButton);
            scheduleViewers.append(chip);
        });

        publicSharingToggle.checked = state.publicSchedules.has(schedule.id);
        sharingStatus.textContent = publicSharingToggle.checked
            ? `${schedule.name} is public and visible to anyone with its link.`
            : `${schedule.name} is shared with ${viewers.length} ${viewers.length === 1 ? "friend" : "friends"}.`;
    };

    const renderSharedSchedulePicker = () => {
        sharedSchedulePicker.replaceChildren();
        schedules.forEach((schedule) => {
            const option = document.createElement("option");
            option.value = schedule.id;
            option.textContent = schedule.name;
            sharedSchedulePicker.append(option);
        });
        if (!schedules.some((schedule) => schedule.id === state.selectedScheduleId)) {
            state.selectedScheduleId = schedules[0]?.id ?? "";
        }
        sharedSchedulePicker.value = state.selectedScheduleId;
    };

    const checkSelectedFriend = () => {
        // if the friend we were comparing with got removed, fall back to the first friend
        const stillFriend = state.friends.some((friend) => friend.username === state.selectedFriend);
        if (state.selectedFriend && !stillFriend) {
            state.selectedFriend = state.friends[0]?.username ?? "";
        }
    };

    const { renderCalendar } = window.FriendsCalendar.createRenderer({
        state,
        schedules,
        usersByUsername,
        displayName,
        makeElement,
    });

    const renderAll = () => {
        renderRequests();
        renderFriends();
        renderSharedSchedulePicker();
        renderViewers();
        checkSelectedFriend();
        renderCalendar();
        renderFreePeriods();
    };

    friendForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const enteredName = usernameInput.value.trim().replace(/^@/, "");
        searchMessage.className = "text-sm";

        if (!enteredName) {
            searchMessage.textContent = "Enter a username to send a friend request.";
            searchMessage.classList.add("text-red-600");
            return;
        }
        try {
            const result = await apiRequest("/api/friends/requests", {
                method: "POST",
                body: JSON.stringify({ username: enteredName }),
            });
            usernameInput.value = "";
            searchMessage.textContent = result.message;
            searchMessage.classList.add("text-purple-700");
        } catch (error) {
            searchMessage.textContent = error.message;
            searchMessage.classList.add("text-red-600");
        }
    });

    sharedSchedulePicker.addEventListener("change", () => {
        state.selectedScheduleId = sharedSchedulePicker.value;
        renderViewers();
    });

    addScheduleViewerButton.addEventListener("click", async () => {
    const username = addScheduleViewer.value;
    if (!username || !state.selectedScheduleId) return;

    const friend = state.friends.find((item) => item.username === username);
    if (!friend) return;

    const friendId = friend.requester_id === scheduleState.currentUserId
        ? friend.addressee_id
        : friend.requester_id;

    try {
        const result = await apiRequest("/api/friends/shares", {
            method: "POST",
            body: JSON.stringify({
                schedule_id: state.selectedScheduleId,
                friend_id: friendId,
            }),
        });
        state.shares = state.shares.filter((item) =>
            !(item.schedule_id === state.selectedScheduleId && item.friend_id === friendId)
        );
        state.shares.push(result.share);
        const viewers = state.viewers[state.selectedScheduleId];
        if (viewers && !viewers.includes(username)) {
            viewers.push(username);
        }
        renderViewers();
    } catch (error) {
        searchMessage.textContent = error.message;
        searchMessage.className = "text-sm text-red-600";
    }
      });

    publicSharingToggle.addEventListener("change", () => {
        if (publicSharingToggle.checked) {
            state.publicSchedules.add(state.selectedScheduleId);
        } else {
            state.publicSchedules.delete(state.selectedScheduleId);
        }
        renderViewers();
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
    renderAll();
    }
})();
