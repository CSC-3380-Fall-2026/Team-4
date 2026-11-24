import type {
    Schedule,
    SchedulePageData,
    ScheduleState,
    ScheduleUser,
} from "./types.js";

export const scheduleColors = {
    blue: {
        label: "Blue",
        picker: "border-blue-400 bg-blue-100 text-blue-900",
        dot: "bg-blue-500",
        event: "border-blue-400 bg-blue-100 text-blue-600",
        favorite: "text-blue-500",
        title: "text-blue-900",
        accent: "accent-blue-600",
    },
    green: {
        label: "Green",
        picker: "border-green-400 bg-green-100 text-green-900",
        dot: "bg-green-500",
        event: "border-green-400 bg-green-100 text-green-600",
        favorite: "text-green-500",
        title: "text-green-900",
        accent: "accent-green-600",
    },
    orange: {
        label: "Orange",
        picker: "border-orange-400 bg-orange-100 text-orange-900",
        dot: "bg-orange-500",
        event: "border-orange-400 bg-orange-100 text-orange-600",
        favorite: "text-orange-500",
        title: "text-orange-900",
        accent: "accent-orange-600",
    },
    purple: {
        label: "Purple",
        picker: "border-purple-400 bg-purple-100 text-purple-900",
        dot: "bg-purple-500",
        event: "border-purple-400 bg-purple-100 text-purple-600",
        favorite: "text-purple-500",
        title: "text-purple-900",
        accent: "accent-purple-600",
    },
    red: {
        label: "Red",
        picker: "border-red-400 bg-red-100 text-red-900",
        dot: "bg-red-500",
        event: "border-red-400 bg-red-100 text-red-600",
        favorite: "text-red-500",
        title: "text-red-900",
        accent: "accent-red-600",
    },
    yellow: {
        label: "Yellow",
        picker: "border-yellow-400 bg-yellow-100 text-yellow-900",
        dot: "bg-yellow-500",
        event: "border-yellow-400 bg-yellow-100 text-yellow-700",
        favorite: "text-yellow-600",
        title: "text-yellow-900",
        accent: "accent-yellow-600",
    },
    pink: {
        label: "Pink",
        picker: "border-pink-400 bg-pink-100 text-pink-900",
        dot: "bg-pink-500",
        event: "border-pink-400 bg-pink-100 text-pink-600",
        favorite: "text-pink-500",
        title: "text-pink-900",
        accent: "accent-pink-600",
    },
    teal: {
        label: "Teal",
        picker: "border-teal-400 bg-teal-100 text-teal-900",
        dot: "bg-teal-500",
        event: "border-teal-400 bg-teal-100 text-teal-600",
        favorite: "text-teal-500",
        title: "text-teal-900",
        accent: "accent-teal-600",
    },
};

export const scheduleState: ScheduleState = {
    currentUserId: null,
    schedules: [],
    users: [],
    metrics: {},
    selectedScheduleId: "",
    editingEventId: null,
};

export class ApiError extends Error {
    code?: string;
    eventNames?: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object"
        && value !== null
        && !Array.isArray(value);
}

export function errorMessage(error: unknown): string {
    return error instanceof Error
        ? error.message
        : "Something went wrong. Please try again.";
}

function responseError(data: unknown, status: number): ApiError {
    const detail = isRecord(data) ? data.detail : undefined;
    let message = "";

    if (typeof detail === "string") {
        message = detail;
    } else if (Array.isArray(detail)) {
        message = detail
            .filter(isRecord)
            .map((issue) => typeof issue.msg === "string"
                ? issue.msg.replace(/^Value error, /, "")
                : "")
            .filter(Boolean)
            .join(" ");
    } else if (
        isRecord(detail)
        && typeof detail.message === "string"
    ) {
        message = detail.message;
    }

    const error = new ApiError(
        message || `Request failed (${status}).`,
    );

    if (isRecord(detail)) {
        error.code = typeof detail.code === "string"
            ? detail.code
            : undefined;

        if (Array.isArray(detail.event_names)) {
            error.eventNames = detail.event_names.filter(
                (name): name is string => typeof name === "string",
            );
        }
    }

    return error;
}

/** Call an existing FastAPI endpoint using the current login cookie. */
export async function apiRequest<T = unknown>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
    const headers = new Headers(options.headers);

    if (
        typeof options.body === "string"
        && !headers.has("Content-Type")
    ) {
        headers.set("Content-Type", "application/json");
    }

    const response = await fetch(path, {
        credentials: "same-origin",
        ...options,
        headers,
    });

    if (response.status === 204) {
        return undefined as T;
    }

    const responseText = await response.text();
    let data: unknown = null;

    if (responseText) {
        try {
            data = JSON.parse(responseText) as unknown;
        } catch {
            if (response.ok) {
                throw new ApiError(
                    "The server did not return JSON. Refresh the page and sign in again if needed.",
                );
            }
        }
    }

    if (!response.ok) {
        throw responseError(data, response.status);
    }

    return data as T;
}

/** Reload saved schedules and metrics. */
export async function loadScheduleData(): Promise<SchedulePageData> {
    const data = await apiRequest<SchedulePageData>(
        "/api/schedule-data",
    );

    const currentUser = data.users.find(
        (user) => user.id === data.currentUserId,
    );

    if (!currentUser) {
        throw new Error(
            "The current user was not included in the schedule response.",
        );
    }

    scheduleState.currentUserId = data.currentUserId;
    scheduleState.users = data.users;
    scheduleState.schedules = currentUser.schedules;
    scheduleState.metrics = data.metrics;

    const selectedExists = scheduleState.schedules.some(
        (schedule) => schedule.id === scheduleState.selectedScheduleId,
    );

    if (!selectedExists) {
        scheduleState.selectedScheduleId =
            scheduleState.schedules[0]?.id ?? "";
    }

    return data;
}

export function getSelectedSchedule(): Schedule | undefined {
    return scheduleState.schedules.find(
        (schedule) => schedule.id === scheduleState.selectedScheduleId,
    );
}

export function toMinutes(time: string): number {
    const [hours, minutes] = time.split(":").map(Number);
    return hours * 60 + minutes;
}

export function formatTime(time: string): string {
    const [hours, minutes] = time.split(":").map(Number);
    const period = hours < 12 ? "AM" : "PM";

    return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${period}`;
}

export function getUserById(
    userId: string | number | null,
): ScheduleUser | undefined {
    return scheduleState.users.find((user) => user.id === userId);
}
