(() => {
// Shared sample data and helpers for the frontend-only schedule prototype.
const scheduleColors = {
    blue: {
        label: "Blue",
        picker: "border-blue-400 bg-blue-100 text-blue-900",
        dot: "bg-blue-500",
        event: "border-blue-400 bg-blue-100 text-blue-600",
        favorite: "text-blue-500",
        title: "text-blue-600",
        accent: "accent-blue-600",
    },
    green: {
        label: "Green",
        picker: "border-green-400 bg-green-100 text-green-900",
        dot: "bg-green-500",
        event: "border-green-400 bg-green-100 text-green-600",
        favorite: "text-green-500",
        title: "text-green-600",
        accent: "accent-green-600",
    },
    orange: {
        label: "Orange",
        picker: "border-orange-400 bg-orange-100 text-orange-900",
        dot: "bg-orange-500",
        event: "border-orange-400 bg-orange-100 text-orange-600",
        favorite: "text-orange-500",
        title: "text-orange-600",
        accent: "accent-orange-600",
    },
    purple: {
        label: "Purple",
        picker: "border-purple-400 bg-purple-100 text-purple-900",
        dot: "bg-purple-500",
        event: "border-purple-400 bg-purple-100 text-purple-600",
        favorite: "text-purple-500",
        title: "text-purple-600",
        accent: "accent-purple-600",
    },
    red: {
        label: "Red",
        picker: "border-red-400 bg-red-100 text-red-900",
        dot: "bg-red-500",
        event: "border-red-400 bg-red-100 text-red-600",
        favorite: "text-red-500",
        title: "text-red-600",
        accent: "accent-red-600",
    },
    yellow: {
        label: "Yellow",
        picker: "border-yellow-400 bg-yellow-100 text-yellow-900",
        dot: "bg-yellow-500",
        event: "border-yellow-400 bg-yellow-100 text-yellow-700",
        favorite: "text-yellow-600",
        title: "text-yellow-700",
        accent: "accent-yellow-600",
    },
    pink: {
        label: "Pink",
        picker: "border-pink-400 bg-pink-100 text-pink-900",
        dot: "bg-pink-500",
        event: "border-pink-400 bg-pink-100 text-pink-600",
        favorite: "text-pink-500",
        title: "text-pink-600",
        accent: "accent-pink-600",
    },
    teal: {
        label: "Teal",
        picker: "border-teal-400 bg-teal-100 text-teal-900",
        dot: "bg-teal-500",
        event: "border-teal-400 bg-teal-100 text-teal-600",
        favorite: "text-teal-500",
        title: "text-teal-600",
        accent: "accent-teal-600",
    },
};

// These are the editable schedules shown on the Schedule page.
const currentUserSchedules = [
    {
        id: "fall_2026",
        name: "Fall 2026",
        color: "blue",
        events: [{
            id: "csc-3380",
            title: "CSC 3380",
            days: ["Monday", "Wednesday", "Friday"],
            start: "09:00",
            end: "12:00",
            location: "Geoscience Complex, E0137",
            guests: ["User", "User"],
            favorite: true,
        }],
    },
    {
        id: "work",
        name: "Work",
        color: "orange",
        events: [{
            id: "library-shift",
            title: "Library Shift",
            days: ["Tuesday", "Thursday", "Saturday"],
            start: "11:00",
            end: "15:00",
            location: "",
            guests: [],
            favorite: false,
        }],
    },
    {
        id: "clubs",
        name: "Clubs",
        color: "green",
        events: [{
            id: "wics-officers",
            title: "WICS Officers",
            days: ["Monday"],
            start: "14:00",
            end: "17:00",
            location: "PFT, 1263",
            guests: ["User", "User"],
            favorite: false,
        }],
    },
    {
        id: "other",
        name: "Other",
        color: "purple",
        events: [{
            id: "gym-workout",
            title: "Gym Workout",
            days: ["Tuesday"],
            start: "17:00",
            end: "19:00",
            location: "",
            guests: [],
            favorite: false,
        }],
    },
];

// Friends' schedules provide mock comparison data; user IDs stay separate from display labels.
const sampleUsers = [
    {
        id: "user",
        displayName: "user",
        schedules: currentUserSchedules,
    },
    {
        id: "user1",
        displayName: "User 1",
        major: "Computer Science",
        status: "Free now",
        schedules: [{
            id: "user1-fall-2026",
            name: "Fall 2026",
            color: "yellow",
            events: [
                { id: "user1-csc-3380", title: "CSC 3380", days: ["Monday", "Wednesday", "Friday"], start: "09:00", end: "12:00", location: "PFT 1210", guests: [], favorite: false },
                { id: "user1-csc-3304", title: "CSC 3304", days: ["Monday", "Wednesday", "Friday"], start: "13:00", end: "15:00", location: "PFT 1200", guests: [], favorite: false },
                { id: "user1-study-group", title: "Study Group", days: ["Tuesday"], start: "15:30", end: "17:00", location: "Library", guests: [], favorite: false },
            ],
        }],
    },
    {
        id: "user2",
        displayName: "User 2",
        major: "Biology",
        status: "Busy (BIOL 1201)",
        schedules: [{
            id: "user2-fall-2026",
            name: "Fall 2026",
            color: "yellow",
            events: [
                { id: "user2-biol-1201", title: "BIOL 1201", days: ["Monday", "Wednesday", "Friday"], start: "10:00", end: "12:00", location: "Lockett Hall", guests: [], favorite: false },
                { id: "user2-chem-lab", title: "Chemistry Lab", days: ["Tuesday", "Thursday"], start: "13:00", end: "16:00", location: "Chemistry Labs", guests: [], favorite: false },
            ],
        }],
    },
    {
        id: "user3",
        displayName: "User 3",
        major: "Biology",
        status: "Free now",
        schedules: [{
            id: "user3-fall-2026",
            name: "Fall 2026",
            color: "yellow",
            events: [
                { id: "user3-biol-1201", title: "BIOL 1201", days: ["Monday", "Wednesday", "Friday"], start: "09:00", end: "11:00", location: "Lockett Hall", guests: [], favorite: false },
                { id: "user3-seminar", title: "Seminar", days: ["Tuesday", "Thursday"], start: "14:00", end: "16:00", location: "Life Sciences", guests: [], favorite: false },
            ],
        }],
    },
    {
        id: "user4",
        displayName: "User 4",
        major: "Biology",
        status: "Busy (BIOL 1201)",
        schedules: [{
            id: "user4-fall-2026",
            name: "Fall 2026",
            color: "yellow",
            events: [
                { id: "user4-biol-1201", title: "BIOL 1201", days: ["Monday", "Wednesday", "Friday"], start: "10:00", end: "12:00", location: "Lockett Hall", guests: [], favorite: false },
                { id: "user4-chem-lab", title: "Chemistry Lab", days: ["Tuesday", "Thursday"], start: "13:00", end: "16:00", location: "Chemistry Labs", guests: [], favorite: false },
            ],
        }],
    },
    {
        id: "user5",
        displayName: "User 5",
        major: "Computer Science",
        status: "Free now",
        schedules: [{
            id: "user5-fall-2026",
            name: "Fall 2026",
            color: "yellow",
            events: [
                { id: "user5-csc-3380", title: "CSC 3380", days: ["Monday", "Wednesday", "Friday"], start: "09:00", end: "12:00", location: "Geoscience Complex", guests: [], favorite: false },
                { id: "user5-csc-3304", title: "CSC 3304", days: ["Monday", "Wednesday", "Friday"], start: "13:00", end: "15:00", location: "PFT", guests: [], favorite: false },
                { id: "user5-study-group", title: "Study Group", days: ["Tuesday"], start: "15:30", end: "17:00", location: "Library", guests: [], favorite: false },
            ],
        }],
    },
    {
        id: "user6",
        displayName: "User 6",
        major: "Biology",
        status: "Busy (BIOL 1201)",
        schedules: [{
            id: "user6-fall-2026",
            name: "Fall 2026",
            color: "yellow",
            events: [
                { id: "user6-biol-1201", title: "BIOL 1201", days: ["Monday", "Wednesday", "Friday"], start: "10:00", end: "12:00", location: "Lockett Hall", guests: [], favorite: false },
                { id: "user6-chem-lab", title: "Chemistry Lab", days: ["Tuesday", "Thursday"], start: "13:00", end: "16:00", location: "Chemistry Labs", guests: [], favorite: false },
            ],
        }],
    },
];

const scheduleState = {
    currentUserId: "user",
    schedules: currentUserSchedules,
    selectedScheduleId: currentUserSchedules[0].id,
    editingEventId: null,
    idSequence: 0,
};

const dayOrder = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const getSelectedSchedule = () => scheduleState.schedules.find(
    (schedule) => schedule.id === scheduleState.selectedScheduleId,
);

const createId = (prefix) => `${prefix}-${Date.now()}-${++scheduleState.idSequence}`;

const toMinutes = (time) => {
    const [hours, minutes] = time.split(":").map(Number);
    return hours * 60 + minutes;
};

const formatTime = (time) => {
    const [hours, minutes] = time.split(":").map(Number);
    const period = hours < 12 ? "AM" : "PM";
    return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${period}`;
};

const getUserById = (userId) => sampleUsers.find((user) => user.id === userId);

window.SchedulePrototype = {
    scheduleColors,
    scheduleState,
    sampleUsers,
    dayOrder,
    getUserById,
    getSelectedSchedule,
    createId,
    toMinutes,
    formatTime,
};
})();
