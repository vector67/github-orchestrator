import Route from '@ember/routing/route';

export default class ConversationDetailRoute extends Route {
  model(params: { conversation_id: string }): string {
    return params.conversation_id;
  }
}
