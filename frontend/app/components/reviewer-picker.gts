import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import type { AssignReviewersRequest, Person } from 'frontend/data/api';

interface ReviewerPickerSignature {
  Args: {
    people: Person[];
    pick: AssignReviewersRequest;
    choose: (pick: AssignReviewersRequest) => void;
  };
}

const inOrder = (people: Person[], logins: Set<string>): string[] =>
  people.map((one) => one.login).filter((login) => logins.has(login));

const toggled = (
  people: Person[],
  pick: AssignReviewersRequest,
  login: string,
): AssignReviewersRequest => {
  const logins = new Set(pick.reviewers);
  if (logins.delete(login)) {
    return {
      reviewers: inOrder(people, logins),
      detailed: pick.detailed === login ? null : pick.detailed,
    };
  }
  return {
    reviewers: inOrder(people, logins.add(login)),
    detailed: pick.detailed,
  };
};

const starred = (
  people: Person[],
  pick: AssignReviewersRequest,
  login: string,
): AssignReviewersRequest => {
  if (pick.detailed === login) return { ...pick, detailed: null };
  return {
    reviewers: inOrder(people, new Set(pick.reviewers).add(login)),
    detailed: login,
  };
};

const toggle =
  (
    choose: (pick: AssignReviewersRequest) => void,
    people: Person[],
    pick: AssignReviewersRequest,
    login: string,
  ) =>
  () =>
    choose(toggled(people, pick, login));

const star =
  (
    choose: (pick: AssignReviewersRequest) => void,
    people: Person[],
    pick: AssignReviewersRequest,
    login: string,
  ) =>
  () =>
    choose(starred(people, pick, login));

const picked = (pick: AssignReviewersRequest, login: string): boolean =>
  pick.reviewers.includes(login);

const isDetailed = (pick: AssignReviewersRequest, login: string): string =>
  String(pick.detailed === login);

const ReviewerPicker: TOC<ReviewerPickerSignature> = <template>
  <fieldset class="reviewer-picker" data-test-reviewer-picker>
    <legend class="note">Ask someone to review; ★ names the detailed reviewer</legend>
    {{#if @people.length}}
      <ul class="reviewer-list">
        {{#each @people key="login" as |person|}}
          <li class="reviewer-row">
            <label class="reviewer-name" data-test-reviewer={{person.login}}>
              <input
                type="checkbox"
                checked={{picked @pick person.login}}
                {{on "change" (toggle @choose @people @pick person.login)}}
              />{{person.login}}</label>
            <button
              type="button"
              class="btn"
              aria-pressed={{isDetailed @pick person.login}}
              title="Detailed reviewer: named on the description’s Detailed reviewer line"
              data-test-detailed={{person.login}}
              {{on "click" (star @choose @people @pick person.login)}}
            >★ detailed</button>
          </li>
        {{/each}}
      </ul>
    {{else}}
      <p class="note">Nobody to ask yet: GitHub has not said who can review.</p>
    {{/if}}
  </fieldset>
</template>;

export default ReviewerPicker;
