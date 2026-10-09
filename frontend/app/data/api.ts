export interface AgentActivity {
  name: string;
  enabled: boolean;
  state: AgentState;
  event: string | null;
  elapsed_seconds: number | null;
  silent_seconds: number | null;
}

export interface AgentOutput {
  lines: OutputLine[];
}

export type AgentState = 'idle' | 'working';

export interface Anchor {
  path: string | null;
  line: number | null;
  start_line: number | null;
  start_side: DiffSide | null;
  side: DiffSide | null;
  original_line: number | null;
  original_start_line: number | null;
  original_commit: string | null;
  is_outdated: boolean;
}

export interface ApproveOperation {
  id: string;
  conversation: string | null;
  kind: 'approve';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  reply: string | null;
  delete_comment: boolean;
  proposal: string | null;
  steps: LandingSteps;
  landed_base: string | null;
  landed_sha: string | null;
  posted_comment: number | null;
  reply_note: string | null;
  ticket_key: string | null;
  ticket_url: string | null;
}

export interface ApproveRequest {
  reply?: string | null;
  delete_comment?: boolean;
  resolve?: boolean;
  message?: string | null;
  ticket?: Ticket | null;
}

export type AuthorKind = 'mine' | 'human' | 'bot';

export interface Brief {
  note: string;
  pointed: PointedLine[];
  include: string[];
}

export interface BriefRequest {
  note?: string;
  pointed?: PointedLine[];
  include?: string[];
}

export type CapturedGit = 'f' | 'p' | 'pra' | 's' | 'l' | 'd';

export type Classification = 'risky' | 'unclear' | 'out-of-scope' | 'already-done' | 'acknowledgement' | 'question' | 'needs-human';

export interface ClientError {
  where: string;
  message: string;
  stack?: string | null;
}

export type CloneState = 'waiting' | 'cloning' | 'cloned' | 'found' | 'failed';

export interface CloseOperation {
  id: string;
  conversation: string | null;
  kind: 'resolve' | 'reject';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  reply: string | null;
  delete_comment: boolean;
  posted_comment: number | null;
}

export interface CloseRequest {
  reply?: string | null;
  delete_comment?: boolean;
}

export interface Comment {
  id: number | null;
  author: string;
  created_at: string | null;
  review_state: ReviewState | null;
  body: string;
  updated_at: string | null;
  html_url: string | null;
  posted_by_board: boolean;
  deleted: boolean;
  deleted_by_board: boolean;
}

export type CommentList = Comment[];

export interface CommentSummary {
  id: number | null;
  author: string;
  created_at: string | null;
  review_state: ReviewState | null;
}

export interface Commits {
  base: string;
  head: string;
}

export type ConfidenceLevel = 'low' | 'medium' | 'high';

export interface Conversation {
  key: string;
  github_node_id: string | null;
  kind: ThreadKind;
  state: ConversationState;
  state_changed_at: string | null;
  reopened: boolean;
  etag: string;
  github_removed: boolean;
  github_resolved: boolean | null;
  github_resolved_at: string | null;
  created_at: string | null;
  anchor: Anchor;
  gist: string | null;
  comments: CommentSummary[];
  operations: OperationSummary[];
  mention: boolean;
  updated_at: string | null;
  author_kind: AuthorKind;
  unread: boolean;
  record_state: RecordState;
}

export interface ConversationList {
  conversations: Conversation[];
  unreadable: string[];
  listed_at: string;
}

export type ConversationState = 'draft' | 'enrolled' | 'queued' | 'working' | 'in-session' | 'rework' | 'landing' | 'ready' | 'waiting' | 'assumed-done' | 'not-mine' | 'deferred' | 'done';

export interface Dashboard {
  pr: DashboardPr;
  polled: boolean;
  status: DashboardStatus;
  system: DashboardSystem;
  frozen: FrozenWorktree | null;
  undismiss_command: string;
  notice: string | null;
  facts: PrFacts | null;
  manager: ManagerFlags;
  threads: ThreadRow[];
  unreadable: string[];
  listed_at: string | null;
}

export interface DashboardPr {
  repo: string;
  number: number;
  title: string | null;
  url: string | null;
  branch: string | null;
  ticket: string | null;
  author: string | null;
}

export interface DashboardStatus {
  detailed_reviewer: string | null;
  you_are_the_detailed_reviewer: boolean;
  mergeable: boolean;
  needs_rebase: boolean;
  last_event_at: string | null;
  review_ready_at: string | null;
  since_you_last_acted: SinceYouActed | null;
  failed_checks: string[];
  checks_done: number;
  checks_total: number;
  changed_files: number | null;
  approved_by: string[];
}

export interface DashboardSystem {
  agent: AgentActivity;
  last_run: LastRun | null;
  queued_events: number;
  on_hold: boolean;
  unpushed_commits: number | null;
  threads: ThreadCounts;
}

