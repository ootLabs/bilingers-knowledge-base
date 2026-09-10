// The Polish dictionary, in one object, assembled from its two halves.
//
// `translations.ts` types its registry against this, so a second locale
// still has to match the whole shape or `npm run typecheck` fails. Both
// halves are `as const`, and spreading them here keeps every string a
// literal type rather than widening it to `string`.
import panel from "./panel";
import parent from "./parent";

const pl = {
  ...parent,
  panel,
} as const;

export default pl;
