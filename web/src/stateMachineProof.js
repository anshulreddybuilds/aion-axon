/**
 * Pure display logic for the Judge Mode state-machine card. Split out of
 * StateMachineCard.jsx (JSX, not directly Node-testable) for the same
 * reason missionStages.jsx/missionApprovalReconcile.js are split from
 * their consuming components: this repo's frontend has zero test
 * framework configured, and a plain Node script can only import plain
 * JS, not JSX.
 *
 * Never invents a transition. Every function here only reads what
 * GET /beastmode/state-machine actually returned.
 */

export function formatPath(states) {
  return (states || []).join(" → ");
}

export function isLegalTransition(transitions, from, to) {
  return Boolean(transitions?.[from]?.includes(to));
}

/**
 * A fixed set of the exact shortcuts a governed system must forbid,
 * checked against the REAL transition table rather than asserted as
 * marketing copy. State names match app/beastmode/state_machine.py's
 * actual constants -- not invented, not the generic names an earlier
 * prompt in this project's history used ("REJECTED", "PENDING") that
 * don't exist in this schema.
 */
export const SELF_AUTHORIZATION_SHORTCUTS = [
  { from: "REQUESTED", to: "INSTALLED", label: "a fresh request installing itself" },
  { from: "AWAITING_APPROVAL", to: "INSTALLED", label: "skipping the human decision" },
  { from: "APPROVAL_REJECTED", to: "INSTALLED", label: "installing after rejection" },
  { from: "EVALUATING", to: "INSTALLED", label: "installing before approval exists at all" },
];

export function checkSelfAuthorizationShortcuts(transitions) {
  return SELF_AUTHORIZATION_SHORTCUTS.map((shortcut) => ({
    ...shortcut,
    blocked: !isLegalTransition(transitions, shortcut.from, shortcut.to),
  }));
}
