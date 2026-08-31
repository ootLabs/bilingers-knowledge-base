import { DEFAULT_LOCALE, type Locale } from "./config";
import pl from "./locales/pl";

// Adding a locale: create lib/i18n/locales/<code>.ts exporting the same
// shape as locales/pl.ts, then add one line here. Nothing else in the app
// changes; no component, page, or route touches this registry directly.
const dictionaries: Record<Locale, typeof pl> = {
  pl,
};

export function getDictionary(locale: Locale = DEFAULT_LOCALE) {
  return dictionaries[locale];
}
