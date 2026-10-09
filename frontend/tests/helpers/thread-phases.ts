import type { Conversation } from 'frontend/data/api';

export const RECORDED = {
 "author": {
  "assumed-done": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"assumed-done\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": "thanks the author, asks for nothing",
     "reason_code": "agent-declined",
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "assumed_done",
   "reopened": false,
   "state": "assumed-done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "declined": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"declined\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": "only the author can choose between the two",
     "reason_code": "agent-declined",
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "deferred": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"deferred\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "defer",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "deferred",
   "reopened": false,
   "state": "deferred",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "discarded": {
   "anchor": {
    "is_outdated": false,
    "line": 11,
    "original_commit": null,
    "original_line": null,
    "original_start_line": null,
    "path": "billing/invoice_writer.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": null,
     "id": null,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00Z",
   "etag": "\"discarded\"",
   "gist": "call it write_iso",
   "github_node_id": null,
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "draft_0000000000000001",
   "kind": "draft",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "create-draft",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000002",
     "kind": "discard",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "discarded",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "draft": {
   "anchor": {
    "is_outdated": false,
    "line": 11,
    "original_commit": null,
    "original_line": null,
    "original_start_line": null,
    "path": "billing/invoice_writer.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": null,
     "id": null,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00Z",
   "etag": "\"draft\"",
   "gist": "call it write_iso",
   "github_node_id": null,
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "draft_0000000000000001",
   "kind": "draft",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "create-draft",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "draft",
   "reopened": false,
   "state": "draft",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "enrolled": {
   "anchor": {
    "is_outdated": false,
    "line": 11,
    "original_commit": null,
    "original_line": null,
    "original_start_line": null,
    "path": "billing/invoice_writer.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": null,
     "id": null,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00Z",
   "etag": "\"enrolled\"",
   "gist": "call it write_iso",
   "github_node_id": null,
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "draft_0000000000000001",
   "kind": "draft",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "create-draft",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000002",
     "kind": "enrol",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "enrolled",
   "reopened": false,
   "state": "enrolled",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "failed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"failed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 3,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": "the tests would not run",
     "reason_code": "max-attempts",
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "filing": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"filing\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "ticket",
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "requeued",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "PRRT_a.3",
     "kind": "file",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "running",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "landing",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "filing failed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"filing failed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "ticket",
     "reason": "Jira refused the project key PROJ",
     "reason_code": "file-failed",
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "PRRT_a.3",
     "kind": "file",
     "lands": null,
     "reason": "Jira refused the project key PROJ",
     "reason_code": "file-failed",
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "landed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "octocat",
     "created_at": "2026-01-01T00:00:00Z",
     "id": 9001,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"landed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "commit",
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "landing": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"landing\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "commit",
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "running",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "landing",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "proposed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"proposed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "push failed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"push failed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "commit",
     "reason": "To github.com:o/r.git\n ! [rejected]  fix-the-widget -> fix-the-widget (fetch first)\nerror: failed to push some refs to 'github.com:o/r.git'",
     "reason_code": "push-failed",
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "queued": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"queued\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 0,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": null,
     "state": "pending",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "queued",
   "state_changed_at": null,
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "rebasing": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"rebasing\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "commit",
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "requeued",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.3",
     "kind": "rebase",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "running",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "landing",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "rejected": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"rejected\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "reject",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "rejected",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "removed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"removed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": true,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "removed",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "reply failed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"reply failed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "approve",
     "lands": "commit",
     "reason": "gh graphql mutation failed: Could not resolve to a node with the global id of 'PRRT_a'",
     "reason_code": "reply-failed",
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "resolved": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "octocat",
     "created_at": "2026-01-01T00:00:00Z",
     "id": 9001,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"resolved\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "resolve",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "resolved",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "rework": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"rework\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "op_000000000001",
     "kind": "rework",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "running",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "rework",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "session": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"session\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "start-session",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": null,
     "state": "running",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "in-session",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "stopped": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"stopped\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": "stopped before it finished",
     "reason_code": "withdrawn",
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "refused",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "stop",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "waiting": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "octocat",
     "created_at": "2026-01-01T00:00:00Z",
     "id": 9001,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"waiting\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "reply",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "waiting_on_reviewer",
   "reopened": false,
   "state": "waiting",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "working": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "anna",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"working\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": 1,
     "attempts_allowed": 3,
     "id": "PRRT_a.1",
     "kind": "first",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00.000000Z",
     "settled_at": null,
     "state": "running",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "open",
   "reopened": false,
   "state": "working",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  }
 },
 "reviewer": {
  "answered": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "anna",
     "created_at": "2026-09-12T10:30:00Z",
     "id": 2,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"answered\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [],
   "record_state": "open",
   "reopened": false,
   "state": "ready",
   "state_changed_at": null,
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "assumed-done": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "anna",
     "created_at": "2026-09-12T10:30:00Z",
     "id": 2,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"assumed-done\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [],
   "record_state": "assumed_done",
   "reopened": false,
   "state": "assumed-done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "confirmed": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "anna",
     "created_at": "2026-09-12T10:30:00Z",
     "id": 2,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"confirmed\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "confirm",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "confirmed",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "deferred": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "anna",
     "created_at": "2026-09-12T10:30:00Z",
     "id": 2,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"deferred\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "defer",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "deferred",
   "reopened": false,
   "state": "deferred",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "discarded": {
   "anchor": {
    "is_outdated": false,
    "line": 11,
    "original_commit": null,
    "original_line": null,
    "original_start_line": null,
    "path": "billing/invoice_writer.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": null,
     "id": null,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00Z",
   "etag": "\"discarded\"",
   "gist": "call it write_iso",
   "github_node_id": null,
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "draft_0000000000000001",
   "kind": "draft",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "create-draft",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000002",
     "kind": "discard",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "discarded",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "draft": {
   "anchor": {
    "is_outdated": false,
    "line": 11,
    "original_commit": null,
    "original_line": null,
    "original_start_line": null,
    "path": "billing/invoice_writer.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": null,
     "id": null,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00Z",
   "etag": "\"draft\"",
   "gist": "call it write_iso",
   "github_node_id": null,
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "draft_0000000000000001",
   "kind": "draft",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "create-draft",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "draft",
   "reopened": false,
   "state": "draft",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "enrolled": {
   "anchor": {
    "is_outdated": false,
    "line": 11,
    "original_commit": null,
    "original_line": null,
    "original_start_line": null,
    "path": "billing/invoice_writer.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": null,
     "id": null,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00Z",
   "etag": "\"enrolled\"",
   "gist": "call it write_iso",
   "github_node_id": null,
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "draft_0000000000000001",
   "kind": "draft",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "create-draft",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    },
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000002",
     "kind": "enrol",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "enrolled",
   "reopened": false,
   "state": "enrolled",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "not-mine": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "human",
   "comments": [
    {
     "author": "ben",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"not-mine\"",
   "gist": "this could use a docstring",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [],
   "record_state": "not_mine",
   "reopened": false,
   "state": "not-mine",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "resolved": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "anna",
     "created_at": "2026-09-12T10:30:00Z",
     "id": 2,
     "review_state": null
    },
    {
     "author": "octocat",
     "created_at": "2026-01-01T00:00:00Z",
     "id": 9001,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"resolved\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": true,
   "github_resolved_at": "2026-09-12T11:00:00Z",
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "resolve",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "resolved",
   "reopened": false,
   "state": "done",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  },
  "waiting": {
   "anchor": {
    "is_outdated": false,
    "line": 42,
    "original_commit": "a1b2c3d",
    "original_line": 42,
    "original_start_line": null,
    "path": "src/foo.py",
    "side": "RIGHT",
    "start_line": null,
    "start_side": null
   },
   "author_kind": "mine",
   "comments": [
    {
     "author": "octocat",
     "created_at": "2026-09-12T10:00:00Z",
     "id": 1,
     "review_state": "CHANGES_REQUESTED"
    },
    {
     "author": "anna",
     "created_at": "2026-09-12T10:30:00Z",
     "id": 2,
     "review_state": null
    },
    {
     "author": "octocat",
     "created_at": "2026-01-01T00:00:00Z",
     "id": 9001,
     "review_state": null
    }
   ],
   "created_at": "2026-09-12T11:00:00.000000Z",
   "etag": "\"waiting\"",
   "gist": "rename the helper",
   "github_node_id": "PRRT_a",
   "github_removed": false,
   "github_resolved": null,
   "github_resolved_at": null,
   "key": "PRRT_a",
   "kind": "review",
   "mention": false,
   "operations": [
    {
     "attempts": null,
     "attempts_allowed": null,
     "id": "op_000000000001",
     "kind": "reply",
     "lands": null,
     "reason": null,
     "reason_code": null,
     "requested_at": "2026-09-12T11:00:00Z",
     "settled_at": "2026-09-12T11:00:00Z",
     "state": "applied",
     "steps_done": null,
     "steps_total": null,
     "ticket_key": null
    }
   ],
   "record_state": "waiting_on_reviewer",
   "reopened": false,
   "state": "waiting",
   "state_changed_at": "2026-09-12T11:00:00Z",
   "unread": false,
   "updated_at": "2026-09-12T11:00:00Z"
  }
 }
} satisfies Record<'author' | 'reviewer', Record<string, Conversation>>;