export interface DeferOperation {
  id: string;
  conversation: string | null;
  kind: 'defer';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  until: string;
  note: string | null;
}

export interface DeferRequest {
  until: string;
  note?: string | null;
}

export interface Diff {
  base: string;
  head: string;
  files: FileChange[];
}

export type DiffFileStatus = 'added' | 'modified' | 'removed' | 'renamed' | 'copied';

export interface DiffHunk {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  section: string | null;
  lines: DiffLine[];
}

export interface DiffLine {
  kind: DiffLineKind;
  old_line: number | null;
  new_line: number | null;
  text: string;
}

export type DiffLineKind = 'context' | 'added' | 'removed';

export type DiffSide = 'LEFT' | 'RIGHT';

export type DiffSource = 'origin' | 'local';

export interface DismissRequest {
  forever: boolean;
}

export interface DraftBody {
  body: string;
  path: string;
  line: number;
  start_line?: number | null;
  start_side?: DiffSide | null;
  side?: DiffSide;
}

export interface DraftOperation {
  id: string;
  conversation: string | null;
  kind: 'create-draft' | 'edit-draft' | 'enrol' | 'withdraw-from-review' | 'discard' | 'post-now';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  body: string | null;
  anchor: Anchor | null;
  posted_comment: number | null;
}

export type ErrorCode = 'not-found' | 'operation-outstanding' | 'nothing-in-flight' | 'work-in-flight' | 'no-proposal' | 'proposal-exists' | 'nothing-committed' | 'already-closed' | 'parked' | 'not-parked' | 'still-a-draft' | 'not-a-draft' | 'already-enrolled' | 'confirm-again' | 'anchor-not-in-diff' | 'empty-brief' | 'malformed-request' | 'empty-body' | 'body-too-long' | 'comment-gone' | 'not-deletable' | 'bad-wake-condition' | 'precondition-failed' | 'unreadable-record' | 'range-inverted' | 'range-too-wide' | 'not-text' | 'no-such-commit' | 'no-such-path' | 'review-in-flight' | 'nothing-enrolled' | 'git-failed' | 'github-rejected' | 'agents-disabled' | 'internal-refusal' | 'foreign-origin' | 'manager-starting' | 'watcher-starting' | 'watcher-failing' | 'not-watching' | 'not-frozen' | 'board-unreachable' | 'terminal-refused' | 'manager-refused' | 'no-gh-token' | 'repo-not-visible' | 'setup-refused' | 'not-broken' | 'server-error';

export interface ErrorDetail {
  status: number;
  code: ErrorCode;
  detail: string;
}

export interface Errors {
  errors: ErrorDetail[];
}

export interface FieldError {
  status: number;
  code: ErrorCode;
  detail: string;
  field: string;
}

export interface FieldErrors {
  errors: FieldError[];
}

export interface FileChange {
  path: string;
  old_path: string | null;
  status: DiffFileStatus;
  added: number;
  removed: number;
  is_binary: boolean;
  line_count?: number | null;
  hunks: DiffHunk[];
}

export interface FileLine {
  number: number;
  text: string;
}

export interface FileLines {
  sha: string;
  path: string;
  from_line: number;
  to_line: number;
  truncated: boolean;
  lines: FileLine[];
}

export interface FileOperation {
  id: string;
  conversation: string | null;
  kind: 'file';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
}

export interface FinishedRun {
  ended_at: string;
  repo: string | null;
  number: number | null;
  event: string;
  elapsed_seconds: number;
  exit_code: number | null;
  cost_usd: number | null;
  failed: boolean;
  board_url: string | null;
}

export interface FixOperation {
  id: string;
  conversation: string | null;
  kind: 'first' | 'rebase' | 'rework' | 'retry';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  attempts: number;
  attempts_allowed: number;
  last_action: string | null;
  progress: string | null;
  plan: PlanStep[];
  onto: string | null;
  conflict: string | null;
  brief: Brief | null;
  proposal: string | null;
  classification: Classification | null;
}

export interface FrozenWorktree {
  worktree: string;
  here: string;
  expected: string;
  seconds_left: number;
  run_working: boolean;
  release_requested: boolean;
}

export interface GitRequest {
  keys: CapturedGit;
}

export interface GitRun {
  exit_code: number;
  lines: string[];
  seconds: number;
  truncated: boolean;
}

export interface Health {
  status: 'ok';
  pid: number;
  serves: 'board' | 'hub';
  hub_url: string;
  font_problem: string | null;
  state: HubState | null;
  version: string | null;
  watcher: WatcherHealth | null;
  newest_release: NewestRelease | null;
}

export interface HeldPullRequest {
  repo: string;
  number: number;
  manager: string;
  board_url: string | null;
  board_answered: boolean;
  dashboard: Dashboard;
}

