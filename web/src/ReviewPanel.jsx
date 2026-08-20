import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./api.js";

/**
 * The code being authorised — not a description of it.
 *
 * The approval card used to show a name, a one-liner and a risk level.
 * None of that is the thing being approved; the thing being approved is
 * source a model wrote that will run on the owner's infrastructure.
 *
 * Deliberately collapsed by default and opened explicitly. An owner who
 * has to click "show me the code" has made a choice; one who is shown a
 * wall of source on every card learns to scroll past it.
 */
export default function ReviewPanel({ requestId }) {
  const [review, setReview] = useState(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || review) return;

    api
      .review(requestId)
      .then(setReview)
      .catch((err) => setError(err.message));
  }, [open, requestId, review]);

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-[10px] text-cyan hover:underline"
      >
        {open ? "hide the code" : "review the code before approving →"}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            {error && <p className="text-[10px] text-danger mt-2">{error}</p>}

            {!review && !error && (
              <p className="text-[10px] text-muted mt-2">loading…</p>
            )}

            {review && review.note && (
              <p className="text-[10px] text-muted mt-2">{review.note}</p>
            )}

            {review && review.code && (
              <div className="mt-2 space-y-2">
                <Evidence review={review} />

                {review.is_first_version ? (
                  <Labelled label="PROPOSED SOURCE (first version)">
                    <Code text={review.code} />
                  </Labelled>
                ) : (
                  <Labelled
                    label={`DIFF vs installed v${review.current_version}`}
                  >
                    <Diff lines={review.diff} />
                  </Labelled>
                )}

                {review.test_code && (
                  <Labelled label="TESTS IT MUST PASS">
                    <Code text={review.test_code} />
                  </Labelled>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Evidence({ review }) {
  const rows = [
    ["safety screen", review.safety?.safe === true],
    ["sandbox tests", review.tests?.passed === true],
    [
      review.evaluation?.status === "SCORED"
        ? `evaluator ${review.evaluation.score}/100`
        : "evaluator UNSCORED",
      review.evaluation?.status === "SCORED",
    ],
    [
      review.research?.grounded
        ? `${review.research.source_count} sources`
        : "research ungrounded",
      review.research?.grounded === true,
    ],
  ];

  return (
    <ul className="text-[10px] font-mono space-y-0.5">
      {rows.map(([label, ok]) => (
        <li key={label} className={ok ? "text-ok" : "text-muted"}>
          {ok ? "✓" : "✗"} {label}
        </li>
      ))}
    </ul>
  );
}

function Labelled({ label, children }) {
  return (
    <div>
      <p className="text-[9px] tracking-[0.15em] text-muted mb-1">{label}</p>
      {children}
    </div>
  );
}

function Code({ text }) {
  return (
    <pre className="text-[10px] font-mono bg-void border border-edge rounded p-2 overflow-x-auto max-h-56 overflow-y-auto scroll-thin whitespace-pre">
      {text}
    </pre>
  );
}

function Diff({ lines }) {
  if (!lines?.length) {
    return (
      <p className="text-[10px] text-muted">
        No change from the installed version.
      </p>
    );
  }

  return (
    <pre className="text-[10px] font-mono bg-void border border-edge rounded p-2 overflow-x-auto max-h-56 overflow-y-auto scroll-thin">
      {lines.map((line, index) => (
        <div
          key={index}
          className={
            line.startsWith("+") && !line.startsWith("+++")
              ? "text-ok"
              : line.startsWith("-") && !line.startsWith("---")
              ? "text-danger"
              : "text-muted"
          }
        >
          {line}
        </div>
      ))}
    </pre>
  );
}
