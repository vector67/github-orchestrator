import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import type { Picked, Timeline } from 'frontend/data/timeline';
import type { ResetControls } from 'frontend/services/pull-request-diff';
import didChange from 'frontend/modifiers/did-change';

type End = 'from' | 'to';

const eq = (one: unknown, other: unknown): boolean => one === other;

const pushedOf = (pushed: boolean | null): string | null =>
  pushed === null ? null : String(pushed);

export interface CommitTimelineSignature {
  Args: {
    timeline: Timeline;
    pick: (sha: string, extend: boolean) => void;
    stretch: (end: End, sha: string) => void;
    choose: (picked: Picked | null) => void;
    fit: (across: number) => void;
    unfold: () => void;
    reset: ResetControls;
  };
}

function svgX(svg: SVGSVGElement, event: PointerEvent): number | null {
  const screen = svg.getScreenCTM();
  if (!screen) return null;
  return new DOMPoint(event.clientX, event.clientY).matrixTransform(
    screen.inverse(),
  ).x;
}

export default class CommitTimeline extends Component<CommitTimelineSignature> {
  @service declare router: RouterService;
  @tracked listing: number | null = null;
  private dragging: End | null = null;
  private dragged: string | null = null;

  listen = (scroll: HTMLElement) => {
    const svg = scroll.querySelector('svg')!;
    const clicked = (event: MouseEvent) => this.clicked(event);
    const grabbed = (event: PointerEvent) => this.grabbed(event);
    const moved = (event: PointerEvent) => this.moved(svg, event);
    const dropped = () => {
      this.dragging = null;
    };
    svg.addEventListener('click', clicked);
    svg.addEventListener('pointerdown', grabbed);
    svg.addEventListener('pointermove', moved);
    svg.addEventListener('pointerup', dropped);
    svg.addEventListener('pointerleave', dropped);
    return () => {
      svg.removeEventListener('click', clicked);
      svg.removeEventListener('pointerdown', grabbed);
      svg.removeEventListener('pointermove', moved);
      svg.removeEventListener('pointerup', dropped);
      svg.removeEventListener('pointerleave', dropped);
    };
  };

  measure = (scroll: HTMLElement) => {
    const watching = new ResizeObserver(() =>
      this.args.fit(scroll.clientWidth),
    );
    watching.observe(scroll);
    return () => watching.disconnect();
  };

  private get counted(): string {
    const here = this.args.timeline.header.diverged?.here ?? 0;
    return here === 1
      ? "Its 1 commit that isn't on origin"
      : `Its ${here} commits that aren't on origin`;
  }

  get dropped(): string {
    return `${this.counted} will be dropped.`;
  }

  get droppedLater(): string {
    return `${this.counted} will be dropped, and so will any commits the agent makes before then.`;
  }

  private clicked(event: MouseEvent): void {
    const target = event.target as Element;
    const opens = target.closest('[data-opens]')?.getAttribute('data-opens');
    if (opens) {
      void this.router.transitionTo(opens);
      return;
    }
    if (target.closest('[data-earlier]')) {
      this.args.unfold();
      return;
    }
    const pill = target
      .closest('[data-collapsed]')
      ?.getAttribute('data-collapsed');
    if (pill) {
      this.listing = this.listing === Number(pill) ? null : Number(pill);
      return;
    }
    const sha = target.closest('[data-pickable]')?.getAttribute('data-sha');
    if (sha) this.args.pick(sha, event.shiftKey);
  }

  private grabbed(event: PointerEvent): void {
    const end = (event.target as Element)
      .closest('[data-end]')
      ?.getAttribute('data-end');
    if (end !== 'from' && end !== 'to') return;
    event.preventDefault();
    this.dragging = end;
    this.dragged = null;
  }

