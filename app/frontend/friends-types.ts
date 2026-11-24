import type { FreeDay, Schedule, ScheduleUser } from "./types.js";

/** A friend or pending request from /api/friends/list. */
export interface Friend {
    id: string;
    user_id: string;
    username: string;
}

export interface FriendLists {
    friends: Friend[];
    incoming_requests: Friend[];
    outgoing_requests: Friend[];
}

/** One schedule shared with one friend, from /api/friends/shares. */
export interface ScheduleShare {
    id: string;
    schedule_id: string;
    friend_id: string;
    username: string;
}

export interface FriendState {
    incoming: Friend[];
    outgoing: Friend[];
    friends: Friend[];
    shares: ScheduleShare[];
    selectedScheduleId: string;
    // which of the checked friend's shared schedules to compare with
    selectedFriendScheduleId: string;
    // null until the first load picks a friend; "" means the student unchecked everyone
    selectedFriend: string | null;
    // which day the overlap chart shows, 0 = Monday
    selectedDay: number;
    // turns true when the day arrows are pressed, after that the day stays put
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
    usersById: Map<string | number, ScheduleUser>;
    displayName: (userId: string | null) => string;
    makeElement: typeof makeElement;
}
