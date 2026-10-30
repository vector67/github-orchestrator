import type { Person } from 'frontend/data/api';

const OFFERED = 5;

function wordsOf(person: Person): string[] {
  return [person.login, person.name ?? ''].map((word) => word.toLowerCase());
}

export function peopleNamed(people: Person[], typed: string): Person[] {
  const query = typed.toLowerCase();
  const starting = people.filter((one) =>
    wordsOf(one).some((word) => word.startsWith(query)),
  );
  const containing = people.filter(
    (one) =>
      !starting.includes(one) &&
      wordsOf(one).some((word) => word.includes(query)),
  );
  return [...starting, ...containing].slice(0, OFFERED);
}
