import type { TOC } from '@ember/component/template-only';
import OldLinkChooser from 'frontend/components/old-link';
import NotFound from 'frontend/templates/not-found';
import type { OldLink } from 'frontend/routes/old-link';

interface OldLinkSignature {
  Args: { model: OldLink | null };
}

const OldLinkPage: TOC<OldLinkSignature> = <template>
  {{#if @model}}
    <OldLinkChooser @link={{@model}} />
  {{else}}
    <NotFound />
  {{/if}}
</template>;

export default OldLinkPage;