export interface HeldPullRequests {
  watching: string[];
  groups: WallGroupName[];
  pull_requests: HeldPullRequest[];
}

export type HubState = 'setup' | 'watching' | 'broken';

export interface LandingSteps {
  filed: boolean;
  picked: boolean;
  pushed: boolean;
  answered: boolean;
}

export interface LastRun {
  event: string;
  exit_code: number | null;
  ended_at: string;
}

export interface ManagerChanges {
  markdown: string | null;
}

export interface ManagerFlags {
  frozen_on: string | null;
  on_hold: boolean;
  working_on: string | null;
  hidden: boolean;
  threads_live: number;
  changed_at: string | null;
}

export interface MentionFact {
  author: string;
  at: string | null;
  answered: boolean;
}

export type MergeState = 'clean' | 'conflicts' | 'behind' | 'blocked' | 'checks-failing' | 'unknown' | 'other';

export interface MovedAside {
  moved_to: string;
}

export interface NewestRelease {
  version: string;
  checked_at: string;
  newer: boolean;
}

export type OperationKind = 'first' | 'rebase' | 'file' | 'rework' | 'retry' | 'start-session' | 'approve' | 'stop' | 'resolve' | 'reject' | 'defer' | 'unpark' | 'confirm' | 'place' | 'reply' | 'create-draft' | 'edit-draft' | 'enrol' | 'withdraw-from-review' | 'discard' | 'post-now' | 'send-review' | 'posted';

export type Operation = FixOperation | SessionOperation | ApproveOperation | FileOperation | StopOperation | CloseOperation | DeferOperation | UnparkOperation | PlaceOperation | ReplyOperation | DraftOperation | ReviewOperation | PostedOperation;

export type OperationList = Operation[];

export type OperationState = 'pending' | 'running' | 'applied' | 'refused' | 'requeued';

export interface OperationSummary {
  id: string;
  kind: OperationKind;
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  steps_done: number | null;
  steps_total: number | null;
  attempts: number | null;
  attempts_allowed: number | null;
  lands: ProposalKind | null;
  ticket_key: string | null;
}

export interface Outcome {
  operation: FixOperation | SessionOperation | ApproveOperation | FileOperation | StopOperation | CloseOperation | DeferOperation | UnparkOperation | PlaceOperation | ReplyOperation | DraftOperation | ReviewOperation | PostedOperation;
  conversation: Conversation;
}

export interface OutputLine {
  text: string;
  run_boundary: boolean;
}

export interface Person {
  login: string;
  name: string | null;
}

export type PersonList = Person[];

export interface PlaceOperation {
  id: string;
  conversation: string | null;
  kind: 'confirm' | 'place';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
}

export interface PlaceRequest {
  to: 'ready' | 'waiting' | 'not-mine' | 'queued';
}

export interface PlanStep {
  text: string;
  file: string | null;
  done: boolean;
}

export interface PointedLine {
  file: string;
  line: number | null;
  text: string;
}

export interface PostedOperation {
  id: string;
  conversation: string | null;
  kind: 'posted';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  review: string | null;
  posted_comment: number | null;
  github_node_id: string | null;
}

export interface PrFacts {
  polled_at: string | null;
  ended: boolean;
  is_author: boolean | null;
  changes_requested_by: string[];
  pending_reviewers: string[];
  ci_status: string;
  merge_state: MergeState | null;
  draft: boolean;
  review_decision: string | null;
  my_review: string | null;
  my_review_at: string | null;
  viewer_requested: boolean;
  mentioned: boolean;
  mentions: MentionFact[];
  unresolved_threads: number | null;
}

export interface Proposal {
  id: string;
  conversation: string;
  kind: ProposalKind;
  reply: string | null;
  ticket: Ticket | null;
  operation: string | null;
  created_at: string | null;
  updated_at: string | null;
  commits: Commits | null;
  directory: string | null;
  summary: string | null;
  agent_note: string | null;
  confidence: ConfidenceLevel | null;
  confidence_note: string | null;
  tests: string | null;
  tests_note: string | null;
  commit_message: string | null;
}

export type ProposalKind = 'commit' | 'reply' | 'ticket';

export type ProposalList = Proposal[];

export interface PullRequest {
  repo: string;
  number: number;
  title: string | null;
  html_url: string;
  base_branch: string | null;
  branch: string | null;
  head_sha: string | null;
}

export type ReasonCode = 'withdrawn' | 'agent-declined' | 'max-attempts' | 'agent-unavailable' | 'conflict' | 'nothing-committed' | 'push-failed' | 'reply-failed' | 'file-failed' | 'comment-gone' | 'github-rejected' | 'git-failed' | 'anchor-not-in-diff' | 'superseded' | 'worktree-missing';

