// Shared, restrained motion language. One entrance (fade + small rise),
// one hover feel, all cheap (transform/opacity only) and reduced-motion safe.
import type { Variants } from "framer-motion";

/** Container that staggers its children's entrance. */
export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
};

/** Child entrance: fade + 6px rise. */
export const riseItem: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: [0.22, 1, 0.36, 1] } },
};

/** Simple fade for overlays. */
export const fade: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.2 } },
};

/** Standard props to reveal a block once when it scrolls into view. */
export const revealOnce = {
  initial: "hidden" as const,
  whileInView: "show" as const,
  viewport: { once: true, margin: "-60px" },
};
