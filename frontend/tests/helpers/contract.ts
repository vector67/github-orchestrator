import served from './board-api-contract.json';

interface Schema {
  $ref?: string;
  type?: string;
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
  anyOf?: Schema[];
  oneOf?: Schema[];
  enum?: unknown[];
  const?: unknown;
  pattern?: string;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  minItems?: number;
  discriminator?: { propertyName: string; mapping: Record<string, string> };
}

interface Contract {
  paths: Record<string, Record<string, Record<string, Schema | null>>>;
  schemas: Record<string, Schema>;
}

const CONTRACT = served as Contract;
const REF = '#/components/schemas/';

function templateOf(path: string): RegExp {
  const pattern = path
    .split(/(\{[^}]+\})/)
    .map((part) =>
      part.startsWith('{')
        ? '[^/]+'
        : part.replace(/[.*+?^$()|[\]\\]/g, '\\$&'),
    )
    .join('');
  return new RegExp(`^${pattern}$`);
}

const ROUTES = Object.entries(CONTRACT.paths).map(([path, methods]) => ({
  path,
  matches: templateOf(path),
  methods,
}));

function kindOf(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  if (typeof value === 'number')
    return Number.isInteger(value) ? 'integer' : 'number';
  return typeof value;
}

function fits(kind: string, wanted: string): boolean {
  return kind === wanted || (wanted === 'number' && kind === 'integer');
}

function problems(value: unknown, schema: Schema, at: string): string[] {
  if (schema.$ref) {
    const named = CONTRACT.schemas[schema.$ref.slice(REF.length)];
    if (!named) return [`${at}: the contract has no ${schema.$ref}`];
    return problems(value, named, at);
  }
  const chosen = chosenBy(schema, value);
  if (chosen) return problems(value, { $ref: chosen }, at);
  const shapes = schema.anyOf ?? schema.oneOf;
  if (shapes) {
    const each = shapes.map((one) => problems(value, one, at));
    const fitting = each.filter((found) => found.length === 0).length;
    if (fitting === 1 || (fitting > 1 && schema.anyOf)) return [];
    if (fitting > 1) return [`${at}: fits ${fitting} of its shapes`];
    return each.reduce((nearest, found) =>
      found.length < nearest.length ? found : nearest,
    );
  }
  const kind = kindOf(value);
  if (schema.type && !fits(kind, schema.type)) {
    return [`${at}: is ${kind}, the contract says ${schema.type}`];
  }
  if ('const' in schema && value !== schema.const) {
    return [
      `${at}: is ${JSON.stringify(value)}, not ${JSON.stringify(schema.const)}`,
    ];
  }
  if (schema.enum && !schema.enum.includes(value)) {
    return [
      `${at}: ${JSON.stringify(value)} is not one of ${JSON.stringify(schema.enum)}`,
    ];
  }
  if (typeof value === 'string') return stringProblems(value, schema, at);
  if (typeof value === 'number' && schema.minimum !== undefined) {
    return value < schema.minimum ? [`${at}: is below ${schema.minimum}`] : [];
  }
  if (Array.isArray(value)) return arrayProblems(value, schema, at);
  if (kind === 'object' && schema.properties) {
    return objectProblems(value as Record<string, unknown>, schema, at);
  }
  return [];
}

function chosenBy(schema: Schema, value: unknown): string | undefined {
  const by = schema.discriminator;
  if (!by || kindOf(value) !== 'object') return undefined;
  const named = (value as Record<string, unknown>)[by.propertyName];
  return typeof named === 'string' ? by.mapping[named] : undefined;
}

function stringProblems(value: string, schema: Schema, at: string): string[] {
  const found: string[] = [];
  if (schema.pattern && !new RegExp(schema.pattern, 'u').test(value)) {
    found.push(`${at}: ${JSON.stringify(value)} misses ${schema.pattern}`);
  }
  if (schema.minLength !== undefined && value.length < schema.minLength) {
    found.push(`${at}: is shorter than ${schema.minLength}`);
  }
  if (schema.maxLength !== undefined && value.length > schema.maxLength) {
    found.push(`${at}: is longer than ${schema.maxLength}`);
  }
  return found;
}

function arrayProblems(value: unknown[], schema: Schema, at: string): string[] {
  const found: string[] = [];
  if (schema.minItems !== undefined && value.length < schema.minItems) {
    found.push(`${at}: has fewer than ${schema.minItems} items`);
  }
  const items = schema.items;
  if (items) {
    value.forEach((one, index) =>
      found.push(...problems(one, items, `${at}[${index}]`)),
    );
  }
  return found;
}

function objectProblems(
  value: Record<string, unknown>,
  schema: Schema,
  at: string,
): string[] {
  const properties = schema.properties ?? {};
  const found = (schema.required ?? [])
    .filter((name) => !(name in value))
    .map((name) => `${at}.${name}: is required and missing`);
  for (const [name, one] of Object.entries(value)) {
    const property = properties[name];
    if (!property) {
      found.push(`${at}.${name}: the contract has no such field`);
    } else {
      found.push(...problems(one, property, `${at}.${name}`));
    }
  }
  return found;
}

const THROUGH_THE_HUB = /^\/pr\/[^/]+\/[^/]+\/[^/]+(\/api\/.*)$/;
const PROXIED = CONTRACT.paths['/pr/{owner}/{name}/{number}/api/{path}'] ?? {};

export function driftOf(
  method: string,
  url: string,
  status: number,
  body: unknown,
): string[] {
  const path = new URL(url, 'http://127.0.0.1').pathname;
  const where = `${method.toUpperCase()} ${path} ${status}`;
  const through = THROUGH_THE_HUB.exec(path);
  if (through) {
    const own = PROXIED[method.toLowerCase()]?.[String(status)];
    if (status >= 400 && own) return problems(body, own, where);
    return driftOf(method, through[1]!, status, body);
  }
  const route = ROUTES.find((one) => one.matches.test(path));
  if (!route) {
    return status === 404 ? [] : [`${where}: the contract has no such path`];
  }
  const answers = route.methods[method.toLowerCase()];
  if (!answers) return [`${where}: the contract has no such method`];
  if (!(String(status) in answers)) {
    return [`${where}: the contract never answers this status`];
  }
  const schema = answers[String(status)];
  if (!schema) return [];
  return problems(body, schema, where);
}