  private moved(svg: SVGSVGElement, event: PointerEvent): void {
    const end = this.dragging;
    const x = end && svgX(svg, event);
    if (!end || x === null) return;
    const nearest = this.args.timeline.dots
      .filter((one) => one.pickable)
      .reduce((best, one) =>
        Math.abs(one.x - x) < Math.abs(best.x - x) ? one : best,
      );
    if (nearest.sha === this.dragged) return;
    this.dragged = nearest.sha;
    this.args.stretch(end, nearest.sha);
  }

  <template>
    <section
      class="commit-timeline"
      aria-label="the branch's timeline"
      data-test-timeline
    >
      <header class="timeline-head">
        <p class="timeline-title" data-test-timeline-header>
          <b>{{@timeline.header.count}}</b>
          {{#if @timeline.header.diverged}}
            in the worktree
          {{else}}
            on
            {{@timeline.header.branch}}
          {{/if}}
          ·
          {{@timeline.header.relation}}
          {{#if @timeline.header.fork}}<code
              class="timeline-fork"
            >{{@timeline.header.fork}}</code>{{/if}}{{#if
            @timeline.header.was
          }}, was
            <code
              class="timeline-fork"
              data-test-was-fork
            >{{@timeline.header.was}}</code>{{/if}}{{#if
            @timeline.header.behind
          }}
            <span
              class="timeline-behind"
              data-test-behind
            >{{@timeline.header.behind}}
              behind
              {{@timeline.header.base}}</span>
            <span class="timeline-aside">{{@timeline.header.base}}'s new commits
              aren't in this diff</span>
          {{else if @timeline.header.tip}}, {{@timeline.header.tip}}{{/if}}
          {{#if @timeline.header.diverged}}
            · origin has
            {{@timeline.header.diverged.other}}
            from
            <code
              class="timeline-fork"
            >{{@timeline.header.diverged.from}}</code>
            <span
              class="timeline-behind"
              data-test-diverged
            >{{@timeline.header.diverged.chip}}</span>
            {{#if @reset.standing.queued}}
              <span class="timeline-reset-queued" data-test-reset-queued>Reset
                queued until the agent finishes
                <button
                  type="button"
                  class="btn timeline-reset"
                  data-test-reset-unqueue
                  {{on "click" @reset.unqueue}}
                >Cancel</button></span>
            {{else}}
              <button
                type="button"
                class="btn timeline-reset"
                data-test-reset-to-origin
                {{on "click" @reset.ask}}
              >Reset to origin</button>
            {{/if}}
          {{/if}}
        </p>
        <span class="timeline-presets" role="group" aria-label="pick a range">
          {{#each @timeline.presets key="name" as |preset|}}
            <button
              type="button"
              class="btn"
              aria-pressed={{if preset.active "true" "false"}}
              disabled={{if preset.available false true}}
              data-test-preset={{preset.name}}
              {{on "click" (fn @choose preset.picks)}}
            >{{preset.label}}</button>
          {{/each}}
        </span>
      </header>
      {{#if @timeline.header.diverged}}
        {{#if @reset.confirming}}
          <div
            class="timeline-reset-confirm"
            role="alertdialog"
            aria-label="reset the worktree to origin"
            data-test-reset-confirm
          >
            {{#if (eq @reset.confirming "later")}}
              <p class="timeline-reset-question">Reset the worktree to origin
                when the agent finishes?
                {{this.droppedLater}}</p>
              <button
                type="button"
                class="btn"
                data-test-reset-yes
                {{on "click" @reset.confirm}}
              >Reset when it finishes</button>
            {{else}}
              <p class="timeline-reset-question">Reset the worktree to origin?
                {{this.dropped}}</p>
              <button
                type="button"
                class="btn"
                data-test-reset-yes
                {{on "click" @reset.confirm}}
              >Reset</button>
            {{/if}}
            <button
              type="button"
              class="btn"
              data-test-reset-no
              {{on "click" @reset.cancel}}
            >Cancel</button>
          </div>
        {{/if}}
      {{/if}}
      {{#if @reset.refused}}
        <p class="timeline-reset-refused" role="status" data-test-reset-refused>
          {{@reset.refused}}
          {{#if @reset.offerLater}}
            <button
              type="button"
              class="btn timeline-reset"
              data-test-reset-later
              {{on "click" @reset.askLater}}
            >Reset when the agent finishes</button>
          {{/if}}
        </p>
      {{/if}}
      {{#if @reset.standing.outcome}}
        <p class="timeline-reset-outcome" role="status" data-test-reset-outcome>
          {{@reset.standing.outcome}}
          <button
            type="button"
            class="btn timeline-reset"
            aria-label="dismiss"
            data-test-reset-dismiss
            {{on "click" @reset.unqueue}}
          >×</button>
        </p>
      {{/if}}
      <div
        class="timeline-scroll"
        {{didChange this.listen}}
        {{didChange this.measure}}
      >
        <svg
          class="timeline-graph"
          width={{@timeline.width}}
          height={{@timeline.height}}
          viewBox="0 0 {{@timeline.width}} {{@timeline.height}}"
          role="img"
          aria-label="the base branch and this branch's commits"
          data-test-timeline-graph
        >
          {{#if @timeline.since}}
            <g data-test-since-fork>
              <rect
                class="timeline-since"
                x={{@timeline.since.x}}
                y={{@timeline.since.y}}
                width={{@timeline.since.width}}
                height={{@timeline.since.height}}
                rx="6"
              />
              <text
                class="timeline-note"
                x={{@timeline.since.x}}
                y={{@timeline.since.textY}}
              >{{@timeline.since.text}}</text>
            </g>
          {{/if}}
          {{#each @timeline.lanes key="@index" as |lane|}}
            <line
              class="timeline-lane"
              data-lane={{lane.lane}}
              data-dashed={{if lane.dashed "true"}}
              data-test-unpushed-lane={{if lane.unpushed "true"}}
              data-test-ghost-lane={{if (eq lane.lane "ghost") "true"}}
              x1={{lane.from}}
              y1={{lane.y}}
              x2={{lane.to}}
              y2={{lane.y}}
            />
          {{/each}}
          {{#each @timeline.curves key="path" as |curve|}}
            {{#if (eq curve.kind "merge")}}
              <path
                class="timeline-lane"
                data-lane={{curve.lane}}
                data-kind="merge"
                d={{curve.path}}
                data-test-merge-curve
              />
            {{else if (eq curve.kind "ghost")}}
              <path
                class="timeline-lane"
                data-lane={{curve.lane}}
                data-kind="ghost"
                d={{curve.path}}
                data-test-ghost-curve
              />
            {{else}}
              <path
                class="timeline-lane"
                data-lane={{curve.lane}}
                d={{curve.path}}
                data-test-fork-curve
              />
            {{/if}}
          {{/each}}
          <rect
            class="timeline-band"
            x={{@timeline.band.x}}
            y={{@timeline.band.y}}
            width={{@timeline.band.width}}
            height={{@timeline.band.height}}
            rx="12"
            data-test-band
          />
          {{#if @timeline.flag}}
            <g class="timeline-flag" data-test-review-flag>
              <line
                x1={{@timeline.flag.x}}
                y1={{@timeline.flag.top}}
                x2={{@timeline.flag.x}}
                y2={{@timeline.flag.bottom}}
              />
              <text
                class="timeline-note"
                x={{@timeline.flag.x}}
                y={{@timeline.flag.textY}}
                text-anchor="middle"
              >{{@timeline.flag.text}}</text>
            </g>
          {{/if}}
          {{#if @timeline.current}}
            <circle
              class="timeline-current"
              cx={{@timeline.current.x}}
              cy={{@timeline.current.y}}
              r="9"
              data-at={{@timeline.current.sha}}
              data-test-current
            />
          {{/if}}
          {{#each @timeline.dots key="sha" as |dot|}}
            {{#if (eq dot.shape "dot")}}
              <circle
                class="timeline-dot"
                cx={{dot.x}}
                cy={{dot.y}}
                r={{dot.radius}}
                data-x={{dot.x}}
                data-y={{dot.y}}
                data-shape={{dot.shape}}
                data-pushed={{pushedOf dot.pushed}}
                data-sha={{dot.sha}}
                data-lane={{dot.lane}}
                data-style={{dot.style}}
                data-in-range={{if dot.inRange "true" "false"}}
                data-pickable={{if dot.pickable "true"}}
                data-test-dot
              ><title>{{dot.title}}</title></circle>
            {{else}}
              <path
                class="timeline-dot"
                d={{dot.path}}
                data-x={{dot.x}}
                data-y={{dot.y}}
                data-shape={{dot.shape}}
                data-pushed={{pushedOf dot.pushed}}
                data-sha={{dot.sha}}
                data-lane={{dot.lane}}
                data-style={{dot.style}}
                data-in-range={{if dot.inRange "true" "false"}}
                data-pickable={{if dot.pickable "true"}}
                data-test-dot
              ><title>{{dot.title}}</title></path>
            {{/if}}
            {{#if dot.showSha}}
              <text
                class="timeline-sha"
                x={{dot.x}}
                y={{dot.shaY}}
                text-anchor="middle"
                data-test-sha
              >{{dot.short}}</text>
            {{/if}}
            {{#if dot.matched}}
              <text
                class="timeline-note"
                x={{dot.x}}
                y={{dot.matchedY}}
                text-anchor="middle"
                data-at={{dot.sha}}
                data-test-matched
              >≈ read</text>
            {{/if}}
            {{#if dot.date}}
              <text
                class="timeline-note"
                x={{dot.x}}
                y={{dot.dateY}}
                text-anchor={{dot.dateAnchor}}
                data-test-date
              >{{dot.date}}</text>
            {{/if}}
          {{/each}}
          {{#each @timeline.days key="x" as |day|}}
            <g class="timeline-day" data-x={{day.x}} data-test-day>
              <line x1={{day.x}} y1={{day.top}} x2={{day.x}} y2={{day.y}} />
              <text
                class="timeline-note"
                x={{day.textX}}
                y={{day.y}}
              >{{day.text}}</text>
            </g>
          {{/each}}
          {{#each @timeline.collapsed key="x" as |run index|}}
            <g
              class="timeline-run"
              data-collapsed={{index}}
              data-x={{run.x}}
              aria-expanded={{if (eq this.listing index) "true" "false"}}
              data-test-collapsed
            >
              <rect
                x={{run.left}}
                y={{run.top}}
                width={{run.width}}
                height={{run.height}}
                rx="10"
              />
              <text
                x={{run.x}}
                y={{run.y}}
                text-anchor="middle"
                dominant-baseline="middle"
              >{{run.text}}</text>
            </g>
          {{/each}}
          {{#if @timeline.earlier}}
            <g
              class="timeline-run"
              data-earlier
              data-x={{@timeline.earlier.x}}
              data-test-earlier
            >
              <rect
                x={{@timeline.earlier.left}}
                y={{@timeline.earlier.top}}
                width={{@timeline.earlier.width}}
                height={{@timeline.earlier.height}}
                rx="10"
              />
              <text
                x={{@timeline.earlier.x}}
                y={{@timeline.earlier.y}}
                text-anchor="middle"
                dominant-baseline="middle"
              >{{@timeline.earlier.text}}</text>
            </g>
          {{/if}}
          {{#each @timeline.labels key="kind" as |label|}}
            {{#if label.box}}
              <rect
                class="timeline-label-box"
                x={{label.box.x}}
                y={{label.box.y}}
                width={{label.box.width}}
                height={{label.box.height}}
                rx="4"
                data-test-label-box={{label.kind}}
              />
            {{/if}}
            <text
              class="timeline-label"
              x={{label.x}}
              y={{label.y}}
              dominant-baseline="middle"
              data-kind={{label.kind}}
              data-at={{label.at}}
              data-opens={{label.opens}}
              data-test-lane-label={{label.kind}}
            >{{label.text}}</text>
          {{/each}}
          <rect
            class="timeline-handle"
            x={{@timeline.band.fromX}}
            y={{@timeline.band.y}}
            width="8"
            height={{@timeline.band.height}}
            transform="translate(-4 0)"
            rx="2"
            data-end="from"
            data-test-handle="from"
          />
          <rect
            class="timeline-handle"
            x={{@timeline.band.toX}}
            y={{@timeline.band.y}}
            width="8"
            height={{@timeline.band.height}}
            transform="translate(-4 0)"
            rx="2"
            data-end="to"
            data-test-handle="to"
          />
        </svg>
      </div>
      {{#each @timeline.collapsed key="x" as |run index|}}
        {{#if (eq this.listing index)}}
          <ol
            class="timeline-run-list"
            aria-label="the commits folded into the pill"
            data-test-collapsed-list
          >
            {{#each run.listed key="@index" as |one|}}
              <li><code class="timeline-run-sha">{{one.short}}</code>
                {{one.subject}}</li>
            {{/each}}
          </ol>
        {{/if}}
      {{/each}}
      {{#if @timeline.ghosts}}
        <p class="timeline-ghosts" data-test-ghost-shas>{{@timeline.ghosts}}</p>
      {{/if}}
      <p class="timeline-key" data-test-timeline-key>
        <span class="timeline-key-item" data-test-key="unread"><i
            data-style="unread"
          ></i>
          unread</span>
        <span class="timeline-key-item" data-test-key="read"><i
            data-style="read"
          ></i>
          read</span>
        <span class="timeline-key-item" data-test-key="current"><i
            data-style="current"
          ></i>
          this commit</span>
        <span class="timeline-key-item" data-test-key="base"><i
            data-style="base"
          ></i>
          {{@timeline.header.main}}</span>
        {{#if (eq @timeline.header.main @timeline.header.base)}}{{else}}
          <span class="timeline-key-item" data-test-key="stack"><i
              data-style="stack"
            ></i>
            {{@timeline.header.base}}</span>
        {{/if}}
        {{#if @timeline.ghosts}}
          <span class="timeline-key-item" data-test-key="ghost"><i
              data-style="ghost"
            ></i>
            what your review saw</span>
        {{/if}}
        <span class="timeline-key-item" data-test-key="band"><i
            data-style="band"
          ></i>
          in the diff</span>
        {{#if @timeline.key.merge}}
          <span class="timeline-key-item" data-test-key="merge"><i
              data-style="merge"
            ></i>
            merge from
            {{@timeline.header.main}}</span>
        {{/if}}
        {{#if @timeline.key.tick}}
          <span class="timeline-key-item" data-test-key="tick"><i
              data-style="tick"
            ></i>
            commit</span>
        {{/if}}
        {{#if @timeline.key.unpushed}}
          <span class="timeline-key-item" data-test-key="not-pushed"><i
              data-style="not-pushed"
            ></i>
            not pushed</span>
        {{/if}}
        {{#if @timeline.key.origin}}
          <span class="timeline-key-item" data-test-key="origin"><i
              data-style="origin"
            ></i>
            on origin, not here</span>
        {{/if}}
        {{#if @timeline.key.merge}}
          <span class="timeline-key-item" data-test-key="merge-pip"><i
              data-style="merge-pip"
            ></i>
            a merge in the pips</span>
        {{/if}}
        <span class="timeline-aside">click a dot for one commit · shift-click or
          drag the handles for a range</span>
      </p>
    </section>
  </template>
}
