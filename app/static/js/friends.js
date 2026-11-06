(() => {
    // Keep friend requests, sharing controls, and schedule comparison local to this page.
    const { scheduleState, getUserById, loadScheduleData } = window.SchedulePrototype;
    const searchMessage = document.querySelector("#friend-search-message");
    loadScheduleData().then(initializeFriends).catch((error) => {
        searchMessage.textContent = error.message;
        searchMessage.className = "text-sm text-red-600";
    });

    function initializeFriends() {
    const sampleUsers = scheduleState.sampleUsers;
    const currentUser = getUserById(scheduleState.currentUserId);
    const schedules = currentUser.schedules;
    const usersByUsername = new Map(sampleUsers.map((user) => [user.username, user]));
    let nextUserNumber = sampleUsers.length + 1;

    const state = {
        requests: [
            { id: "request-1", username: "user5", major: "Computer Science" },
            { id: "request-2", username: "user6", major: "Biology" },
        ],
        friends: [
            { username: "user1" },
            { username: "user2" },
            { username: "user3" },
            { username: "user4" },
        ],
        viewers: {
            fall_2026: ["user1", "user2", "user3"],
            work: [],
            clubs: [],
            other: [],
        },
        publicSchedules: new Set(),
        selectedScheduleId: schedules[0].id,
        selectedFriend: "user1",
    };
    const userLabels = new Map();

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
    const compareFriendPicker = document.querySelector("#compare-friend-picker");
    const makeElement = (tag, classes, text) => {
        const element = document.createElement(tag);
        element.className = classes;
        if (text !== undefined) {
            element.textContent = text;
        }
        return element;
    };

    const displayName = (username) => {
        const knownUsername = usersByUsername.get(username)?.username;
        const label = knownUsername
            ? knownUsername === "user" ? "user" : knownUsername.replace(/^user/, "User ")
            : userLabels.get(username);
        if (label) {
            return label;
        }
        const generatedLabel = `User ${nextUserNumber++}`;
        userLabels.set(username, generatedLabel);
        return generatedLabel;
    };

    const makeButton = (text, classes, action, label) => {
        const button = makeElement("button", classes, text);
        button.type = "button";
        button.setAttribute("aria-label", label);
        button.addEventListener("click", action);
        return button;
    };

    const renderRequests = () => {
        requestList.replaceChildren();
        requestCount.textContent = `${state.requests.length} New`;
        requestCount.classList.toggle("hidden", state.requests.length === 0);
        noRequests.classList.toggle("hidden", state.requests.length > 0);

        state.requests.forEach((request) => {
            const item = makeElement("li", "flex flex-col gap-3 rounded-md border border-neutrals-100 bg-neutrals-0 p-3 sm:flex-row sm:items-center sm:justify-between");
            const identity = makeElement("div", "flex min-w-0 items-center gap-3");
            identity.append(makeElement("span", "size-9 shrink-0 rounded-full bg-neutrals-100"));
            const details = makeElement("div", "min-w-0");
            const requestName = displayName(request.username);
            details.append(
                makeElement("p", "truncate text-sm font-bold text-neutrals-800", requestName),
                makeElement("p", "truncate text-xs text-neutrals-400", request.major),
            );
            identity.append(details);

            const actions = makeElement("div", "flex shrink-0 gap-2");
            actions.append(
                makeButton("Accept", "rounded-md bg-purple-400 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-purple-500", () => {
                    const directoryEntry = usersByUsername.get(request.username);
                    if (!directoryEntry) {
                        const newUser = {
                            username: request.username,
                            major: request.major,
                            status: "Free now",
                            schedules: [],
                        };
                        sampleUsers.push(newUser);
                        usersByUsername.set(request.username, newUser);
                    }
                    state.friends.push({
                        username: request.username,
                    });
                    state.requests = state.requests.filter((item) => item.id !== request.id);
                    renderAll();
                }, `Accept ${requestName}'s request`),
                makeButton("Decline", "rounded-md border border-neutrals-200 px-3 py-1.5 text-xs font-semibold text-neutrals-500 transition-colors hover:bg-yellow-50", () => {
                    state.requests = state.requests.filter((item) => item.id !== request.id);
                    renderRequests();
                }, `Decline ${requestName}'s request`),
            );
            item.append(identity, actions);
            requestList.append(item);
        });
    };

    const renderFriends = () => {
        friendsList.replaceChildren();
        noFriends.classList.toggle("hidden", state.friends.length > 0);

        state.friends.forEach((friend) => {
            const user = usersByUsername.get(friend.username);
            const status = friend.status ?? user?.status ?? "Free now";
            const item = makeElement("li", "flex items-center justify-between gap-3 rounded-md border border-neutrals-100 bg-neutrals-0 px-3 py-2");
            const identity = makeElement("div", "flex min-w-0 items-center gap-3");
            identity.append(makeElement("span", "size-9 shrink-0 rounded-full bg-neutrals-100"));
            const details = makeElement("div", "min-w-0");
            const nameLine = makeElement("p", "flex items-center gap-1 text-sm font-bold text-neutrals-800");
            nameLine.append(document.createTextNode(displayName(friend.username)));
            nameLine.append(makeElement("span", "size-1.5 rounded-full bg-emerald-500"));
            details.append(nameLine);
            const statusClass = status.startsWith("Free")
                ? "text-xs font-medium text-emerald-600"
                : "truncate text-xs font-medium text-neutrals-400";
            details.append(makeElement("p", statusClass, status));
            identity.append(details);

            const removeButton = makeButton("Remove", "shrink-0 rounded-md border border-red-300 px-3 py-1.5 text-xs font-semibold text-red-600 transition-colors hover:bg-red-50", () => {
                state.friends = state.friends.filter((item) => item.username !== friend.username);
                Object.values(state.viewers).forEach((viewers) => {
                    const viewerIndex = viewers.indexOf(friend.username);
                    if (viewerIndex >= 0) {
                        viewers.splice(viewerIndex, 1);
                    }
                });
                if (state.selectedFriend === friend.username) {
                    state.selectedFriend = state.friends[0]?.username ?? "";
                }
                renderAll();
            }, `Remove ${displayName(friend.username)} from friends`);
            item.append(identity, removeButton);
            friendsList.append(item);
        });
    };

    const renderViewers = () => {
        // This picker controls sharing only; it does not filter the comparison calendar
        const schedule = schedules.find((item) => item.id === state.selectedScheduleId);
        const viewers = state.viewers[schedule.id] ?? [];
        scheduleViewers.replaceChildren();
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
            const chip = makeElement("span", "inline-flex items-center gap-1 rounded-md bg-purple-500 px-2.5 py-1 text-xs font-medium text-white", displayName(username));
            const removeButton = makeButton("×", "cursor-pointer text-sm leading-none text-white/80 hover:text-yellow-300", () => {
                state.viewers[schedule.id] = viewers.filter((viewer) => viewer !== username);
                renderViewers();
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

    const renderComparePicker = () => {
        const previousFriend = state.selectedFriend;
        compareFriendPicker.replaceChildren();
        state.friends.forEach((friend) => {
            const option = document.createElement("option");
            option.value = friend.username;
            option.textContent = displayName(friend.username);
            compareFriendPicker.append(option);
        });
        if (state.friends.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "No friends yet";
            compareFriendPicker.append(option);
            compareFriendPicker.disabled = true;
            state.selectedFriend = "";
        } else {
            compareFriendPicker.disabled = false;
            state.selectedFriend = state.friends.some((friend) => friend.username === previousFriend)
                ? previousFriend
                : state.friends[0].username;
            compareFriendPicker.value = state.selectedFriend;
        }
        const selectedFriend = state.friends.find((friend) => friend.username === state.selectedFriend);
        document.querySelector("#friend-legend-name").textContent = selectedFriend
            ? displayName(selectedFriend.username)
            : "Friend";
    };

    const { renderCalendar, scrollCalendarToFirstEvent } = window.FriendsCalendar.createRenderer({
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
        renderComparePicker();
        renderCalendar();
    };

    friendForm.addEventListener("submit", (submitEvent) => {
        submitEvent.preventDefault();
        const enteredName = usernameInput.value.trim().replace(/^@/, "");
        searchMessage.className = "text-sm";

        if (!enteredName) {
            searchMessage.textContent = "Enter a username to send a friend request.";
            searchMessage.classList.add("text-red-600");
            return;
        }
        const username = `user${nextUserNumber++}`;
        state.requests.push({
            id: `request-${Date.now()}`,
            username,
            major: "Student",
        });
        usernameInput.value = "";
        searchMessage.textContent = "Friend request added to pending requests.";
        searchMessage.classList.add("text-purple-700");
        renderRequests();
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
        if (!viewers.includes(username)) {
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

    compareFriendPicker.addEventListener("change", () => {
        state.selectedFriend = compareFriendPicker.value;
        renderCalendar();
    });
    renderAll();
    scrollCalendarToFirstEvent();
    }
})();