export type RecordState = 'open' | 'waiting_on_reviewer' | 'assumed_done' | 'not_mine' | 'confirmed' | 'deferred' | 'rejected' | 'resolved' | 'removed' | 'draft' | 'enrolled' | 'discarded';

export interface ReplyOperation {
  id: string;
  conversation: string | null;
  kind: 'reply';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  body: string;
  posted_comment: number | null;
}

export interface ReplyRequest {
  body: string;
}

export interface ResolveRequest {
  reply?: string | null;
  delete_comment?: boolean;
  resolve?: boolean;
  thumbs_up?: boolean;
}

export interface ReviewOperation {
  id: string;
  conversation: string | null;
  kind: 'send-review';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  verdict: ReviewVerdict;
  body: string | null;
  drafts: string[];
  posted_review: number | null;
}

export type ReviewState = 'APPROVED' | 'CHANGES_REQUESTED' | 'COMMENTED' | 'DISMISSED' | 'PENDING';

export type ReviewVerdict = 'APPROVE' | 'REQUEST_CHANGES' | 'COMMENT';

export interface RunLedger {
  watcher: WatcherHealth;
  today: RunsToday;
  runs: FinishedRun[];
}

export interface RunsToday {
  runs: number;
  cost_usd: number | null;
  unpriced: number;
}

export interface SendReviewRequest {
  verdict: ReviewVerdict;
  body?: string | null;
}

export interface SessionOperation {
  id: string;
  conversation: string | null;
  kind: 'start-session';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  steer: string | null;
  last_action: string | null;
  progress: string | null;
  plan: PlanStep[];
  proposal: string | null;
}

export interface Setup {
  state: HubState;
  etag: string;
  config_path: string;
  problem: string | null;
  active_account: string | null;
  gh_account: string | null;
  repos: SetupRepo[];
  options: SetupOptions;
  hub_port: number;
  agent_name: string;
  requirements: SetupRequirement[];
}

export interface SetupAccount {
  login: string;
  scopes: string[];
}

export interface SetupClone {
  repo: string;
  path: string;
  exists: boolean;
  is_clone: boolean;
}

export interface SetupCloneProgress {
  repo: string;
  path: string;
  state: CloneState;
  error: string | null;
}

export interface SetupOperation {
  id: string;
  state: WriteState;
  clones: SetupCloneProgress[];
  error: string | null;
  archived: string[];
  kept_worktrees: string[];
}

export interface SetupOptions {
  agent_model: string;
  agents_enabled: boolean;
  max_thread_runs: number;
}

export interface SetupRepo {
  repo: string;
  local_path: string;
  new_worktree_command?: string;
}

export interface SetupRepoChoice {
  repo: string;
  can_push: boolean;
  has_my_prs: boolean;
  default_branch: string;
}

export interface SetupRepoChoices {
  login: string;
  repos: SetupRepoChoice[];
}

export interface SetupRequest {
  gh_account: string;
  repos: SetupRepo[];
  options: SetupOptions;
  hub_port?: number | null;
}

export interface SetupRequirement {
  program: string;
  fix: string | null;
}

export interface SinceYouActed {
  commits: number;
  force_pushed: boolean;
  reviews: number;
  comments: number;
  threads_resolved: number;
}

export interface StartSessionRequest {
  steer?: string | null;
  pointed?: PointedLine[];
  include?: string[];
}

export interface StopOperation {
  id: string;
  conversation: string | null;
  kind: 'stop';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
  stopped: string | null;
}

export interface TerminalRequest {
  keys: string;
}

export interface TerminalSession {
  id: string;
  argv: string[];
  worktree: string;
}

export interface TerminalSessionList {
  sessions: TerminalSession[];
}

export interface ThreadCounts {
  queued: number;
  live: number;
  proposed: number;
  drafts: number;
}

export type ThreadKind = 'draft' | 'review' | 'issue' | 'review-summary' | 'pr-body';

export interface ThreadRow {
  key: string;
  state: ConversationState;
  record_state: RecordState;
  author_kind: AuthorKind;
  updated_at: string | null;
}

export interface Ticket {
  project: string;
  title: string;
  body: string;
}

export interface Tour {
  due: boolean;
}

export interface UnparkOperation {
  id: string;
  conversation: string | null;
  kind: 'unpark';
  state: OperationState;
  reason: string | null;
  reason_code: ReasonCode | null;
  requested_at: string | null;
  settled_at: string | null;
}

export type WallGroup = 'needs-you' | 'draft' | 'agent-working' | 'waiting-on-others' | 'on-hold' | 'mentioned';

export interface WallGroupName {
  group: WallGroup;
  name: string;
}

export interface WatcherHealth {
  polled_at: string | null;
  next_poll_at: string | null;
  overdue: boolean;
  last_error: string | null;
  fix: string | null;
}

export type WriteState = 'cloning' | 'failed' | 'restarting';
