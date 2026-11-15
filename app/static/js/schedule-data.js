(() => {
const scheduleColors = {
    blue: { label: "Blue", picker: "border-blue-400 bg-blue-100 text-blue-900", dot: "bg-blue-500", event: "border-blue-400 bg-blue-100 text-blue-600", favorite: "text-blue-500", title: "text-blue-600", accent: "accent-blue-600" },
    green: { label: "Green", picker: "border-green-400 bg-green-100 text-green-900", dot: "bg-green-500", event: "border-green-400 bg-green-100 text-green-600", favorite: "text-green-500", title: "text-green-600", accent: "accent-green-600" },
    orange: { label: "Orange", picker: "border-orange-400 bg-orange-100 text-orange-900", dot: "bg-orange-500", event: "border-orange-400 bg-orange-100 text-orange-600", favorite: "text-orange-500", title: "text-orange-600", accent: "accent-orange-600" },
    purple: { label: "Purple", picker: "border-purple-400 bg-purple-100 text-purple-900", dot: "bg-purple-500", event: "border-purple-400 bg-purple-100 text-purple-600", favorite: "text-purple-500", title: "text-purple-600", accent: "accent-purple-600" },
    red: { label: "Red", picker: "border-red-400 bg-red-100 text-red-900", dot: "bg-red-500", event: "border-red-400 bg-red-100 text-red-600", favorite: "text-red-500", title: "text-red-600", accent: "accent-red-600" },
    yellow: { label: "Yellow", picker: "border-yellow-400 bg-yellow-100 text-yellow-900", dot: "bg-yellow-500", event: "border-yellow-400 bg-yellow-100 text-yellow-700", favorite: "text-yellow-600", title: "text-yellow-700", accent: "accent-yellow-600" },
    pink: { label: "Pink", picker: "border-pink-400 bg-pink-100 text-pink-900", dot: "bg-pink-500", event: "border-pink-400 bg-pink-100 text-pink-600", favorite: "text-pink-500", title: "text-pink-600", accent: "accent-pink-600" },
    teal: { label: "Teal", picker: "border-teal-400 bg-teal-100 text-teal-900", dot: "bg-teal-500", event: "border-teal-400 bg-teal-100 text-teal-600", favorite: "text-teal-500", title: "text-teal-600", accent: "accent-teal-600" },
};

const scheduleState = {
    currentUserId: null,
    schedules: [],
    sampleUsers: [],
    metrics: {},
    selectedScheduleId: "",
    editingEventId: null,
};

const apiRequest = async (path, options = {}) => {
    const response = await fetch(path, {
        credentials: "same-origin",
        ...options,
        headers: {
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers,
        },
    });

    if (response.status === 204) {
        return null;
    }

    const responseText = await response.text();
    let responseData = null;
    if (responseText) {
        try {
            responseData = JSON.parse(responseText);
        } catch {
            responseData = null;
        }
    }
    if (!response.ok) {
        const detail = responseData?.detail;
        const message = Array.isArray(detail)
            ? detail.map((issue) => issue.msg).join(" ")
            : detail;
        throw new Error(message || `Request failed (${response.status}).`);
    }
    return responseData;
};

const loadScheduleData = async () => {
    const data = await apiRequest("/api/schedule-data");
    scheduleState.currentUserId = data.currentUserId;
    scheduleState.sampleUsers = data.users;
    const currentUser = data.users.find((user) => user.id === data.currentUserId);
    if (!currentUser) {
        throw new Error("The current user was not included in the schedule response.");
    }
    scheduleState.schedules = currentUser.schedules;
    scheduleState.metrics = data.metrics;
    if (!scheduleState.schedules.some((schedule) => schedule.id === scheduleState.selectedScheduleId)) {
        scheduleState.selectedScheduleId = scheduleState.schedules[0]?.id ?? "";
    }
    return data;
};

const getSelectedSchedule = () => scheduleState.schedules.find(
    (schedule) => schedule.id === scheduleState.selectedScheduleId,
);

const toMinutes = (time) => {
    const [hours, minutes] = time.split(":").map(Number);
    return hours * 60 + minutes;
};

const formatTime = (time) => {
    const [hours, minutes] = time.split(":").map(Number);
    const period = hours < 12 ? "AM" : "PM";
    return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${period}`;
};

const getUserById = (userId) => scheduleState.sampleUsers.find((user) => user.id === userId);

window.SchedulePrototype = {
    scheduleColors,
    scheduleState,
    apiRequest,
    loadScheduleData,
    getUserById,
    getSelectedSchedule,
    toMinutes,
    formatTime,
};
})();
