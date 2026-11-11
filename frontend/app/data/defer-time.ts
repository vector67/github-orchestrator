import type { PrMilestone } from 'frontend/data/api';

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const DAY_NAMES = [
  'sunday',
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
];
const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];
const MINUTE = 60_000;
const UNITS: Record<string, number> = {
  m: MINUTE,
  h: 60 * MINUTE,
  d: 24 * 60 * MINUTE,
  w: 7 * 24 * 60 * MINUTE,
};
const MONDAY = 1;
const MORNING = 9;

export interface DeferPreset {
  name: string;
  hint: string;
  at: Date;
}

export function clockOf(at: Date): string {
  return `${at.getHours()}:${String(at.getMinutes()).padStart(2, '0')}`;
}

export function whenOf(at: Date): string {
  return `${WEEKDAYS[at.getDay()]} ${at.getDate()} ${MONTHS[at.getMonth()]} ${clockOf(at)}`;
}

function dayAt(now: Date, daysOn: number, hour: number, minute = 0): Date {
  return new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + daysOn,
    hour,
    minute,
  );
}

export function presetsAt(now: Date): DeferPreset[] {
  const hourOn = new Date(now.getTime() + UNITS.h!);
  const later = new Date(now.getTime() + 3 * UNITS.h!);
  const tomorrow = dayAt(now, 1, MORNING);
  const monday = dayAt(now, ((MONDAY - now.getDay() + 6) % 7) + 1, MORNING);
  return [
    { name: '1 hour', hint: clockOf(hourOn), at: hourOn },
    { name: 'Later today', hint: clockOf(later), at: later },
    {
      name: 'Tomorrow 9:00',
      hint: WEEKDAYS[tomorrow.getDay()]!,
      at: tomorrow,
    },
    { name: 'Monday 9:00', hint: WEEKDAYS[monday.getDay()]!, at: monday },
  ];
}

const SPAN = /^(\d+)\s*(m|min|mins|h|hr|hrs|hours?|d|days?|w|weeks?)$/;
const DAY_AND_TIME = /^([a-z]+)(?:\s+(\d{1,2})(?::(\d{2}))?)?$/;
const TIME = /^(\d{1,2}):(\d{2})$/;

function dayOffsets(word: string, today: number): number[] | null {
  if (word === 'today') return [0];
  if (word === 'tomorrow') return [1];
  const weekday = DAY_NAMES.findIndex(
    (day) => word.length >= 3 && day.startsWith(word),
  );
  if (weekday < 0) return null;
  const ahead = (weekday - today + 7) % 7;
  return [ahead, ahead + 7];
}

export function parseDeferTime(typed: string, now: Date): Date | null {
  const text = typed.trim().toLowerCase();
  const span = SPAN.exec(text);
  if (span) {
    const amount = Number(span[1]);
    const unit = UNITS[span[2]![0]!]!;
    return amount > 0 ? new Date(now.getTime() + amount * unit) : null;
  }
  const time = TIME.exec(text);
  const dayed = time ? null : DAY_AND_TIME.exec(text);
  const offsets = time ? [0, 1] : dayed && dayOffsets(dayed[1]!, now.getDay());
  if (!offsets) return null;
  const hour = Number(time?.[1] ?? dayed?.[2] ?? MORNING);
  const minute = Number(time?.[2] ?? dayed?.[3] ?? 0);
  if (hour > 23 || minute > 59) return null;
  return (
    offsets
      .map((daysOn) => dayAt(now, daysOn, hour, minute))
      .find((at) => at.getTime() > now.getTime()) ?? null
  );
}

export const MILESTONES: Record<PrMilestone, string> = {
  'needs-you': 'lands in Needs you',
  approved: 'is approved',
  'new-commit': 'gets a new commit',
  merged: 'is merged',
  closed: 'is closed',
  'any-activity': 'has any new activity',
};
