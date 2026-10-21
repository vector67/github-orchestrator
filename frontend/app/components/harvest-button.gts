import type { TOC } from '@ember/component/template-only';
import type { Numbered } from 'frontend/data/wall';

interface HarvestButtonSignature {
  Args: { pr: Numbered; title: string; url: string | null };
}

const ownerOf = (pr: Numbered): string => pr.repo.split('/')[0] ?? '';

const nameOf = (pr: Numbered): string => pr.repo.split('/')[1] ?? '';

const item = (pr: Numbered, title: string): string =>
  JSON.stringify({ id: String(pr.number), name: `#${pr.number}: ${title}` });

const group = (pr: Numbered): string =>
  JSON.stringify({ id: nameOf(pr), name: nameOf(pr) });

const account = (pr: Numbered): string => JSON.stringify({ id: ownerOf(pr) });

const permalink = (pr: Numbered, url: string | null): string =>
  url ?? `https://github.com/${pr.repo}/pull/${pr.number}`;

const HarvestButton: TOC<HarvestButtonSignature> = <template>
  <button
    type="button"
    class="harvest-timer"
    aria-label="Harvest timer"
    title="Harvest timer"
    data-skip-styling="true"
    data-item={{item @pr @title}}
    data-group={{group @pr}}
    data-account={{account @pr}}
    data-permalink={{permalink @pr @url}}
  ><svg
      class="stopwatch"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentcolor"
      stroke-width="2"
      aria-hidden="true"
      focusable="false"
    ><circle cx="8" cy="9.25" r="5.25" /><path
        d="M6 1.5h4M8 9.25V6.5"
      /></svg></button>
</template>;

export default HarvestButton;
