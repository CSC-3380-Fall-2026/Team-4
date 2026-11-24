import type { FreeDay, Schedule } from "./types.js";

export interface FriendUser {
    id?: string | number;
    username: string;
    major?: string;
    status?: string;
    schedules: Schedule[];
}

export interface FriendRequest {
    id: string;
    username: string;
    major?: string;
}

export interface FriendState {
    requests: FriendRequest[];
    friends: { username: string }[];
    viewers: Record<string, string[]>;
    publicSchedules: Set<string>;
    selectedScheduleId: string;
    selectedFriend: string;
    selectedDay: number;
    dayPicked: boolean;
    freeDays: FreeDay[];
}

export interface FreeCard {
    day: string;
    start: string;
    end: string;
    duration: number;
}

export function makeElement<K extends keyof HTMLElementTagNameMap>(
    tag: K,
    classes: string,
    text?: string,
): HTMLElementTagNameMap[K] {
    const element = document.createElement(tag);
    element.className = classes;

    if (text !== undefined) {
        element.textContent = text;
    }

    return element;
}

export interface CalendarOptions {
    state: FriendState;
    schedules: Schedule[];
    usersByUsername: Map<string, FriendUser>;
    displayName: (username: string) => string;
    makeElement: typeof makeElement;
}
