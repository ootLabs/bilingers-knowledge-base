// Dates as a person reads them, in one place, because "kiedy to się zmieniło"
// is on three panel screens and three different formats would read as three
// different pieces of information.

const FORMAT = new Intl.DateTimeFormat("pl-PL", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/**
 * One timestamp as Polish prose, in the reader's own time zone.
 *
 * An unparseable value comes back as an empty string rather than as "Invalid
 * Date": a broken timestamp is worth showing nothing for, and it must not turn
 * a working list into a screen full of English error text.
 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const moment = new Date(value);
  return Number.isNaN(moment.getTime()) ? "" : FORMAT.format(moment);
}
