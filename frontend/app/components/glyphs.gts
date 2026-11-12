import type { TOC } from '@ember/component/template-only';

export interface GlyphsSignature {
  Args: { opensDialog?: boolean; runsAgent?: boolean };
}

const Glyphs: TOC<GlyphsSignature> = <template>
  {{#if @runsAgent}}
    <svg
      class="glyph"
      data-glyph="agent"
      viewBox="0 0 16 16"
      fill="currentcolor"
      aria-hidden="true"
      focusable="false"
    ><path
        d="M8 1C8.5 5 11 7.5 15 8 11 8.5 8.5 11 8 15 7.5 11 5 8.5 1 8 5 7.5 7.5 5 8 1Z"
      /></svg>
  {{/if}}
  {{#if @opensDialog}}
    <svg
      class="glyph"
      data-glyph="dialog"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentcolor"
      stroke-width="1.5"
      aria-hidden="true"
      focusable="false"
    ><rect x="2" y="3" width="12" height="10" /><path d="M2 6.25h12" /></svg>
  {{/if}}
</template>;

export default Glyphs;
