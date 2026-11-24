export type ColorName =
    | "blue"
    | "green"
    | "orange"
    | "purple"
    | "red"
    | "yellow"
    | "pink"
    | "teal";

export type RenderPage = () => void;

export interface ScheduleEvent {
    id: string;
    title: string;
    days: string[];
    start: string;
    end: string;
    location: string;
    guests: string[];
    favorite: boolean;
}

export interface Schedule {
    id: string;
    name: string;
    color: ColorName;
    events: ScheduleEvent[];
}

export interface ScheduleUser {
    id: string | number;
    username: string | null;
    email: string;
    gpa: number | null;
    completedCreditHours: number;
    courses: unknown[];
    schedules: Schedule[];
}

export interface ScheduleMetrics {
    totalHours: number;
    daysBusy: string;
}

export interface SchedulePageData {
    currentUserId: string | number;
    users: ScheduleUser[];
    metrics: Record<string, ScheduleMetrics>;
}

export interface ScheduleState {
    currentUserId: string | number | null;
    schedules: Schedule[];
    users: ScheduleUser[];
    metrics: Record<string, ScheduleMetrics>;
    selectedScheduleId: string;
    editingEventId: string | null;
}

export interface CoursePreset {
    courseId: string;
    title: string;
    courseName: string;
    department: string;
    number: number;
    credit: number;
    category: string;
    semester: string;
}

export interface FreeDay {
    day: string;
    periods: {
        start: string;
        end: string;
    }[];
}

export interface SharedFreeTime {
    days: FreeDay[];
}
